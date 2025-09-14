"""Quick import smoke test to detect modules that fail on import.

Runable from the repo root or from the tools/ directory; this script will
ensure the repository root is on sys.path before importing modules.

Usage:
    python tools/import_smoke.py
"""

import importlib
import sys
from pathlib import Path

# Ensure repository root (parent of tools/) is on sys.path so imports like
# `import router` resolve when the script is executed as `python tools/import_smoke.py`.
repo_root = Path(__file__).resolve().parent.parent
repo_root_str = str(repo_root)
if sys.path[0] != repo_root_str:
    # insert at position 0 so imports prefer repo root
    sys.path.insert(0, repo_root_str)

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

print(f"[import_smoke] sys.path[0]={sys.path[0]}")

for name in candidates:
    try:
        m = importlib.import_module(name)
        print(f"[import_smoke] IMPORT OK: {name} -> module={getattr(m, '__file__', None)}")
    except Exception as e:
        print(f"[import_smoke] IMPORT FAIL: {name} -> {type(e).__name__}: {e}")

print("[import_smoke] Done")
