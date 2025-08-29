# run_live_meme.py
from __future__ import annotations
import os, sys, time, math, argparse, datetime as dt
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils import load_config, setup_logger, bps_to_frac
from strategy import TrendBreakoutStrategy
from risk import RiskConfig
from guardrails import GuardConfig, TradeGuard

from notifier import TelegramNotifier, CMD_INBOX
from news_service import bullets_for
from ledger import log_entry, log_exit, daily_pnl_text
from acct_portfolio import ccxt_summary
from regional_utils import primary_exchange, fallback_exchange


# ------- universe helpers (memecoins) -------
MEME_DEFAULTS = [
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "BONK/USDT", "WIF/USDT",
    "FLOKI/USDT", "BABYDOGE/USDT"
]

# ---- error throttle (in-memory) ----
_ERROR_MUTE = {}  # key -> next_allowed_ts

def notify_once(notifier, key: str, message: str, cooldown_sec: int = 900):
    now = time.time()
    nxt = _ERROR_MUTE.get(key, 0)
    if now >= nxt:
        notifier.note(message)
        _ERROR_MUTE[key] = now + cooldown_sec


def _normalize_symbols_for_venue(symbols, venue_id: str):
    # BinanceUS tends to use /USD instead of /USDT for some pairs
    if venue_id.lower() in ("binanceus", "coinbase", "kraken"):
        out = []
        for s in symbols:
            base, quote = s.split("/")
            if quote == "USDT":
                out.append(f"{base}/USD")
            else:
                out.append(s)
        return out
    return symbols

# --------- minimal CCXT factory ----------
# ---- exchange factory with optional proxy & sane timeout/backoff ----
def make_exchange(exchange_id: str, api_key=None, api_secret=None):
    import ccxt
    proxies = None
    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("PROXY_URL")
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    ex = getattr(ccxt, exchange_id)({
        "apiKey": api_key or os.getenv("API_KEY"),
        "secret": api_secret or os.getenv("API_SECRET"),
        "enableRateLimit": True,
        "timeout": 15000,
        **({"proxies": proxies} if proxies else {}),
        "options": {
            "defaultType": "spot"
        }
    })
    return ex

def _consume_commands():
    if not CMD_INBOX.exists(): return []
    try:
        import json
        with open(CMD_INBOX, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f if x.strip()]
        CMD_INBOX.unlink(missing_ok=True)
        cmds = []
        for line in lines:
            try:
                d = json.loads(line)
                c = d.get("cmd")
                if c: cmds.append(c)
            except Exception:
                pass
        return cmds
    except Exception:
        return []

def _parse_qty(s: str, default: float) -> float:
    try:
        v = float(s)
        return v if v > 0 else default
    except Exception:
        return default

print("run_live_meme.py starting…")

def live_loop(exchange_id: str, symbols: list, timeframe: str, cfg: dict,
              fixed_stake_usd: float = 1.5,
              balance_every_min: float | None = 30.0,
              report_hour: str | None = "21:00"):
    load_dotenv()
    log = setup_logger("live_meme", level=os.getenv("LOG_LEVEL","INFO"),
                       log_dir=os.getenv("LOG_DIR","logs"))
    nfy = TelegramNotifier()
    # Notifier diagnostic: surface enabled flag and presence of token/chat_id
    try:
        enabled = getattr(nfy, 'enabled', False)
        token = getattr(nfy, 'token', '') or os.getenv('TELEGRAM_BOT_TOKEN','')
        chat = getattr(nfy, 'chat_id', '') or os.getenv('TELEGRAM_CHAT_ID','')
        token_ok = bool(token.strip())
        chat_ok = bool(str(chat).strip())
        log.info('Notifier enabled=%s token_present=%s chat_id_present=%s', enabled, token_ok, chat_ok)
        if not enabled:
            log.warning('Telegram notifier disabled. To enable, set TELEGRAM_ENABLED=true and TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in your .env or environment.')
        elif not token_ok or not chat_ok:
            log.warning('Telegram notifier enabled but missing token or chat id. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.')
    except Exception:
        log.exception('Notifier diagnostic failed')

    from router import ExchangeRouter
    from ultra_core import UltraCore
    ex = ExchangeRouter()
    # Diagnostic: show router info and a small market sample to help debugging startup
    try:
        info = ex.info()
        log.info("ExchangeRouter info: %s", info)
        # show first 10 market symbols
        try:
            sample = list(ex.markets.keys())[:10]
            log.info("Sample markets (%d): %s", len(sample), sample)
        except Exception:
            log.info("Could not sample markets")
    except Exception as e:
        log.error("Router init diagnostics failed: %s", e)
    log.info("Starting meme loop exchange=%s symbols=%s timeframe=%s",
             exchange_id, symbols, timeframe)
    symbols = _normalize_symbols_for_venue(symbols, exchange_id)
    # Resolve symbols against router markets where possible and log mapping
    resolved = []
    missing = []
    for s in symbols:
        try:
            if s in ex.markets:
                resolved.append(s)
            else:
                # try swapping USD/USDT
                alt = s.replace('/USDT', '/USD') if s.endswith('/USDT') else s.replace('/USD', '/USDT')
                if alt in ex.markets:
                    resolved.append(alt)
                else:
                    missing.append(s)
        except Exception:
            missing.append(s)
    if resolved:
        log.info("Resolved meme symbols: %s", resolved)
    if missing:
        log.warning("Some meme symbols not found on exchange markets: %s", missing)
    symbols = resolved or symbols
    nfy.hello(f"{exchange_id} (meme)", symbols, timeframe)
    # Startup health summary: try to post balances and daily pnl if notifier enabled
    try:
        if getattr(nfy, 'enabled', False):
            try:
                nfy.balance_snapshot([ccxt_summary(ex)])
            except Exception:
                nfy.note('balance snapshot failed at startup')
            try:
                nfy.daily_pnl(daily_pnl_text())
            except Exception:
                nfy.note('daily PnL summary failed at startup')
    except Exception:
        log.info('Notifier startup summary skipped')
    ultra = UltraCore(ex, None, logger=log)

    fee_frac  = bps_to_frac(cfg.get("fee_bps", 10))
    slip_frac = bps_to_frac(cfg.get("slippage_bps", 3))

    strat = TrendBreakoutStrategy(
        ema_fast=cfg["strategy"]["ema_fast"],
        ema_slow=cfg["strategy"]["ema_slow"],
        bb_period=cfg["strategy"]["bb_period"],
        bb_std=cfg["strategy"]["bb_std"],
        bb_bw_lookback=cfg["strategy"]["bb_bandwidth_lookback"],
        bb_bw_quantile=cfg["strategy"]["bb_bandwidth_quantile"],
        atr_period=cfg["risk"]["atr_period"]
    )
    risk_cfg = RiskConfig(
        initial_equity=cfg["risk"]["initial_equity"],
        risk_per_trade_bps=cfg["risk"]["risk_per_trade_bps"],
        max_daily_loss_bps=cfg["risk"]["max_daily_loss_bps"],
        max_open_positions=cfg["risk"]["max_open_positions"],
        atr_stop_mult=cfg["risk"]["atr_stop_mult"],
        atr_trail_mult=cfg["risk"]["atr_trail_mult"],
        atr_period=cfg["risk"]["atr_period"],
    )
    guard = TradeGuard(GuardConfig(**cfg["guards"]))

    live_enabled = os.getenv("ENABLE_LIVE","false").lower() == "true"
    equity = float(risk_cfg.initial_equity)
    open_pos: dict = {}

    day_tag = dt.datetime.utcnow().strftime("%Y-%m-%d")
    next_bal_ts = time.time() + (balance_every_min or 0) * 60 if balance_every_min else None

    def maybe_daily_report(force=False):
        nonlocal day_tag
        now = dt.datetime.utcnow()
        trigger = False
        if force:
            trigger = True
        elif report_hour:
            hh, mm = [int(x) for x in report_hour.split(":")]
            trigger = (now.strftime("%Y-%m-%d") != day_tag) or (now.hour==hh and now.minute==mm)
        if trigger:
            # use daily_pnl_text from ledger for a compact report
            try:
                nfy.daily_pnl(daily_pnl_text())
            except Exception as e:
                nfy.note(str(e))
            try:
                nfy.balance_snapshot([ccxt_summary(ex)])
            except Exception as e:
                nfy.note(str(e))
            day_tag = now.strftime("%Y-%m-%d")

    # Warm up
    ex.safe_fetch_ohlcv(symbols[0], timeframe=timeframe, limit=5)

    while True:
        # Commands
        nfy.poll_commands(throttle_ms=0)
        for cmd in _consume_commands():
            parts = cmd.split()
            if not parts: 
                continue
            verb = parts[0].lower()
            if verb == "/balance":
                try:
                    nfy.balance_snapshot([ccxt_summary(ex)])
                except Exception as e:
                    nfy.note(str(e))
                continue
            if verb in ("/buy","/sell","/flat"):
                sym = parts[1] if len(parts)>=2 else None
                qty = _parse_qty(parts[2], 0.0) if len(parts)>=3 else 0.0
                if not sym: 
                    continue
                try:
                    if verb == "/flat":
                        if sym in open_pos and live_enabled:
                            side = "sell" if open_pos[sym]["amount"] > 0 else "buy"
                            ex.safe_place_order(sym, side, abs(open_pos[sym]["amount"]))
                            log_exit(f"{sym}|{timeframe}|{int(time.time())}", exit_px=0.0, status="closed")
                            del open_pos[sym]
                        continue
                    if qty <= 0:
                        px = ex.safe_fetch_ticker(sym)["last"]
                        qty = max(0.0, float(fixed_stake_usd) / max(1e-9, px))
                    side = "buy" if verb=="/buy" else "sell"
                    if live_enabled:
                        ex.safe_place_order(sym, side, qty)
                    log_entry(venue=exchange_id, market="meme", symbol=sym, tf=timeframe, side=side, entry_px=0.0, qty=qty, sl=None, tp=None, meta={"tag": "cmd"})
                except Exception as e:
                    log.error("Command error %s: %s", cmd, e)

        # Balances + daily report
        if next_bal_ts and time.time() >= next_bal_ts:
            try:
                nfy.balance_snapshot([ccxt_summary(ex)])
            except Exception as e:
                nfy.note(str(e))
            next_bal_ts = time.time() + (balance_every_min or 0) * 60
        maybe_daily_report(False)

        # UltraCore god mode trading pass (protected)
        try:
            ultra.god_mode_cycle()
        except Exception as e:
            log.error("UltraCore cycle error: %s", e, exc_info=True)

        time.sleep(5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default=os.getenv("EXCHANGE_ID","binanceus"))
    ap.add_argument("--symbols", default="")                          # optional explicit list
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--stake_usd", type=float, default=1.5)
    ap.add_argument("--balance_every", type=float, default=30.0)
    args = ap.parse_args()

    cfg = load_config("config.yml")

    if args.symbols.strip():
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = MEME_DEFAULTS
    live_loop(args.exchange, symbols, args.timeframe, cfg,
              fixed_stake_usd=args.stake_usd,
              balance_every_min=args.balance_every,
              report_hour="21:00")
    
    # ...existing code...
