import json
import os  # noqa: F401  # intentionally kept
import traceback

os.environ["EXCHANGE_ID"] = os.environ.get("EXCHANGE_ID", "paper")
os.environ["ENABLE_LIVE"] = "false"

os.makedirs("runtime", exist_ok=True)

error_info = None
try:
    from router import ExchangeRouter
    from ultra_core import UltraCore

    r = ExchangeRouter()
    print("Router markets count=", len(getattr(r, "markets", {})))
    try:
        from universe import Universe

        u = Universe(r) if hasattr(r, "markets") else None
    except Exception:
        u = None
    ultra = UltraCore(r, u)

    scan = ultra.scan_markets()
    with open("runtime/ultra_scan.json", "w", encoding="utf-8") as fh:
        json.dump(scan, fh, indent=2, default=str)
    ops = ultra.scout_opportunities(scan)
    with open("runtime/ultra_ops.json", "w", encoding="utf-8") as fh:
        json.dump(ops, fh, indent=2, default=str)
    plans = ultra.plan_trades(ops)
    with open("runtime/ultra_plans.json", "w", encoding="utf-8") as fh:
        json.dump(plans, fh, indent=2, default=str)
    print("WROTE ultra debug files")
except Exception as e:
    error_info = traceback.format_exc()
    print("ULTRA_DEBUG_ERROR", e)
    try:
        with open("runtime/ultra_debug_error.txt", "w", encoding="utf-8") as fh:
            fh.write(error_info)
    except Exception:
        pass
    # ensure files exist even on error (helpful for CI/commands expecting files)
    try:
        if not os.path.exists("runtime/ultra_scan.json"):
            with open("runtime/ultra_scan.json", "w", encoding="utf-8") as fh:
                json.dump({}, fh)
        if not os.path.exists("runtime/ultra_ops.json"):
            with open("runtime/ultra_ops.json", "w", encoding="utf-8") as fh:
                json.dump([], fh)
        if not os.path.exists("runtime/ultra_plans.json"):
            with open("runtime/ultra_plans.json", "w", encoding="utf-8") as fh:
                json.dump([], fh)
    except Exception:
        pass
