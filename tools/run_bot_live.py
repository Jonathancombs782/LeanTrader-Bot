import json
import os
import sys

# ensure project root importable
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)


def bars_to_df(bars):
    """Convert ccxt OHLCV list to a pandas DataFrame.

    Returns an empty DataFrame with standard columns when bars is falsy.
    """
    import pandas as pd

    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "timestamp"])

    rows = []
    for r in bars:
        ts, o, h, l, c, v = r[:6]
        rows.append(
            {
                "timestamp": int(ts),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            }
        )

    return pd.DataFrame(rows)


def guess_usdt_balance(bal):
    try:
        if isinstance(bal, dict):
            if "total" in bal and isinstance(bal["total"], dict):
                usdt = bal["total"].get("USDT")
                if isinstance(usdt, dict):
                    return float(usdt.get("free") or usdt.get("total") or 0.0)
                try:
                    return float(usdt or 0.0)
                except Exception:
                    pass

            if "free" in bal and isinstance(bal["free"], dict):
                return float(bal["free"].get("USDT") or 0.0)

            fut = bal.get("futures") or {}
            if isinstance(fut, dict) and "free_cash" in fut:
                return float(fut.get("free_cash") or 0.0)
    except Exception:
        pass

    return 0.0


def main(symbol: str = None, timeframe: str = "1m", limit: int = 200):
    out = {"errors": [], "results": {}}

    try:
        from router import ExchangeRouter
        from strategy import resolve_strategy_and_params
    except Exception as e:
        out["errors"].append(f"import error: {e}")
        print(json.dumps(out, indent=2))
        return

    # safety gates
    enable_live = os.getenv("ENABLE_LIVE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    allow_live = os.getenv("ALLOW_LIVE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    if not (enable_live and allow_live):
        out["errors"].append("ENABLE_LIVE and ALLOW_LIVE must both be set to enable live orders")
        print(json.dumps(out, indent=2))
        return

    try:
        ex = ExchangeRouter()
        out["results"]["exchange_info"] = ex.info()
    except Exception as e:
        out["errors"].append(f"ExchangeRouter init failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # pick symbol
    if not symbol:
        syms = ex.spot_symbols("USDT") or list(getattr(ex, "markets", {}).keys())
        symbol = syms[0] if syms else "BTC/USDT"
    out["results"]["symbol"] = symbol

    try:
        bars = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = bars_to_df(bars)
        out["results"]["ohlcv_rows"] = len(df)
    except Exception as e:
        out["errors"].append(f"fetch_ohlcv failed: {e}")
        print(json.dumps(out, indent=2))
        return

    try:
        strat, params = resolve_strategy_and_params()
        out["results"]["strategy"] = {"class": type(strat).__name__, "params": params}
    except Exception as e:
        out["errors"].append(f"resolve_strategy_and_params failed: {e}")
        print(json.dumps(out, indent=2))
        return

    try:
        sample = df.tail(500).reset_index(drop=True)
        if sample.empty:
            out["errors"].append("no OHLCV data to run strategy")
            print(json.dumps(out, indent=2))
            return
        atr_stop_mult = float(os.getenv("ATR_STOP_MULT", "1.0"))
        atr_trail_mult = float(os.getenv("ATR_TRAIL_MULT", "0.5"))
        sig_df, info = strat.entries_and_exits(sample, atr_stop_mult=atr_stop_mult, atr_trail_mult=atr_trail_mult)
        out["results"]["strategy_info"] = info
        last = sig_df.iloc[-1].to_dict() if not sig_df.empty else {}
        out["results"]["last_row"] = last
        long_signal = bool(last.get("long_signal"))
    except Exception as e:
        out["errors"].append(f"strategy execution failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # determine order size
    try:
        live_amount = os.getenv("LIVE_ORDER_AMOUNT")
        if live_amount:
            amount = float(live_amount)
        else:
            bal = ex.safe_fetch_balance()
            usdt_free = guess_usdt_balance(bal)
            out["results"]["usdt_free_estimate"] = usdt_free
            usd_target = float(os.getenv("LIVE_ORDER_USD", "10.0"))
            price = float(last.get("close") or (df["close"].iloc[-1] if not df.empty else 0.0) or 0.0)
            amount = (usd_target / price) if price > 0 else 0.0
        max_order = os.getenv("MAX_ORDER_SIZE")
        if max_order:
            try:
                max_order_f = float(max_order)
                if amount > max_order_f:
                    out["results"]["order_rejected"] = f"computed amount {amount} > MAX_ORDER_SIZE {max_order_f}"
                    print(json.dumps(out, indent=2))
                    return
            except Exception:
                pass
    except Exception as e:
        out["errors"].append(f"failed to compute order amount: {e}")
        print(json.dumps(out, indent=2))
        return

    # place order only if signal exists
    try:
        if long_signal and amount > 0:
            res = ex.safe_place_order(symbol, "buy", amount, price=None, params={})
            out["results"]["placed_order"] = res
        else:
            out["results"]["placed_order"] = {
                "ok": False,
                "note": "no long signal or zero amount",
            }
    except Exception as e:
        out["errors"].append(f"order placement error: {e}")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
