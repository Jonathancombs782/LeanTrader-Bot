# portfolio.py
from __future__ import annotations

import os, math
from pathlib import Path
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv

# CCXT (crypto)
try:
    import ccxt  # type: ignore
except Exception:
    ccxt = None  # graceful if crypto not used

# MetaTrader 5 (FX)
try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    mt5 = None  # graceful if FX not used


load_dotenv()


# ---------- helpers ----------
def _fmt_usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    v = abs(x)
    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:,.2f}M"
    if v >= 1_000:
        return f"{sign}${v:,.0f}"
    return f"{sign}${v:,.2f}"


def _ensure_ccxt_exchange(exchange=None, exchange_id: Optional[str] = None):
    """
    Return a ready CCXT exchange instance.
    - If 'exchange' is provided, reuse it.
    - Else build from ENV: EXCHANGE_ID / API_KEY / API_SECRET
    """
    if exchange is not None:
        return exchange

    if ccxt is None:
        raise RuntimeError("ccxt not installed")

    ex_id = (exchange_id or os.getenv("EXCHANGE_ID") or "").lower().strip()
    if not ex_id:
        raise RuntimeError("Missing EXCHANGE_ID (e.g. 'binanceus', 'bybit').")

    api_key = os.getenv("API_KEY") or ""
    api_secret = os.getenv("API_SECRET") or ""

    klass = getattr(ccxt, ex_id)
    ex = klass({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        # a short-ish timeout helps prevent blocking loops
        "timeout": 15000,
    })
    # Some venues need apiKey even for public endpoints (BinanceUS quirks).
    # If you have credentials, set them in .env to avoid “requires apiKey” noise.
    return ex


def _estimate_in_quote(ex, asset: str, amount: float, quote: str = "USD") -> float:
    """
    Rough USD (or quote) value using a direct market if possible, else USDT fallback.
    """
    if amount <= 0:
        return 0.0
    a = asset.upper()
    q = quote.upper()

    # If asset is already the quote (USD / USDT)
    if a == q:
        return amount

    # Try A/QUOTE then A/USDT, then 0 if none
    symbols = [f"{a}/{q}", f"{a}/USDT"]
    from router import ExchangeRouter
    router = ExchangeRouter()
    for s in symbols:
        try:
            # Prefer router safe wrapper, fall back to direct fetch with guarded logs
            # Prefer router safe wrapper and guard any adapter fallbacks
            try:
                if hasattr(router, 'safe_fetch_ticker'):
                    ticker = router.safe_fetch_ticker(s)
                else:
                    try:
                        ticker = router.ex.fetch_ticker(s) if hasattr(router, 'ex') else {}
                    except Exception as e:
                        print(f"[acct_portfolio] fetch_ticker failed for {s}: {e}")
                        ticker = {}
            except Exception as e:
                print(f"[acct_portfolio] safe_fetch_ticker outer failed for {s}: {e}")
                ticker = {}
            px = float((ticker.get("last") if isinstance(ticker, dict) else None) or (ticker.get("close") if isinstance(ticker, dict) else None) or 0)
            if px > 0:
                return amount * px
        except Exception:
            continue
    return 0.0


# ---------- public: crypto balances ----------
def ccxt_summary(exchange=None, exchange_id: Optional[str] = None, quote: str = "USD") -> List[str]:
    """
    Returns pretty lines with non-zero balances and totals.
    If you already created an exchange instance, pass it via 'exchange'.
    Otherwise we will build from ENV (EXCHANGE_ID/API_KEY/API_SECRET).
    """
    ex = _ensure_ccxt_exchange(exchange, exchange_id)
    from router import ExchangeRouter
    router = ExchangeRouter()
    try:
        try:
            bal = router.safe_fetch_balance() if hasattr(router, 'safe_fetch_balance') else router.account().get("balance", {})
        except Exception as e:
            print(f"[acct_portfolio] safe_fetch_balance/account fetch failed: {e}")
            bal = router.account().get("balance", {})
    except Exception as e:
        raise RuntimeError(f"{ex.id} balance error: {e}")

    totals: Dict[str, float] = {}
    try:
        totals = {k.upper(): float(v or 0) for k, v in (bal.get("total") or {}).items()}
    except Exception:
        pass

    lines: List[str] = []
    total_quote = 0.0

    for asset, amt in sorted(totals.items()):
        if amt <= 0:
            continue
        try:
            est_q = _estimate_in_quote(ex, asset, amt, quote=quote)
            total_quote += est_q
            lines.append(f"{asset:<6} {amt:,.6f}  (~{_fmt_usd(est_q)})")
        except Exception:
            lines.append(f"{asset:<6} {amt:,.6f}")

    if not lines:
        lines.append("(no balances or all zero)")

    lines.append(f"— estimated total: {_fmt_usd(total_quote)}")
    return lines


# ---------- public: MT5 account summary ----------
def mt5_summary() -> List[str]:
    """
    Connect to the running MT5 terminal (or initialize) and return a short account summary.
    ENV used:
      MTS_PATH      = full path to terminal64.exe
      MT5_LOGIN     = (optional if already logged-in terminal)
      MT5_PASSWORD  = (optional)
      MT5_SERVER    = (optional)
    """
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package not installed")

    # Initialize if not already
    path = os.getenv("MTS_PATH")  # e.g. C:\Program Files\OctaFX MetaTrader 5\terminal64.exe
    if not mt5.initialize(path=path):
        # capture last error
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.initialize failed: ({code}) {desc}")

    # Optional login if provided
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if login and password and server:
        try:
            login_ok = mt5.login(int(login), password=password, server=server)
            if not login_ok:
                code, desc = mt5.last_error()
                raise RuntimeError(f"mt5.login failed: ({code}) {desc}")
        except Exception as e:
            raise RuntimeError(f"mt5.login exception: {e}")

    info = mt5.account_info()
    if info is None:
        code, desc = mt5.last_error()
        raise RuntimeError(f"mt5.account_info failed: ({code}) {desc}")

    # Positions/PnL
    pos_list = mt5.positions_get()
    pos_count = len(pos_list) if pos_list is not None else 0
    profit = 0.0
    if pos_list:
        try:
            profit = float(sum(float(p.profit or 0) for p in pos_list))
        except Exception:
            pass

    lines = [
        f"Account: {getattr(info, 'name', '')} ({getattr(info, 'login', '')})",
        f"Balance:  {_fmt_usd(float(getattr(info, 'balance', 0.0)))}",
        f"Equity:   {_fmt_usd(float(getattr(info, 'equity', 0.0)))}",
        f"Margin:   {_fmt_usd(float(getattr(info, 'margin', 0.0)))}",
        f"Positions: {pos_count}  (unrealized PnL: {_fmt_usd(profit)})",
    ]
    return lines
