import sys

sys.path.insert(0, ".")
try:
    import risk_guard
    import trader_core

    print("trader_core ok:", hasattr(trader_core, "TraderCore"))
    print("risk_guard ok:", hasattr(risk_guard, "RiskConfig"))
except Exception as e:
    import traceback

    traceback.print_exc()
    print("ERR", e)
