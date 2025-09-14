import pandas as pd
import numpy as np

from strategies.pipeline import daily_rebalance_job


def _make_sample_df(n=200, cols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "BNBUSDT")):
    rng = np.random.default_rng(0)
    prices = {}
    for i, c in enumerate(cols):
        # random walk with slight drift
        steps = rng.normal(loc=0.0005 - 0.0002 * (i % 3), scale=0.01, size=n)
        series = 100 * np.cumprod(1.0 + steps)
        prices[c] = series
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=n, freq="1min")
    return pd.DataFrame(prices, index=idx)


def main():
    df = _make_sample_df()
    res = daily_rebalance_job(df)
    print("rebalance result:", res)


if __name__ == "__main__":
    main()

