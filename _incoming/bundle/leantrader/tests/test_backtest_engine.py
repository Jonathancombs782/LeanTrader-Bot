import pandas as pd

from leantrader.backtest.engine import backtest


def test_backtest_runs():
    idx = pd.date_range("2024-01-01", periods=200, freq="15T")
    df = pd.DataFrame({"open": 1.10, "high": 1.12, "low": 1.08, "close": 1.11}, index=idx)
    sig = pd.DataFrame({"signal": "x", "side": "long", "go": 1}, index=idx)
    eq = backtest(df, sig, risk_cfg=None)
    assert len(eq) > 0
