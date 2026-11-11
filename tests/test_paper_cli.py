"""CLI tests. Network-free: feeds and history are monkeypatched."""
import json
from types import SimpleNamespace

import pytest

from paper import cli as cli_mod
from paper.engine import PaperEngine
from paper.ledger import Ledger
from paper.signals import Signal, SignalSide


class _Bar:
    def __init__(self, close: float):
        self.close = close


def _engine_with_sol_goog(tmp_path) -> PaperEngine:
    eng = PaperEngine(ledger=Ledger(tmp_path / "ledger"))
    eng.update_prices({"SOL": 130.0, "GOOG": 350.0})
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "sol trend")).accepted
    assert eng.submit_signal(
        Signal("GOOG", SignalSide.LONG, 350, 340, 370, "goog trend")).accepted
    return eng


def _status_args(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(ledger=str(tmp_path / "ledger"),
                           cache="cache", evidence="evidence")


def _engine_with_sol_goog_rolled_to(tmp_path, day: str) -> PaperEngine:
    """Engine with SOL+GOOG positions whose last recorded day_roll is `day`
    (a past date), so the next command runs on a new day."""
    eng = _engine_with_sol_goog(tmp_path)
    assert eng.roll_day_if_new(today=day)
    return eng


def test_status_appends_nothing_on_a_new_day(tmp_path, monkeypatch, capsys):
    # The ledger's last roll is a past day: before B2, the first status run
    # of the new day appended a day_roll (or day_roll_refused) event.
    _engine_with_sol_goog_rolled_to(tmp_path, "2026-09-29")
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 130.0}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda symbol, *a, **k: ([_Bar(350.0)], None))

    assert cli_mod.cmd_status(_status_args(tmp_path)) == 0
    capsys.readouterr()
    ledger = Ledger(tmp_path / "ledger")
    assert ledger.read("equity") == []
    assert ledger.read("risk_events") == [
        e for e in ledger.read("risk_events")
        if e.get("event") == "day_roll"
        and e.get("trading_day") == "2026-09-29"
    ], "status must append no event of any kind"


def test_roll_command_advances_baseline_once(tmp_path, monkeypatch, capsys):
    _engine_with_sol_goog_rolled_to(tmp_path, "2026-09-29")
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 130.0}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda symbol, *a, **k: ([_Bar(350.0)], None))

    assert cli_mod.cmd_roll(_status_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "rolled to" in out
    ledger = Ledger(tmp_path / "ledger")
    rolls = [e for e in ledger.read("risk_events")
             if e.get("event") == "day_roll"]
    assert len(rolls) == 2  # yesterday's setup roll + today's roll
    # Second roll is a no-op: the baseline is already today's.
    assert cli_mod.cmd_roll(_status_args(tmp_path)) == 0
    assert "already on" in capsys.readouterr().out
    assert len([e for e in ledger.read("risk_events")
                if e.get("event") == "day_roll"]) == 2


def test_roll_command_refuses_on_indeterminate_marks(
        tmp_path, monkeypatch, capsys):
    _engine_with_sol_goog_rolled_to(tmp_path, "2026-09-29")
    # No marks at all: the baseline would be computed from an incomplete
    # mark set, so the roll must refuse instead of recording a bad baseline.
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda *a, **k: ([], None))

    assert cli_mod.cmd_roll(_status_args(tmp_path)) == 1
    assert "refused" in capsys.readouterr().out
    ledger = Ledger(tmp_path / "ledger")
    refused = [e for e in ledger.read("risk_events")
               if e.get("event") == "day_roll_refused"]
    assert len(refused) == 1
    assert len([e for e in ledger.read("risk_events")
                if e.get("event") == "day_roll"]) == 1


def test_current_marks_includes_stocks(monkeypatch):
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 107.0}, None))

    def fake_bars(symbol, universe=None, **kw):
        assert symbol == "GOOG"
        return ([_Bar(349.52)], None)

    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars", fake_bars)
    assert cli_mod._current_marks("cache", "evidence") == {
        "SOL": 107.0, "GOOG": 349.52}


def test_status_skips_snapshot_when_position_unmarked(
        tmp_path, monkeypatch, capsys):
    _engine_with_sol_goog(tmp_path)
    # crypto mark only; the stock history fetch finds nothing
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 130.0}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda *a, **k: ([], None))

    assert cli_mod.cmd_status(_status_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "GOOG" in out
    # the readout prints, but no bogus equity row is recorded
    assert Ledger(tmp_path / "ledger").read("equity") == []
    assert "SOL" in out and "GOOG" in out


def test_status_reads_snapshot_without_recording(
        tmp_path, monkeypatch, capsys):
    eng = _engine_with_sol_goog(tmp_path)
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 130.0}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda symbol, *a, **k: ([_Bar(350.0)], None))

    assert cli_mod.cmd_status(_status_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "WARNING" not in out
    # status is a read-only readout: it prints the snapshot but records
    # no equity row, so the evening loop stays the only writer
    assert Ledger(tmp_path / "ledger").read("equity") == []
    lines = out.splitlines()
    snap = json.loads("\n".join(lines[:lines.index("}") + 1]))
    # equity counts the GOOG position value, not just the debited cash
    assert snap["equity"] == pytest.approx(
        eng.portfolio.equity({"SOL": 130.0, "GOOG": 350.0}))
