"""CLI tests. Network-free: feeds and history are monkeypatched."""
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


def test_status_records_snapshot_with_stock_marks(
        tmp_path, monkeypatch, capsys):
    eng = _engine_with_sol_goog(tmp_path)
    monkeypatch.setattr(cli_mod.feeds, "fetch_prices",
                        lambda **kw: ({"SOL": 130.0}, None))
    monkeypatch.setattr(cli_mod.history, "fetch_daily_bars",
                        lambda symbol, *a, **k: ([_Bar(350.0)], None))

    assert cli_mod.cmd_status(_status_args(tmp_path)) == 0
    assert "WARNING" not in capsys.readouterr().out
    snaps = Ledger(tmp_path / "ledger").read("equity")
    assert len(snaps) == 1
    # equity counts the GOOG position value, not just the debited cash
    assert snaps[0]["equity"] == pytest.approx(
        eng.portfolio.equity({"SOL": 130.0, "GOOG": 350.0}))
