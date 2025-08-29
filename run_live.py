# run_live.py
from __future__ import annotations
import os, sys, time, math, argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from dotenv import load_dotenv

# ---- project root on path ----
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# ---- local modules (must exist) ----
from utils import load_config, setup_logger
from strategy import TrendBreakoutStrategy
from risk import RiskConfig
from guardrails import GuardConfig, TradeGuard
from news_service import bullets_for
from notifier import TelegramNotifier
from ledger import log_entry, log_exit, daily_pnl_text
from cmd_reader import read_commands           # writes by notifier.poll_commands()
from acct_portfolio import ccxt_summary            # pretty balances
from order_utils import place_market, safe_create_order

load_dotenv()

# -------- ccxt exchange bootstrap --------
def _pick_exchanges() -> List[str]:
    # allow REGION to hint default exchange order
    region = (os.getenv("REGION","").strip().upper() or "GLOBAL")
    # prioritized candidates
    if region in ("US","USA"):
        return [os.getenv("EXCHANGE_ID","binanceus"), "coinbase", "kraken", "okx", "bybit", "gateio"]
    return [os.getenv("EXCHANGE_ID","bybit"), "okx", "binance", "gateio", "kraken", "coinbase", "binanceus"]

def _make_exchange_trylist() -> List[Any]:
    import ccxt
    tries = []
    for ex_id in _pick_exchanges():
        if not ex_id: continue
        try:
            klass = getattr(ccxt, ex_id)
        except AttributeError:
            continue
        opts = {
            "enableRateLimit": True,
            "timeout": 15000,
            "apiKey": os.getenv("API_KEY") or "",
            "secret": os.getenv("API_SECRET") or "",
        }
        # bybit testnet
        if ex_id == "bybit" and os.getenv("BYBIT_TESTNET","false").lower()=="true":
            opts["urls"] = {"api": "https://api-testnet.bybit.com"}
        tries.append(klass(opts))
    return tries

def ensure_exchange():
    from router import ExchangeRouter
    router = ExchangeRouter()
    router._load_markets_safe()
    return router

# -------- data fetch --------
def fetch_df(ex, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    # use router safe wrapper when available
    raw = []
    try:
        # Prefer router-like safe wrapper; many callsites pass a router.ExchangeRouter
        if hasattr(ex, 'safe_fetch_ohlcv'):
            try:
                raw = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            except Exception as e:
                print(f"[run_live] safe_fetch_ohlcv failed for {symbol}: {e}")
                raw = []
        else:
            # try a guarded direct fetch if present
            try:
                if hasattr(ex, 'fetch_ohlcv'):
                    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                else:
                    raw = []
            except Exception as e:
                print(f"[run_live] fetch_ohlcv failed for {symbol}: {e}")
                raw = []
    except Exception as e:
        print(f"[run_live] safe fetch wrapper raised for {symbol}: {e}")
        raw = []
    if not raw:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","vol"])
    df = pd.DataFrame(raw, columns=["ts","open","high","low","close","vol"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms")
    return df

# -------- OCO helper (spot best-effort) --------
def place_oco_ccxt(ex, symbol: str, side: str, qty: float, entry_px: float,
                   stop_px: float, take_px: float) -> Dict[str,Any]:
    """
    Generic OCO wrapper: most spot venues lack a native OCO; we:
    1) Place market order immediately
    2) Place stop-loss sell/buy + take-profit sell/buy as separate orders (reduce intent)
    NOTE: Some venues require margin/stop trigger params; we keep it minimal & best-effort.
    """
    # Best-effort entry then optional TP/SL as siblings. This function never raises.
    try:
        order = None
        # entry
        try:
            if hasattr(ex, 'safe_place_order'):
                order = ex.safe_place_order(symbol, side, qty)
            else:
                order = place_market(ex, symbol, side, qty)
        except Exception:
            # last resort: try create_order
            try:
                from order_utils import safe_create_order
                order = safe_create_order(ex, 'market', symbol, side, qty)
            except Exception:
                order = {"ok": False, "error": "entry failed"}

        if not order:
            return {"ok": False, "error": "entry failed or no order method"}

        opp = 'sell' if side == 'buy' else 'buy'
        notified = {'entry': order}

        # take-profit
        try:
            if hasattr(ex, 'safe_place_order'):
                notified['tp'] = ex.safe_place_order(symbol, opp, qty, price=take_px, params={'reduceOnly': True})
            elif hasattr(ex, 'create_limit_order'):
                try:
                    notified['tp'] = ex.create_limit_order(symbol, opp, qty, float(take_px))
                except Exception:
                    # fall back to generic create_order if present
                    try:
                        notified['tp'] = safe_create_order(ex, 'limit', symbol, opp, qty, float(take_px), params={'reduceOnly': True})
                    except Exception:
                        notified['tp'] = {"ok": False, "error": "tp create failed"}
            elif hasattr(ex, 'create_order'):
                try:
                    notified['tp'] = safe_create_order(ex, 'limit', symbol, opp, qty, float(take_px), params={'reduceOnly': True})
                except Exception:
                    try:
                        notified['tp'] = safe_create_order(ex, 'limit', symbol, opp, qty, float(take_px))
                    except Exception:
                        notified['tp'] = {"ok": False, "error": "tp create failed"}
            else:
                notified['tp_err'] = 'no tp order method'
        except Exception as e:
            notified['tp_err'] = str(e)

        # stop-loss
        try:
            params = {'reduceOnly': True, 'stopPrice': float(stop_px)}
            if hasattr(ex, 'safe_place_order'):
                notified['sl'] = ex.safe_place_order(symbol, opp, qty, price=stop_px, params=params)
            elif hasattr(ex, 'create_stop_order'):
                try:
                    notified['sl'] = ex.create_stop_order(symbol, opp, qty, float(stop_px), params=params)
                except Exception:
                        try:
                            from order_utils import safe_create_order
                            notified['sl'] = safe_create_order(ex, 'stop', symbol, opp, qty, float(stop_px), params=params)
                        except Exception:
                            notified['sl'] = {"ok": False, "error": "sl create failed"}
            elif hasattr(ex, 'create_order'):
                try:
                    # prefer centralized safe_create_order wrapper
                    notified['sl'] = safe_create_order(ex, 'stop', symbol, opp, qty, stop_px, params=params)
                except Exception:
                    try:
                        notified['sl'] = safe_create_order(ex, 'stop', symbol, opp, qty, stop_px)
                    except Exception:
                        notified['sl'] = {"ok": False, "error": "sl create failed"}
            else:
                notified['sl_err'] = 'no sl order method'
        except Exception as e:
            notified['sl_err'] = str(e)

        return {'ok': True, 'orders': notified}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def handle_cmds_ccxt(cmds, router, tg, live: bool):
    """Process a small set of telegram commands safely.

    Currently supports:
      - FLATTEN <SYMBOL>
    Any command errors are reported to Telegram via tg.note and do not raise.
    """
    if not cmds:
        return
    for text in cmds:
        try:
            parts = (text or "").strip().split()
            if not parts:
                continue
            verb = parts[0].lower()
            if verb == 'flatten' and len(parts) > 1:
                sym = parts[1].upper()
                base = sym.split('/')[0]
                try:
                    bal = router.safe_fetch_balance() if hasattr(router, 'safe_fetch_balance') else router.fetch_balance()
                except Exception:
                    bal = {}
                amt = float((bal.get('free') or {}).get(base, 0) or 0)
                if amt > 0 and live:
                    try:
                        if hasattr(router, 'safe_place_order'):
                            router.safe_place_order(sym, 'sell', amt)
                        else:
                            place_market(router, sym, 'sell', amt)
                        tg.note(f"flattened {sym} {amt}")
                    except Exception as e:
                        tg.note(f"flatten failed: {e}")
                else:
                    tg.note(f"(paper) flat {sym} free={amt}")
            else:
                tg.note(f"unknown cmd: {text}")
        except Exception as e:
            try:
                tg.note(f"cmd error: {text} -> {e}")
            except Exception:
                pass

# -------- main --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="auto", help="comma list or 'auto'")
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--stake_usd", type=float, default=2.0)
    ap.add_argument("--top_k", type=int, default=3)
    ap.add_argument("--balance_every", type=int, default=30)  # minutes
    args = ap.parse_args()

    cfg = load_config("config.yml")
    log = setup_logger("live", level=os.getenv("LOG_LEVEL","INFO"), log_dir=os.getenv("LOG_DIR","logs"))
    live = (os.getenv("ENABLE_LIVE","false").lower()=="true")

    router = ensure_exchange()
    tg = TelegramNotifier()
    tg.hello(router.id, args.symbols, args.timeframe)

    # strategy + risk + guards
    strat = TrendBreakoutStrategy(
        ema_fast=cfg["strategy"]["ema_fast"], ema_slow=cfg["strategy"]["ema_slow"],
        bb_period=cfg["strategy"]["bb_period"], bb_std=cfg["strategy"]["bb_std"],
        bb_bw_lookback=cfg["strategy"]["bb_bandwidth_lookback"],
        bb_bw_quantile=cfg["strategy"]["bb_bandwidth_quantile"],
        atr_period=cfg["risk"]["atr_period"]
    )
    risk_cfg = RiskConfig(**cfg["risk"])
    guard = TradeGuard(GuardConfig(**cfg["guards"]))

    # discover symbols (simple, from markets)
    if args.symbols == "auto":
        syms = [s for s,m in router.markets.items() if m.get("spot") and s.endswith("/USDT")]
        preferred = {"BTC/USDT","ETH/USDT","SOL/USDT","XRP/USDT","DOGE/USDT","AVAX/USDT","LINK/USDT","MATIC/USDT","TON/USDT"}
        symbols = [s for s in syms if s in preferred] or syms[:15]
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    last_bal_ts = 0.0

    # --- UltraCore god mode integration ---
    from ultra_core import UltraCore
    from universe import Universe
    ultra_universe = Universe(router) if hasattr(router, 'markets') else None
    ultra = UltraCore(router, ultra_universe, logger=log)

    while True:
        # Handle Telegram commands
        try:
            handle_cmds_ccxt(read_commands(), router, tg, live)
        except Exception:
            pass

        # Run god mode trading cycle
        ultra.god_mode_cycle()

        # periodic balances + daily PnL
        now = time.time()
        if args.balance_every > 0 and now - last_bal_ts >= args.balance_every*60:
            try:
                tg.balance_snapshot(ccxt_summary(router))
                tg.daily_pnl(daily_pnl_text())
            except Exception as e:
                tg.note(f"portfolio/pnl unavailable: {e}")
            last_bal_ts = now

        time.sleep(5)
