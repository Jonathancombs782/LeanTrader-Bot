"""Tests for paper.strategy (trend_v1) and paper.history.Bar."""
from paper.history import Bar
from paper.strategy import avg_daily_range, generate_signal, sma


def _bars(n, start, step):
    # steadily rising closes => clean uptrend
    return [Bar(date=f"2026-01-{i+1:02d}", open=start + i * step,
                high=start + i * step + 1, low=start + i * step - 1,
                close=start + i * step) for i in range(n)]


def test_sma():
    assert sma([1, 2, 3, 4], 4) == 2.5
    assert sma([1, 2, 3], 4) is None


def test_long_signal_uptrend():
    bars = _bars(60, 100.0, 0.5)  # 100 -> ~130, strong uptrend
    sig = generate_signal("SOL", bars, bars[-1].close, (), crypto_closes_only=False)
    assert sig is not None
    assert sig.side.value == "long"
    assert sig.stop < sig.entry < sig.target
    # 2:1 reward-to-risk by construction
    assert abs((sig.target - sig.entry) / (sig.entry - sig.stop) - 2.0) < 1e-9
    assert "uptrend" in sig.thesis


def test_flat_when_no_trend():
    # oscillate around a flat line: SMAs stay tangled
    bars = [Bar(date=f"2026-01-{i+1:02d}", open=100, high=101, low=99,
                close=100 + (1 if i % 2 else -1)) for i in range(60)]
    assert generate_signal("GOOG", bars, 100.0, (), crypto_closes_only=False) is None


def test_short_signal_downtrend():
    bars = _bars(60, 200.0, -0.5)  # 200 -> ~170, steady decline
    sig = generate_signal("SOL", bars, bars[-1].close, (), crypto_closes_only=True)
    assert sig is not None
    assert sig.side.value == "short"
    assert sig.target < sig.entry < sig.stop


def test_avg_daily_range_crypto_vs_stock():
    bars = _bars(20, 100.0, 2.0)
    # stock: true high-low range = 2.0 every day
    assert abs(avg_daily_range(bars, crypto_closes_only=False) - 2.0) < 1e-9
    # crypto: close-to-close move = 2.0 every day
    assert abs(avg_daily_range(bars, crypto_closes_only=True) - 2.0) < 1e-9


def test_insufficient_history_returns_none():
    bars = _bars(10, 100.0, 0.5)
    assert generate_signal("SOL", bars, 105.0, (), crypto_closes_only=True) is None
