import os, sys, json, traceback

# ensure project root is importable
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

# force paper broker mode for safe dry-run
os.environ.setdefault("EXCHANGE_ID", "paper")
os.environ.setdefault("PAPER_START_CASH", "10000")
os.environ.setdefault("ENABLE_LIVE", "false")

def run():
    out = {"errors": [], "results": {}}
    try:
        from router import ExchangeRouter
    except Exception as e:
        out["errors"].append(f"import ExchangeRouter failed: {e}")
        print(json.dumps(out, indent=2))
        return

    try:
        ex = ExchangeRouter()
        out["results"]["info"] = ex.info()
    except Exception as e:
        out["errors"].append(f"instantiating ExchangeRouter failed: {e}")
        out["errors"].append(traceback.format_exc())
        print(json.dumps(out, indent=2))
        return

    # sample symbol to exercise fetch_ohlcv fallback/synth
    sym = "BTC/USDT"
    try:
        bars = ex.fetch_ohlcv(sym, timeframe="1m", limit=5)
        out["results"]["fetch_ohlcv_sample"] = bars[:3]
    except Exception as e:
        out["errors"].append(f"fetch_ohlcv failed: {e}")

    try:
        # safe dry-run order
        order = ex.safe_place_order(sym, "buy", 0.001, price=None)
        out["results"]["safe_place_order"] = order
    except Exception as e:
        out["errors"].append(f"safe_place_order failed: {e}")

    try:
        bal = ex.safe_fetch_balance()
        out["results"]["balance_snapshot"] = bal
    except Exception as e:
        out["errors"].append(f"safe_fetch_balance failed: {e}")

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    run()
