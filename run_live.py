# run_live.py
from __future__ import annotations

import argparse
import os  # noqa: F401  # intentionally kept
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

# ---- project root on path ----
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Top-level imports that must remain at top
# ...existing code...

# avoid importing safe_create_order at top-level to prevent redefinition warnings

load_dotenv()


# -------- ccxt exchange bootstrap --------
def _pick_exchanges() -> List[str]:
    # allow REGION to hint default exchange order
    region = os.getenv("REGION", "").strip().upper() or "GLOBAL"
    # prioritized candidates
    if region in ("US", "USA"):
        return [
            os.getenv("EXCHANGE_ID", "binanceus"),
            "coinbase",
            "kraken",
            "okx",
            "bybit",
            "gateio",
        ]
    return [
        os.getenv("EXCHANGE_ID", "bybit"),
        "okx",
        "binance",
        "gateio",
        "kraken",
        "coinbase",
        "binanceus",
    ]


def _make_exchange_trylist() -> List[Any]:
    import ccxt

    tries = []
    for ex_id in _pick_exchanges():
        if not ex_id:
            continue
        try:
            klass = getattr(ccxt, ex_id)
        except AttributeError:
            continue
        # allow configurable timeout via environment (milliseconds)
        timeout_ms = int(os.getenv("CCXT_TIMEOUT_MS", "30000"))
        opts = {
            "enableRateLimit": True,
            "timeout": timeout_ms,
            "apiKey": os.getenv("API_KEY") or "",
            "secret": os.getenv("API_SECRET") or "",
        }
        # bybit testnet
        if ex_id == "bybit" and os.getenv("BYBIT_TESTNET", "false").lower() == "true":
            opts["urls"] = {"api": "https://api-testnet.bybit.com"}
        tries.append(klass(opts))
    return tries


def ensure_exchange():
    from router import ExchangeRouter

    router = ExchangeRouter()
    router._load_markets_safe()
    return router

# provide a safe top-level reference for `place_market` so linters don't flag F821
try:
    from order_utils import place_market  # type: ignore
except Exception:
    def place_market(*args, **kwargs):
        """Fallback stub used at import time to satisfy linters; real implementation
        is imported locally where needed.
        """
        raise RuntimeError("place_market is not available in this environment")


# -------- data fetch --------
def fetch_df(ex, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    # use router safe wrapper when available
    raw = []
    # retry/backoff settings (env-driven)
    retries = int(os.getenv("FETCH_RETRIES", "3"))
    base_backoff = float(os.getenv("FETCH_BACKOFF_S", "0.5"))

    for attempt in range(max(1, retries)):
        try:
            # Prefer router-like safe wrapper; many callsites pass a router.ExchangeRouter
            if hasattr(ex, "safe_fetch_ohlcv"):
                try:
                    raw = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                except Exception as e:
                    print(f"[run_live] safe_fetch_ohlcv failed for {symbol}: {e}")
                    raw = []
            else:
                # try a guarded direct fetch if present
                try:
                    if hasattr(ex, "fetch_ohlcv"):
                        raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                    else:
                        raw = []
                except Exception as e:
                    print(f"[run_live] fetch_ohlcv failed for {symbol}: {e}")
                    raw = []
        except Exception as e:
            print(f"[run_live] safe fetch wrapper raised for {symbol}: {e}")
            raw = []

        if raw:
            break

        # exponential backoff before retrying
        if attempt < retries - 1:
            sleep_s = base_backoff * (2 ** attempt)
            time.sleep(sleep_s)
    if not raw:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "vol"]
        )
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "vol"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms")
    return df


# -------- OCO helper (spot best-effort) --------
def place_oco_ccxt(
    ex,
    symbol: str,
    side: str,
    qty: float,
    entry_px: float,
    stop_px: float,
    take_px: float,
) -> Dict[str, Any]:
    """
    Generic OCO wrapper: most spot venues lack a native OCO; we:
    1) Place market order immediately
    2) Place stop-loss sell/buy + take-profit sell/buy as separate orders (reduce intent)
    NOTE: Some venues require margin/stop trigger params; we keep it minimal & best-effort.
    """
    # Best-effort entry then optional TP/SL as siblings. This function never raises.
    # local import to avoid top-level import after runtime init
    from order_utils import place_market, safe_create_order

    try:
        order = None
        # entry
        try:
            if hasattr(ex, "safe_place_order"):
                order = ex.safe_place_order(symbol, side, qty)
            else:
                order = place_market(ex, symbol, side, qty)
        except Exception:
            # last resort: try create_order
            try:
                order = safe_create_order(ex, "market", symbol, side, qty)
            except Exception:
                order = {"ok": False, "error": "entry failed"}

        if not order:
            return {"ok": False, "error": "entry failed or no order method"}

        opp = "sell" if side == "buy" else "buy"
        notified = {"entry": order}

        # take-profit
        try:
            if hasattr(ex, "safe_place_order"):
                notified["tp"] = ex.safe_place_order(
                    symbol, opp, qty, price=take_px, params={"reduceOnly": True}
                )
            elif hasattr(ex, "create_limit_order"):
                try:
                    notified["tp"] = ex.create_limit_order(
                        symbol, opp, qty, float(take_px)
                    )
                except Exception:
                    # fall back to generic create_order if present
                    try:
                        notified["tp"] = safe_create_order(
                            ex,
                            "limit",
                            symbol,
                            opp,
                            qty,
                            float(take_px),
                            params={"reduceOnly": True},
                        )
                    except Exception:
                        notified["tp"] = {"ok": False, "error": "tp create failed"}
            elif hasattr(ex, "create_order"):
                try:
                    notified["tp"] = safe_create_order(
                        ex,
                        "limit",
                        symbol,
                        opp,
                        qty,
                        float(take_px),
                        params={"reduceOnly": True},
                    )
                except Exception:
                    try:
                        notified["tp"] = safe_create_order(
                            ex, "limit", symbol, opp, qty, float(take_px)
                        )
                    except Exception:
                        notified["tp"] = {"ok": False, "error": "tp create failed"}
            else:
                notified["tp_err"] = "no tp order method"
        except Exception as e:
            notified["tp_err"] = str(e)

        # stop-loss
        try:
            params = {"reduceOnly": True, "stopPrice": float(stop_px)}
            if hasattr(ex, "safe_place_order"):
                notified["sl"] = ex.safe_place_order(
                    symbol, opp, qty, price=stop_px, params=params
                )
            elif hasattr(ex, "create_stop_order"):
                try:
                    notified["sl"] = ex.create_stop_order(
                        symbol, opp, qty, float(stop_px), params=params
                    )
                except Exception:
                    try:
                        from order_utils import safe_create_order

                        notified["sl"] = safe_create_order(
                            ex, "stop", symbol, opp, qty, float(stop_px), params=params
                        )
                    except Exception:
                        notified["sl"] = {"ok": False, "error": "sl create failed"}
            elif hasattr(ex, "create_order"):
                try:
                    # prefer centralized safe_create_order wrapper
                    notified["sl"] = safe_create_order(
                        ex, "stop", symbol, opp, qty, stop_px, params=params
                    )
                except Exception:
                    try:
                        notified["sl"] = safe_create_order(
                            ex, "stop", symbol, opp, qty, stop_px
                        )
                    except Exception:
                        notified["sl"] = {"ok": False, "error": "sl create failed"}
            else:
                notified["sl_err"] = "no sl order method"
        except Exception as e:
            notified["sl_err"] = str(e)

        return {"ok": True, "orders": notified}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
            if verb == "flatten" and len(parts) > 1:
                sym = parts[1].upper()
                base = sym.split("/")[0]
                try:
                    bal = (
                        router.safe_fetch_balance()
                        if hasattr(router, "safe_fetch_balance")
                        else router.fetch_balance()
                    )
                except Exception:
                    bal = {}
                amt = float((bal.get("free") or {}).get(base, 0) or 0)
                if amt > 0 and live:
                    try:
                        if hasattr(router, "safe_place_order"):
                            router.safe_place_order(sym, "sell", amt)
                        else:
                            # prefer order_utils.place_market if available, else use top-level stub
                            try:
                                import order_utils

                                order_utils.place_market(router, sym, "sell", amt)
                            except Exception:
                                # top-level stub defined earlier will raise at runtime if not available
                                # reference via globals() to satisfy linters and runtime
                                globals().get("place_market", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("place_market is not available")))(router, sym, "sell", amt)
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

    # local imports (moved from top-level to avoid E402 warnings)
    from utils import load_config, setup_logger
    from acct_portfolio import ccxt_summary
    from cmd_reader import read_commands
    from guardrails import GuardConfig, TradeGuard
    from ledger import daily_pnl_text
    from notifier import TelegramNotifier
    from risk import RiskConfig
    from strategy import TrendBreakoutStrategy

    cfg = load_config("config.yml")
    log = setup_logger(
        "live",
        level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=os.getenv("LOG_DIR", "logs"),
    )
    live = os.getenv("ENABLE_LIVE", "false").lower() == "true"

    router = ensure_exchange()
    # explicit safety guard: if live is disabled, block any method that would send
    # real orders to an exchange unless the exchange is explicitly the `paper` adapter.
    def _disable_live_orders(router_obj, logger):
        try:
            ex_id = getattr(router_obj, "id", "") or os.getenv("EXCHANGE_ID", "").lower()
            if ex_id and str(ex_id).lower() == "paper":
                logger.info("Exchange is paper; order blocking not applied.")
                return
        except Exception:
            ex_id = os.getenv("EXCHANGE_ID", "")

        if live:
            return

        blocked = [
            "create_order",
            "create_limit_order",
            "create_stop_order",
            "safe_place_order",
            "safe_create_order",
        ]

        for name in blocked:
            if hasattr(router_obj, name):
                try:
                    setattr(router_obj, f"_orig_{name}", getattr(router_obj, name))
                except Exception:
                    pass

            # create a closure capturing the method name
            def make_stub(n):
                def stub(*args, **kwargs):
                    logger.warning(f"Blocked order call {n} because ENABLE_LIVE is not 'true'. Args={args} kwargs={kwargs}")
                    return {"ok": False, "error": "live disabled"}

                return stub

            try:
                setattr(router_obj, name, make_stub(name))
            except Exception:
                # best-effort; don't fail startup
                logger.debug(f"Could not override {name} on router")

    _disable_live_orders(router, log)
    tg = TelegramNotifier()
    tg.hello(router.id, args.symbols, args.timeframe)

    # strategy + risk + guards
    TrendBreakoutStrategy(
        ema_fast=cfg["strategy"]["ema_fast"],
        ema_slow=cfg["strategy"]["ema_slow"],
        bb_period=cfg["strategy"]["bb_period"],
        bb_std=cfg["strategy"]["bb_std"],
        bb_bw_lookback=cfg["strategy"]["bb_bandwidth_lookback"],
        bb_bw_quantile=cfg["strategy"]["bb_bandwidth_quantile"],
        atr_period=cfg["risk"]["atr_period"],
    )
    RiskConfig(**cfg["risk"])
    TradeGuard(GuardConfig(**cfg["guards"]))

    # discover symbols (simple, from markets)
    if args.symbols == "auto":
        syms = [
            s
            for s, m in router.markets.items()
            if m.get("spot") and s.endswith("/USDT")
        ]
        preferred = {
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "XRP/USDT",
            "DOGE/USDT",
            "AVAX/USDT",
            "LINK/USDT",
            "MATIC/USDT",
            "TON/USDT",
        }
        # prefer a short curated list when available, else fall back to top symbols
        syms = [s for s in syms if s in preferred] or syms[:15]
    else:
        syms = [s.strip().upper() for s in args.symbols.split(",")]

    last_bal_ts = 0.0

    # --- UltraCore god mode integration ---
    from ultra_core import UltraCore
    from universe import Universe

    ultra_universe = Universe(router) if hasattr(router, "markets") else None
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
        if args.balance_every > 0 and now - last_bal_ts >= args.balance_every * 60:
            try:
                tg.balance_snapshot(ccxt_summary(router))
                tg.daily_pnl(daily_pnl_text())
            except Exception as e:
                tg.note(f"portfolio/pnl unavailable: {e}")
            last_bal_ts = now

        time.sleep(5)
