try:
    import importlib

    mod = importlib.import_module("mt5_adapter")
    min_stop_distance_points = getattr(mod, "min_stop_distance_points", None)
    print("import succeeded, callable:", callable(min_stop_distance_points))
    if callable(min_stop_distance_points):
        print(min_stop_distance_points.__name__)
    else:
        print("min_stop_distance_points is not callable or missing")
except Exception:
    import traceback

    traceback.print_exc()
