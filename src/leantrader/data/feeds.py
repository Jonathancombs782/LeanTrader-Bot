import pandas as pd

try:
    import ccxt
except Exception:
    ccxt = None


def get_ohlc_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"], index_col="time")
    return df[["open", "high", "low", "close"]].sort_index()


def get_ohlc_ccxt(exchange: str, symbol: str, timeframe: str = "15m", limit: int = 1000) -> pd.DataFrame:
    assert ccxt is not None, "ccxt not installed"
    ex = getattr(ccxt, exchange)()
    ex.load_markets()
    bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)
    return df[["open", "high", "low", "close"]].sort_index()


def resample_frames(df: pd.DataFrame) -> dict:
    # build aligned frames on M15 index
    m15 = df
    h1 = m15.resample("60T").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    h4 = m15.resample("240T").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d1 = m15.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    # forward align to m15 index
    frames = {
        "M15": m15,
        "H1": h1.reindex(m15.index, method="ffill"),
        "H4": h4.reindex(m15.index, method="ffill"),
        "D1": d1.reindex(m15.index, method="ffill"),
    }
    return frames
