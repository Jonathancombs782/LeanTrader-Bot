import json
import os  # noqa: F401  # intentionally kept
import sys

# ensure project root importable
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

# Force safe paper mode
os.environ.setdefault("EXCHANGE_ID", "paper")
os.environ.setdefault("ENABLE_LIVE", "false")
os.environ.setdefault("ALLOW_LIVE", "false")


def bars_to_df(bars):
    # bars: list of [ts, o, h, l, c, v]
    import pandas as pd

    if not bars:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "timestamp"]
        )
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
    df = pd.DataFrame(rows)
    # keep time order if needed
    return df


def run_once(symbol=None, timeframe="1m", limit=200):
    out = {"errors": [], "results": {}}
    try:
        from router import ExchangeRouter
        from strategy import (get_strategy,  # noqa: F401  # intentionally kept
                              resolve_strategy_and_params)
    except Exception as e:
        out["errors"].append(f"import error: {e}")
        print(json.dumps(out, indent=2))
        return

    try:
        ex = ExchangeRouter()
        out["results"]["exchange_info"] = ex.info()
    except Exception as e:
        out["errors"].append(f"ExchangeRouter init failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # pick a symbol if not provided
    if not symbol:
        syms = ex.spot_symbols("USDT") or list(ex.markets.keys())
        symbol = syms[0] if syms else "BTC/USDT"
    out["results"]["symbol"] = symbol

    # fetch OHLCV
    try:
        bars = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = bars_to_df(bars)
        out["results"]["ohlcv_rows"] = len(df)
    except Exception as e:
        out["errors"].append(f"fetch_ohlcv failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # resolve strategy
    try:
        strat, params = resolve_strategy_and_params()
        out["results"]["strategy"] = {"class": type(strat).__name__, "params": params}
    except Exception as e:
        out["errors"].append(f"resolve_strategy_and_params failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # run strategy single cycle (use last N rows as input)
    try:
        # keep last 500 rows if available
        sample = df.tail(500).reset_index(drop=True)
        if sample.empty:
            out["errors"].append("no OHLCV data to run strategy")
            print(json.dumps(out, indent=2))
            return
        # default ATR multipliers (adjust as needed)
        atr_stop_mult = float(os.getenv("ATR_STOP_MULT", "1.0"))
        atr_trail_mult = float(os.getenv("ATR_TRAIL_MULT", "0.5"))
        sig_df, info = strat.entries_and_exits(
            sample, atr_stop_mult=atr_stop_mult, atr_trail_mult=atr_trail_mult
        )
        out["results"]["strategy_info"] = info
        # examine last signal
        last = sig_df.iloc[-1].to_dict() if not sig_df.empty else {}
        out["results"]["last_row"] = last
        long_signal = bool(last.get("long_signal"))
    except Exception as e:
        out["errors"].append(f"strategy execution failed: {e}")
        print(json.dumps(out, indent=2))
        return

    # compute a tiny order amount (paper)
    try:
        # safe tiny default; you can compute based on balance and price
        amount = float(os.getenv("PAPER_ORDER_AMOUNT", "0.001"))
        if long_signal:
            order = ex.safe_place_order(symbol, "buy", amount, price=None, params={})
            out["results"]["attempted_order"] = order
        else:
            out["results"]["attempted_order"] = {"ok": False, "note": "no long signal"}
    except Exception as e:
        out["errors"].append(f"order attempt failed: {e}")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    run_once()
