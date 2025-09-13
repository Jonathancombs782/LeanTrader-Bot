import importlib
import sys

sys.path.insert(0, r"c:\Users\User\Downloads\LeanTrader_ForexPack")
try:
    m = importlib.import_module("mt5_adapter")
    print("\n".join(sorted(n for n in dir(m) if not n.startswith("_"))))
except Exception as e:
    print("IMPORT-ERROR:", e)
    raise
