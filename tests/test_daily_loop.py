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


# -- Nov 9, 2026 ledger fix: one mark snapshot per run --------------------
# The Nov 3 plan said $89,422.15 (SOL $93.47) while a later status snapshot
# said $89,413.83 (SOL $93.43): two snapshots seven seconds apart. The
# evening loop must record its equity row from the same snapshot the plans
# used, and must load every mark before gating any signal (the old
# per-asset update rejected SOL every night with "GOOG (missing mark)").


def test_run_loop_snapshot_matches_plan_equity(tmp_path, monkeypatch):
    import pytest

    from paper import daily_loop as loop_mod
    from paper.engine import PaperEngine
    from paper.ledger import Ledger
    from paper.signals import Signal, SignalSide

    ledger_path = str(tmp_path / "ledger")
    eng = PaperEngine(ledger=Ledger(ledger_path))
    eng.update_prices({"SOL": 130.0, "GOOG": 350.0})
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "sol trend")).accepted
    assert eng.submit_signal(
        Signal("GOOG", SignalSide.LONG, 350, 340, 370, "goog trend")).accepted

    def fake_prices(symbols=None, universe=None, cache_dir="paper/cache",
                    evidence_dir="paper/evidence", with_marks=False):
        from paper.receipts import utcnow_iso
        # received_at must be fresh: mark staleness is judged on it
        # (MAX_MARK_AGE_S = 36h), so a hardcoded Nov 9 timestamp ages
        # past the fail-closed window and the snapshot goes indeterminate.
        # source_observed_at is the provider's own time and may stay old.
        marks = {
            "SOL": {"source_observed_at": "2026-11-09T22:56:23+00:00",
                    "received_at": utcnow_iso()},
        }
        return ({"SOL": 130.0}, marks, None)

    def fake_bars(symbol, universe=None, **kw):
        return ([Bar(date="2026-11-09", open=350.0, high=351.0, low=349.0,
                     close=350.0)], None)

    monkeypatch.setattr(loop_mod.feeds, "fetch_prices", fake_prices)
    monkeypatch.setattr(loop_mod.history, "fetch_daily_bars", fake_bars)
    # no trend either night: the point is the snapshot, not the signals
    monkeypatch.setattr(loop_mod.strategy, "generate_signal",
                        lambda *a, **k: None)

    summary = loop_mod.run_loop(ledger_path=ledger_path,
                                plans_dir=str(tmp_path / "plans"),
                                cache_dir=str(tmp_path / "cache"),
                                evidence_dir=str(tmp_path / "evidence"))
    rows = Ledger(ledger_path).read("equity")
    assert len(rows) == 1
    assert rows[0]["equity"] == pytest.approx(summary["equity"])
    assert rows[0]["legitimacy"] == "legit"
    assert rows[0]["mark_state"] == "ok"
    assert rows[0]["marks"]["SOL"]["price"] == pytest.approx(130.0)
    assert rows[0]["marks"]["GOOG"]["price"] == pytest.approx(350.0)
    assert summary["snapshot"] == "recorded"
    # the plan file is dated by run day; find whichever file was written
    plan_files = list((tmp_path / "plans").glob("*.md"))
    assert len(plan_files) == 1
    assert "Equity snapshot: recorded." in plan_files[0].read_text()
