"""Ledger hash-chain tests (B4/D4). Network-free.

Each new line carries prev_hash + record_sha; verify_chain() fails on
any edit, delete, reorder, or unchained-after-chained line. Pre-chain
(legacy) lines are a valid prefix, never rewritten.
"""
import hashlib
import json

import pytest

from paper import cli as cli_mod
from paper.engine import replay_ledger
from paper.ledger import GENESIS_PREV_HASH, Ledger, _record_sha


def _rewrite(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_first_append_is_genesis(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    rec = ledger.append("signals", {"signal_id": "abc"})
    assert rec["prev_hash"] == GENESIS_PREV_HASH
    assert rec["record_sha"] == _record_sha(rec)


def test_appends_chain_prev_to_record_sha(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    first = ledger.append("signals", {"signal_id": "a"})
    second = ledger.append("signals", {"signal_id": "b"})
    third = ledger.append("fills", {"signal_id": "a"})
    assert second["prev_hash"] == first["record_sha"]
    assert second["record_sha"] == _record_sha(second)
    # chains are per-stream: the fills stream starts at GENESIS
    assert third["prev_hash"] == GENESIS_PREV_HASH


def test_verify_chain_passes_on_chained_lines(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    for i in range(3):
        ledger.append("equity", {"equity": 100_000 + i})
    res = ledger.verify_chain("equity")
    assert res["ok"] and res["chained"] == 3 and res["legacy"] == 0


def test_verify_chain_catches_edited_line(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    for i in range(3):
        ledger.append("equity", {"equity": 100_000 + i})
    path = tmp_path / "ledger" / "equity.ndjson"
    rows = ledger.read("equity")
    rows[1]["equity"] = 999_999  # tamper after the fact
    _rewrite(path, rows)
    res = ledger.verify_chain("equity")
    assert not res["ok"]
    assert "record_sha mismatch" in res["failures"][0]


def test_verify_chain_catches_deleted_line(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    for i in range(3):
        ledger.append("equity", {"equity": 100_000 + i})
    path = tmp_path / "ledger" / "equity.ndjson"
    rows = ledger.read("equity")
    del rows[1]
    _rewrite(path, rows)
    res = ledger.verify_chain("equity")
    assert not res["ok"]
    assert "prev_hash mismatch" in res["failures"][0]


def test_verify_chain_catches_reordered_lines(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    for i in range(3):
        ledger.append("equity", {"equity": 100_000 + i})
    path = tmp_path / "ledger" / "equity.ndjson"
    rows = ledger.read("equity")
    rows[0], rows[1] = rows[1], rows[0]
    _rewrite(path, rows)
    res = ledger.verify_chain("equity")
    assert not res["ok"]


def test_legacy_prefix_is_tolerated_and_anchored(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    # two pre-chain lines, written exactly as the old code wrote them
    (root / "equity.ndjson").write_text(
        '{"logged_at": "2026-11-01T00:00:00+00:00", "equity": 90000}\n'
        '{"logged_at": "2026-11-02T00:00:00+00:00", "equity": 91000}\n')
    ledger = Ledger(root)
    chained = ledger.append("equity", {"equity": 92000})
    # the first chained line anchors on the raw bytes of the last legacy line
    legacy_raw = ('{"logged_at": "2026-11-02T00:00:00+00:00", '
                  '"equity": 91000}')
    assert chained["prev_hash"] == hashlib.sha256(
        legacy_raw.encode("utf-8")).hexdigest()
    res = ledger.verify_chain("equity")
    assert res["ok"] and res["legacy"] == 2 and res["chained"] == 1


def test_legacy_line_after_chained_history_fails(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    ledger.append("equity", {"equity": 100_000})
    path = tmp_path / "ledger" / "equity.ndjson"
    with path.open("a") as f:
        # a line written by old code (or by hand) after chaining started
        f.write('{"logged_at": "2026-11-12T00:00:00+00:00", '
                '"equity": 100001}\n')
    res = ledger.verify_chain("equity")
    assert not res["ok"]
    assert "unchained line after chained history" in res["failures"][0]


def test_chain_survives_replay(tmp_path):
    from paper.signals import Signal, SignalSide
    from paper.engine import PaperEngine
    eng = PaperEngine(ledger=Ledger(tmp_path / "ledger"))
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "t")).accepted
    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert list(replayed.portfolio.positions) == ["SOL"]
    assert replayed.replay_diagnostics == []
    assert Ledger(tmp_path / "ledger").verify_chain("fills")["ok"]
    assert Ledger(tmp_path / "ledger").verify_chain("signals")["ok"]


def test_cli_verify_checks_chain(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    ledger = Ledger(tmp_path / "ledger")
    ledger.append("equity", {"equity": 100_000})
    args = SimpleNamespace(ledger=str(tmp_path / "ledger"))
    assert cli_mod.cmd_verify(args) == 0
    assert "chain equity: OK" in capsys.readouterr().out
    # tamper with the chained line: verify must now fail
    path = tmp_path / "ledger" / "equity.ndjson"
    rows = ledger.read("equity")
    rows[0]["equity"] = 1
    _rewrite(path, rows)
    assert cli_mod.cmd_verify(args) == 1
    assert "CHAIN FAILED" in capsys.readouterr().out
