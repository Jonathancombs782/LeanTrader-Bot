import sys

sys.path.insert(0, r"c:\Users\User\Downloads\LeanTrader_ForexPack\src")
try:
    import importlib

    m = importlib.import_module("leantrader")
    print("leantrader imported:", getattr(m, "__version__", "no __version__"))
    app_mod = importlib.import_module("leantrader.api.app")
    print("leantrader.api.app imported, has symbols:", [a for a in dir(app_mod) if not a.startswith("_")][:50])
    print("app symbol present?", hasattr(app_mod, "app"))
except Exception as e:
    print("IMPORT ERROR:", type(e).__name__, str(e))
