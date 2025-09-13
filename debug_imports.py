import importlib
import inspect
import os
import traceback

print("CWD=", os.getcwd())
try:
    m = importlib.import_module("mt5_adapter")
    print("module file:", getattr(m, "__file__", None))
    print("attrs snapshot:", sorted([n for n in dir(m) if n.startswith(("min_stop", "order_send", "symbol_trade"))]))
    if hasattr(m, "min_stop_distance_points"):
        print("min_stop_distance_points source:")
        print(inspect.getsource(m.min_stop_distance_points))
    if hasattr(m, "order_send_market"):
        print("order_send_market source:")
        print(inspect.getsource(m.order_send_market))
    if hasattr(m, "symbol_trade_specs"):
        print("symbol_trade_specs source:")
        print(inspect.getsource(m.symbol_trade_specs))
except Exception:
    traceback.print_exc()
