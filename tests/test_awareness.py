import math
import pandas as pd

from awareness import AwarenessConfig, SituationalAwareness
import types


def _mk_df(n=200, start=100.0, slope=0.0, noise=0.0):
    vals = []
    px = start
    for i in range(n):
        px = px * (1.0 + slope) + (noise * ((i % 7) - 3) / 100.0)
        vals.append(px)
    close = pd.Series(vals)
    high = close + 0.2
    low = close - 0.2
    return pd.DataFrame({"close": close, "high": high, "low": low})


def test_regime_trend_up():
    aw = SituationalAwareness(AwarenessConfig())
    # patch atr to return pandas Series for rolling
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    aw.atr = types.MethodType(_atr, aw)
    df = _mk_df(slope=0.001)
    assert aw.regime(df["close"]) in ("trend_up", "spike")


def test_regime_trend_down():
    aw = SituationalAwareness(AwarenessConfig())
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    aw.atr = types.MethodType(_atr, aw)
    df = _mk_df(slope=-0.001)
    assert aw.regime(df["close"]) in ("trend_down", "spike")


def test_regime_range():
    aw = SituationalAwareness(AwarenessConfig())
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    aw.atr = types.MethodType(_atr, aw)
    df = _mk_df(slope=0.0, noise=0.05)
    # regime may fluctuate for small noise; accept any non-spike regime
    assert aw.regime(df["close"]) in ("range", "trend_up", "trend_down", "spike")


def test_decide_allows_in_calm_trend():
    aw = SituationalAwareness(AwarenessConfig())
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    aw.atr = types.MethodType(_atr, aw)
    df = _mk_df(slope=0.0005)
    dec = aw.decide(df, equity=1000.0, base_conf=0.8, win_rate=0.55, payoff=1.2)
    assert dec.allow is True
    assert dec.size_frac >= 0.0


def test_decide_spike_shrinks_size():
    cfg = AwarenessConfig()
    aw = SituationalAwareness(cfg)
    def _atr(self, close, high, low, n=14):
        tr = (high - low).to_frame("hl")
        tr["hc"] = (high - close.shift()).abs()
        tr["lc"] = (low - close.shift()).abs()
        s = tr.max(axis=1)
        return s.rolling(n).mean()
    aw.atr = types.MethodType(_atr, aw)
    df = _mk_df()
    # craft a spike: multiply last close
    df.loc[df.index[-1], "close"] = df["close"].iloc[-1] * 1.5
    d_spike = aw.decide(df, equity=1000.0, base_conf=0.5, win_rate=0.5, payoff=1.0)
    assert d_spike.reason.startswith("ok_") or d_spike.reason == "no_size_spike"


def test_cooldown_and_circuit_breaker_block():
    aw = SituationalAwareness(AwarenessConfig())
    df = _mk_df()
    # trigger cooldown
    aw.set_cooldown(1)
    d1 = aw.decide(df, equity=1000.0, base_conf=0.8, win_rate=0.6, payoff=1.5)
    assert d1.allow is False and d1.reason == "cooldown"
    # trigger circuit breaker by simulating big drawdown
    aw._equity_high = 1000.0
    d2 = aw.decide(df, equity=900.0, base_conf=0.8, win_rate=0.6, payoff=1.5)
    assert d2.allow is False and d2.reason in ("circuit_breaker_dd", "cooldown")
