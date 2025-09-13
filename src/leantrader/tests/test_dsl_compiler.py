import pandas as pd

from leantrader.dsl.compiler import compile_strategy, load_strategy


def test_compile_strategy():
    spec = load_strategy("src/leantrader/dsl/examples/smc_trend_breakout.yaml")
    fn = compile_strategy(spec)
    idx = pd.date_range("2024-01-01", periods=100, freq="15T")
    df = pd.DataFrame({"open": 1.1, "high": 1.12, "low": 1.08, "close": 1.11}, index=idx)
    df["adx_14"] = 20
    df["rsi_14"] = 50
    df["fvg_score"] = 1
    df["ms_state"] = "bull"
    df["rsi_div"] = 1
    frames = {"M15": df, "H1": df, "H4": df, "D1": df}
    out = fn(frames)
    assert "go" in out.columns
