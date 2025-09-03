"""Cross-timeframe manager (CTF):

Upgraded behavior:
 - Weighted TF voting: 1h=3, 15m=2, 5m=1 (higher TFs dominate)
 - Volatility guard: skip trades when ATR/BBW indicates low activity
 - Partial-close retry: when close fails due to insufficient qty, query holdings and retry with available qty
 - Writes richer records to runtime/closed_trades.json and leaves reconciled open_trades.json
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Dict, List

from dotenv import load_dotenv
import pandas as pd


def _read(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: pathlib.Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr_bb(df: pd.DataFrame) -> dict:
    # compute ATR% and BB width
    try:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        tr = pd.concat(
            [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        ma = close.rolling(20).mean()
        sd = close.rolling(20).std(ddof=0)
        bbw = ((ma + 2 * sd) - (ma - 2 * sd)) / ma.replace(0, pd.NA)
        bbw_last = float(bbw.iloc[-1]) if len(bbw) else 0.0
        atr_pct = float(atr / (close.iloc[-1] if close.iloc[-1] else 1.0))
        return {"atr_pct": atr_pct, "bbw": bbw_last}
    except Exception:
        return {"atr_pct": 0.0, "bbw": 0.0}


def tf_signal(bars: List[List[float]]) -> str:
    try:
        df = pd.DataFrame(bars, columns=["ts", "open", "high", "low", "close", "vol"])
        fast = ema(df["close"], 20).iloc[-1]
        slow = ema(df["close"], 50).iloc[-1]
        price = float(df["close"].iloc[-1])
        if fast > slow and price > fast:
            return "buy"
        if fast < slow and price < fast:
            return "sell"
    except Exception:
        pass
    return "flat"


def _get_available_qty(router, symbol: str):
    """Robustly read available base qty from router/ex change shapes.

    Returns None when balance info cannot be determined.
    Handles:
      - ccxt-like dict with currency keys
      - ccxt-like {'total': {...}} shape (PaperBroker.fetch_balance)
      - router.ex.holdings attribute (PaperBroker.holdings)
    """
    base = symbol.split("/")[0]
    ex = getattr(router, "ex", None)
    try:
        if ex is None:
            return None
        # prefer fetch_balance if available
        if hasattr(ex, "fetch_balance"):
            bal = ex.fetch_balance() or {}
            if isinstance(bal, dict):
                # direct currency key
                if base in bal and isinstance(bal[base], dict):
                    acct = bal.get(base) or {}
                    return float(acct.get("free", acct.get("total", 0)) or 0.0)
                # 'total' mapping (PaperBroker.fetch_balance returns under 'total')
                if "total" in bal and isinstance(bal["total"], dict) and base in bal["total"]:
                    acct = bal["total"][base]
                    if isinstance(acct, dict):
                        return float(acct.get("free", acct.get("total", 0)) or 0.0)
        # fallback to holdings attribute
        if hasattr(ex, "holdings"):
            h = getattr(ex, "holdings", {}) or {}
            if base in h:
                return float(h.get(base, 0.0) or 0.0)
    except Exception:
        return None
    return None


def main():
    load_dotenv()
    from traders_core.router import ExchangeRouter

    RUNTIME = pathlib.Path("runtime")
    OPEN = RUNTIME / "open_trades.json"
    CLOSED = RUNTIME / "closed_trades.json"

    rows: List[Dict[str, Any]] = _read(OPEN, [])
    closed: List[Dict[str, Any]] = _read(CLOSED, [])
    if not rows:
        print("no open trades")
        return

    router = ExchangeRouter()

    # weights favor higher TFs
    tfs = ["5m", "15m", "1h"]
    weights = {"5m": 1, "15m": 2, "1h": 3}

    for t in list(rows):
        sym = t.get("symbol")
        side = t.get("side")
        mode = t.get("mode", "spot")
        amt = float(t.get("amount", t.get("qty", 0)))
        print(f"CTF evaluating {sym} side={side} amt={amt}")

        weighted = 0
        votes = {}
        skip = False
        for tf in tfs:
            bars = router.fetch_ohlcv(sym, tf, limit=200)
            if not bars:
                votes[tf] = 0
                continue
            vf = _atr_bb(pd.DataFrame(bars, columns=["ts","open","high","low","close","vol"]))
            # apply simple volatility guard: skip if ATR%<0.0002 and BBW<0.005 (very quiet)
            if vf.get("atr_pct", 0) < 0.0002 and vf.get("bbw", 0) < 0.005:
                print(f"  {sym} {tf}: low vol atr%={vf.get('atr_pct'):.6f} bbw={vf.get('bbw'):.6f} -> skip trade")
                skip = True
                break
            s = tf_signal(bars)
            votes[tf] = s
            weighted += s * weights.get(tf, 1)

        if skip:
            continue

        print(f"  {sym} votes: {votes} weighted_sum={weighted}")

        # decide: positive -> buy bias, negative -> sell bias
        bias = 0
        if weighted > 0:
            bias = 1
        elif weighted < 0:
            bias = -1

        # map bias to side
        disagree = (bias == 1 and side == "sell") or (bias == -1 and side == "buy")
        if disagree:
            print(f"CTF: disagreement for {sym} (side={side}), attempting close")
            close_side = "sell" if side == "buy" else "buy"
            try:
                if mode == "spot":
                    res = router.place_spot_market(sym, close_side, qty=amt)
                else:
                    res = router.place_futures_market(sym, close_side, qty=amt, close=True)
            except Exception as e:
                res = {"ok": False, "error": str(e)}

            entry = {"symbol": sym, "side_open": side, "side_close": close_side, "mode": mode, "amount": amt, "closed_at": int(time.time()), "result": res}

            # retry logic for insufficient qty
            if isinstance(res, dict) and not res.get("ok"):
                err = str(res.get("error") or "").lower()
                if "insufficient" in err:
                    avail = _get_available_qty(router, sym)
                    if avail and avail > 0:
                        retry_qty = min(avail, amt)
                        try:
                            if mode == "spot":
                                retry = router.place_spot_market(sym, close_side, qty=retry_qty)
                            else:
                                retry = router.place_futures_market(sym, close_side, qty=retry_qty, close=True)
                        except Exception as e:
                            retry = {"ok": False, "error": str(e)}
                        entry["retry_with_available"] = {"qty": retry_qty, "result": retry}
                        if isinstance(retry, dict) and retry.get("ok"):
                            try:
                                rows.remove(t)
                            except Exception:
                                pass

            # if initial close succeeded, remove from open
            if isinstance(res, dict) and res.get("ok"):
                try:
                    rows.remove(t)
                except Exception:
                    pass

            closed.append(entry)

    _write(OPEN, rows)
    _write(CLOSED, closed)
    print(f"CTF run done. remaining open: {len(rows)} closed total: {len(closed)}")


if __name__ == "__main__":
    main()
