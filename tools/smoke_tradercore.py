import sys

sys.path.append(r"c:\Users\User\Downloads\LeanTrader_ForexPack")
from trader_core import TraderCore

# instantiate with empty lists
tc = TraderCore([], [], [], [], [], [])
print("TraderCore instantiated; mt5:", bool(tc.mt5))
