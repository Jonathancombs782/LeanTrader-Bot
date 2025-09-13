import sys

sys.path.append(r"c:\Users\User\Downloads\LeanTrader_ForexPack")
from tools.continuous_demo import main  # noqa: E402

# run for 0.1 minutes (~6 seconds)
main(0.1)
