modules = [
    "traders_core.router",
    "execution_adv",
    "trade_planner",
    "crypto_trader",
    "traders_core.connectors.crypto_ccxt",
    "order_utils",
    "run_live",
    "bybit_adapter",
    "bybit_smoke",
]
import sys
from pathlib import Path

# Add repo root to sys.path dynamically
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for m in modules:
    try:
        __import__(m)
        print("IMPORT OK:", m)
    except Exception as e:
        print("IMPORT FAIL:", m, type(e).__name__, e)
