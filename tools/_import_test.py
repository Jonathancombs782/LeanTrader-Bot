# quick import test for trader_core and risk_guard
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
print("sys.path[0]=", sys.path[0])
try:
    import risk_guard

    print("risk_guard has RiskConfig:", hasattr(risk_guard, "RiskConfig"))
    import trader_core

    print("trader_core imported, TraderCore exists:", hasattr(trader_core, "TraderCore"))
except Exception as e:
    import traceback

    traceback.print_exc()
    print("ERR", e)
