import importlib
import traceback

print("CWD=", __import__("os").getcwd())
try:
    m = importlib.import_module("mt5_signals")
    print("mt5_signals imported ok")
except Exception:
    traceback.print_exc()
try:
    import mt5_adapter

    attrs = sorted(
        [
            a
            for a in dir(mt5_adapter)
            if a.startswith("min_stop")
            or a.startswith("bars_df")
            or a.startswith("ensure_symbol")
            or a.startswith("order_send")
            or a.startswith("symbol_trade")
        ]
    )
    print("mt5_adapter file=", getattr(mt5_adapter, "__file__", None))
    print("attrs snapshot=", attrs)
    import inspect

    if hasattr(mt5_adapter, "min_stop_distance_points"):
        print("min_stop source:")
        print(inspect.getsource(mt5_adapter.min_stop_distance_points))
except Exception:
    traceback.print_exc()
