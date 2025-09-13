import pandas as pd

from ..backtest.engine import backtest
from ..config import CFG
from ..features.microstructure import engineer
from ..policy.house_smc import run as run_house


def run_demo(frames):
    eng = {k: engineer(v) for k, v in frames.items()}
    sigs = run_house(eng)
    eq = backtest(eng["M15"], sigs, CFG.risk)
    return sigs, eq
