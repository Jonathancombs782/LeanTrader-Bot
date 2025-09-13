"""Import-smoke runner used by GitHub Actions and locally.
Exits non-zero when any import fails.
"""

import importlib
import sys

candidates = [
    "router",
    "trader_core",
    "risk_guard",
    "mt5_adapter",
    "mt5_signals",
    "bybit_adapter",
    "paper_broker",
    "tools.web_crawler",
]

fails = []
for n in candidates:
    try:
        importlib.import_module(n)
        print(f"IMPORT OK: {n}")
    except Exception as e:
        print(f"IMPORT FAIL: {n} -> {e}")
        fails.append((n, str(e)))

if fails:
    print("\nImport smoke found failures:")
    for f, e in fails:
        print(f, e)
    sys.exit(1)

print("\nImport smoke passed")
