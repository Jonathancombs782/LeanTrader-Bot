"""Replay hardening tests (B3). Network-free.

Malformed records fail closed with ReplayError (a named diagnostic, not a
bare KeyError); duplicate signal_ids, duplicate positions, and orphan
fills/closes are flagged in engine.replay_diagnostics and skipped —
never silently overwritten or swallowed.
"""
import json

import pytest

from paper.engine import PaperEngine, ReplayError, replay_ledger
from paper.ledger import Ledger


def _ledger(tmp_path) -> Ledger:
    return Ledger(tmp_path / "ledger")


def _accepted_signal(signal_id: str, symbol: str = "SOL", entry: float = 130.0,
                     stop: float = 120.0, target: float = 150.0) -> dict:
    return {
        "signal_id": signal_id, "symbol": symbol, "side": "long",
        "entry": entry, "stop": stop, "target": target, "thesis": "t",
        "disposition": "accepted",
    }


def _fill(signal_id: str, symbol: str = "SOL", quantity: float = 10.0,
          fill_price: float = 130.05, notional: float = 1300.5,
          fee: float = 1.3005, **extra) -> dict:
    rec = {
        "signal_id": signal_id, "symbol": symbol, "side": "long",
        "quantity": quantity, "mid_price": 130.0, "fill_price": fill_price,
        "notional": notional, "fee": fee, "slippage_bps": 5,
        "risk_amount": 100.0, "legitimacy": "legit",
        "at": "2026-11-10T00:00:00+00:00",
    }
    rec.update(extra)
    return rec


def _kinds(engine) -> list[str]:
    return [d["kind"] for d in engine.replay_diagnostics]


# -- (a) malformed records raise ReplayError, not bare KeyError -----------
def test_malformed_close_missing_field_raises(tmp_path):
    ledger = _ledger(tmp_path)
    rec = {"event": "close", "symbol": "SOL", "quantity": 10.0, "fee": 1.4}
    ledger.append("fills", rec)  # no exit_price; logged_at added by append
    with pytest.raises(ReplayError, match="exit_price"):
        replay_ledger(ledger)


def test_malformed_close_missing_logged_at_raises(tmp_path):
    # logged_at is added by Ledger.append, so a record without it can only
    # arrive from a hand-edited file — write the raw line to prove the
    # guard runs before _fill_key reads it.
    root = tmp_path / "ledger"
    root.mkdir()
    (root / "fills.ndjson").write_text(json.dumps({
        "event": "close", "symbol": "SOL", "exit_price": 140.0, "fee": 1.4,
    }) + "\n")
    with pytest.raises(ReplayError, match="logged_at"):
        replay_ledger(_ledger(tmp_path))


def test_malformed_fill_bad_number_raises(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("signals", _accepted_signal("sig-1"))
    ledger.append("fills", _fill("sig-1", quantity="not-a-number"))
    with pytest.raises(ReplayError, match="quantity"):
        replay_ledger(ledger)


def test_malformed_fill_invalid_side_raises(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("signals", _accepted_signal("sig-1"))
    ledger.append("fills", _fill("sig-1", side="sideways"))
    with pytest.raises(ReplayError, match="side"):
        replay_ledger(ledger)


def test_malformed_fill_unknown_event_raises(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("fills", {"event": "adjust", "symbol": "SOL"})
    with pytest.raises(ReplayError, match="unknown event"):
        replay_ledger(ledger)


# -- (b) duplicates are flagged, never overwritten ------------------------
def test_duplicate_signal_id_flagged_not_double_applied(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("signals", _accepted_signal("sig-1"))
    ledger.append("fills", _fill("sig-1"))
    ledger.append("fills", _fill("sig-1"))  # same signal_id, second copy
    eng = replay_ledger(ledger)
    assert list(eng.portfolio.positions) == ["SOL"]
    assert eng.portfolio.positions["SOL"].quantity == pytest.approx(10.0)
    # cash debited once, not twice
    assert eng.portfolio.cash == pytest.approx(100_000 - 1300.5 - 1.3005)
    assert _kinds(eng) == ["duplicate_fill"]


def test_second_fill_same_symbol_flagged_not_overwritten(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("signals", _accepted_signal("sig-1"))
    ledger.append("signals", _accepted_signal("sig-2", entry=132.0,
                                              stop=122.0, target=152.0))
    ledger.append("fills", _fill("sig-1"))
    ledger.append("fills", _fill("sig-2", quantity=5.0, fill_price=132.05,
                                 notional=660.25, fee=0.66025))
    eng = replay_ledger(ledger)
    # the first position stands; the second fill never overwrote it and
    # its cash debit never happened (the Nov 4, 2026 SOL pattern)
    assert list(eng.portfolio.positions) == ["SOL"]
    assert eng.portfolio.positions["SOL"].quantity == pytest.approx(10.0)
    assert eng.portfolio.cash == pytest.approx(100_000 - 1300.5 - 1.3005)
    assert _kinds(eng) == ["duplicate_position"]


# -- (c) orphan fills/closes are surfaced ---------------------------------
def test_orphan_fill_flagged_and_skipped(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("fills", _fill("no-such-signal"))
    eng = replay_ledger(ledger)
    assert eng.portfolio.positions == {}
    assert eng.portfolio.cash == pytest.approx(100_000)
    assert _kinds(eng) == ["orphan_fill"]
    assert eng.replay_diagnostics[0]["signal_id"] == "no-such-signal"


def test_orphan_close_flagged_not_crash(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("fills", {
        "event": "close", "symbol": "SOL", "exit_price": 140.0,
        "quantity": 10.0, "fee": 1.4, "slippage_bps": 5,
        "realized_pnl": 100.0, "at": "2026-11-10T00:00:00+00:00",
    })
    eng = replay_ledger(ledger)  # must not raise
    assert eng.portfolio.positions == {}
    assert _kinds(eng) == ["orphan_close"]


# -- refresh re-reads stay silent; clean replays stay clean ---------------
def test_refresh_reread_does_not_flag_duplicates(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.append("signals", _accepted_signal("sig-1"))
    ledger.append("fills", _fill("sig-1"))
    ledger.append("fills", _fill("sig-1"))  # duplicate line in the file
    eng = PaperEngine(ledger=ledger)
    assert eng.refresh_from_ledger() == 1
    assert _kinds(eng) == ["duplicate_fill"]
    # second refresh re-reads the same lines: the applied set silences
    # them, and the diagnostic is not repeated
    assert eng.refresh_from_ledger() == 0
    assert _kinds(eng) == ["duplicate_fill"]


def test_clean_replay_has_no_diagnostics(tmp_path):
    eng = PaperEngine(ledger=_ledger(tmp_path))
    eng.update_prices({"SOL": 130.0})
    from paper.signals import Signal, SignalSide
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "t")).accepted
    replayed = replay_ledger(_ledger(tmp_path))
    assert replayed.replay_diagnostics == []
    assert list(replayed.portfolio.positions) == ["SOL"]
