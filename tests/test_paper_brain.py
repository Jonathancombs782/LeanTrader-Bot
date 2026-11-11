"""Milestone 1 tests for the paper-trading brain. Network-free."""
import json
from pathlib import Path

import pytest

from paper import feeds as feeds_mod
from paper.engine import PaperEngine, replay_ledger
from paper.fills import FEE_BPS, SLIPPAGE_BPS, simulate_fill
from paper.ledger import Ledger
from paper.receipts import Receipt, hash_bytes, utcnow_iso
from paper.risk import RiskBreach, RiskLimits, check_new_trade, size_position
from paper.signals import Signal, SignalSide
from paper.universe import BLUE_CHIPS, by_symbol


# -- signals -------------------------------------------------------------
def test_signal_long_validation():
    s = Signal("SOL", SignalSide.LONG, 130, 120, 150, "breakout retest")
    assert s.risk_per_unit == 10


def test_signal_rejects_inverted_long():
    with pytest.raises(ValueError):
        Signal("SOL", SignalSide.LONG, 130, 140, 150, "bad")


def test_signal_rejects_inverted_short():
    with pytest.raises(ValueError):
        Signal("SOL", SignalSide.SHORT, 130, 120, 150, "bad")


def test_signal_requires_thesis():
    with pytest.raises(ValueError):
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "  ")


def test_inputs_hash_deterministic():
    kw = dict(symbol="SOL", side=SignalSide.LONG, entry=130, stop=120,
              target=150, thesis="t", inputs={"a": 1})
    assert Signal(**kw).inputs_hash == Signal(**kw).inputs_hash


def test_signal_roundtrip():
    r = Receipt("t", "s", utcnow_iso(), "abc", None)
    s = Signal("SOL", SignalSide.LONG, 130, 120, 150, "t", receipts=(r,),
               inputs={"a": 1})
    s2 = Signal.from_dict(s.to_dict())
    assert s2.signal_id == s.signal_id and s2.inputs_hash == s.inputs_hash


# -- receipts ------------------------------------------------------------
def test_hash_bytes_known():
    assert hash_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_receipt_verify_roundtrip(tmp_path):
    p = tmp_path / "snap.json"
    p.write_bytes(b'{"px": 1}')
    r = Receipt("t", "s", utcnow_iso(), hash_bytes(b'{"px": 1}'), str(p))
    assert r.verify_payload()
    p.write_bytes(b'{"px": 2}')
    assert not r.verify_payload()


# -- fills ---------------------------------------------------------------
def test_buy_fills_above_mid_sell_below():
    buy = simulate_fill("SOL", SignalSide.LONG, 10, 100.0, "major")
    sell = simulate_fill("SOL", SignalSide.SHORT, 10, 100.0, "major")
    assert buy.fill_price > 100.0 > sell.fill_price
    assert buy.slippage_bps == 5


def test_fill_fee_math():
    f = simulate_fill("SOL", SignalSide.LONG, 10, 100.0, "major")
    assert f.fee == pytest.approx(f.notional * FEE_BPS / 10_000)


def test_fill_rejects_bad_inputs():
    with pytest.raises(ValueError):
        simulate_fill("SOL", SignalSide.LONG, 0, 100.0)
    with pytest.raises(ValueError):
        simulate_fill("SOL", SignalSide.LONG, 10, -1.0)


# -- risk ----------------------------------------------------------------
def _ok(**kw):
    base = dict(equity=100_000, trade_risk_amount=1_000, trade_notional=10_000,
                open_risk_amount=0, symbol_open_notional=0,
                daily_pnl_pct=0.0, drawdown_pct=0.0)
    base.update(kw)
    return base


def test_risk_limits_reject_invalid_construction():
    with pytest.raises(ValueError):
        RiskLimits(max_risk_per_trade_pct=-5)
    with pytest.raises(ValueError):
        RiskLimits(max_portfolio_heat_pct=float("inf"))
    with pytest.raises(ValueError):
        RiskLimits(kill_switch_drawdown_pct=float("nan"))


def test_risk_accepts_sane_trade():
    check_new_trade(RiskLimits(), **_ok())  # no raise


def test_risk_rejects_oversize_trade():
    with pytest.raises(RiskBreach) as e:
        check_new_trade(RiskLimits(), **_ok(trade_risk_amount=2_001))
    assert e.value.limit == "per_trade_risk"


def test_risk_rejects_heat():
    with pytest.raises(RiskBreach) as e:
        check_new_trade(RiskLimits(), **_ok(open_risk_amount=5_500,
                                           trade_risk_amount=1_000))
    assert e.value.limit == "portfolio_heat"


def test_risk_rejects_position_size():
    with pytest.raises(RiskBreach) as e:
        check_new_trade(RiskLimits(), **_ok(trade_notional=25_001))
    assert e.value.limit == "position_size"


def test_risk_daily_halt():
    with pytest.raises(RiskBreach) as e:
        check_new_trade(RiskLimits(), **_ok(daily_pnl_pct=-4.0))
    assert e.value.limit == "daily_loss_halt"


def test_risk_kill_switch():
    with pytest.raises(RiskBreach) as e:
        check_new_trade(RiskLimits(), **_ok(drawdown_pct=15.0))
    assert e.value.limit == "kill_switch"


def test_size_position_caps_notional():
    # 2% of 100k = $2000 risk; risk/unit $10 -> 200 units -> $26k notional,
    # capped at 25% of equity = $25k -> 192.307 units @ $130
    qty = size_position(100_000, RiskLimits(), 10, 130)
    assert qty == pytest.approx(25_000 / 130)


# -- engine --------------------------------------------------------------
def _engine(tmp_path):
    return PaperEngine(ledger=Ledger(tmp_path / "ledger"))


def _sig(**kw):
    base = dict(symbol="SOL", side=SignalSide.LONG, entry=130, stop=120,
                target=150, thesis="breakout retest holds")
    base.update(kw)
    return Signal(**base)


def test_engine_accepts_and_ledgers(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    res = eng.submit_signal(_sig())
    assert res.accepted
    assert "SOL" in eng.portfolio.positions
    assert len(eng.ledger.read("signals")) == 1
    assert len(eng.ledger.read("fills")) == 1


def test_engine_rejects_no_price(tmp_path):
    eng = _engine(tmp_path)
    res = eng.submit_signal(_sig())
    assert not res.accepted and "no price" in res.reason


def test_engine_rejects_and_logs_breach(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0, "LINK": 12.0, "BTC": 84000.0, "XRP": 1.78})
    assert eng.submit_signal(_sig(symbol="SOL", entry=130, stop=120, target=150)).accepted
    assert eng.submit_signal(_sig(symbol="LINK", entry=12, stop=11, target=14)).accepted
    assert eng.submit_signal(_sig(symbol="BTC", entry=84000, stop=80000, target=90000)).accepted
    # heat is near the 6% cap; a 4th trade breaches portfolio_heat
    res = eng.submit_signal(_sig(symbol="XRP", entry=1.78, stop=1.60, target=2.10))
    assert not res.accepted
    assert "portfolio_heat" in res.reason
    breaches = eng.ledger.read("risk_events")
    assert breaches and breaches[-1]["limit"] == "portfolio_heat"
    assert eng.ledger.read("signals")[-1]["disposition"] == "rejected"


def test_engine_close_realizes_pnl(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.update_prices({"SOL": 140.0})
    pnl = eng.close("SOL")
    assert pnl > 0
    assert "SOL" not in eng.portfolio.positions
    snap = eng.snapshot_equity()
    assert snap["equity"] > 100_000


def test_engine_daily_halt_blocks_new_trades(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.update_prices({"SOL": 100.0})  # deep red day
    eng.portfolio.day_start_equity = 100_000
    res = eng.submit_signal(_sig(symbol="LINK"))
    # LINK has no price -> rejected for no price first; give it a price
    eng.update_prices({"LINK": 12.0})
    res = eng.submit_signal(_sig(symbol="LINK", entry=12, stop=11, target=14))
    assert not res.accepted
    assert "daily_loss_halt" in res.reason


# -- ledger --------------------------------------------------------------
def test_ledger_roundtrip(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    ledger.append("signals", {"signal_id": "abc"})
    rows = ledger.read("signals")
    assert rows[0]["signal_id"] == "abc" and "logged_at" in rows[0]


def test_ledger_verify_catches_tamper(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    snap = tmp_path / "snap.json"
    snap.write_bytes(b'{"px": 1}')
    r = Receipt("coingecko_price_snapshot", "http://x", utcnow_iso(),
                hash_bytes(b'{"px": 1}'), str(snap))
    s = Signal("SOL", SignalSide.LONG, 130, 120, 150, "t", receipts=(r,))
    ledger.append("signals", s.to_dict())
    assert ledger.verify_receipts() == {}
    snap.write_bytes(b'{"px": 999}')
    failures = ledger.verify_receipts()
    assert failures == {s.signal_id: ["coingecko_price_snapshot"]}


# -- universe / feeds ----------------------------------------------------
def test_blue_chips_universe():
    syms = {a.symbol for a in BLUE_CHIPS}
    assert {"BTC", "SOL", "XRP", "USDC"} <= syms
    assert by_symbol("BTC").tier == "major"


def test_blue_chips_is_19_assets_documented():
    # docs/paper-architecture.md promises a 19-asset seed universe
    assert len(BLUE_CHIPS) == 19
    assert "ETH" not in {a.symbol for a in BLUE_CHIPS}


def test_feed_extract():
    wanted = [by_symbol("BTC"), by_symbol("SOL")]
    data = {"bitcoin": {"usd": 84000}, "solana": {"usd": 133.3}}
    prices, provider_ts = feeds_mod._extract(data, wanted)
    assert prices == {"BTC": 84000.0, "SOL": 133.3}
    # no last_updated_at in the payload -> timestamps unknown, not fabricated
    assert provider_ts == {"BTC": None, "SOL": None}


def test_feed_extract_keeps_last_updated_at():
    wanted = [by_symbol("BTC"), by_symbol("SOL")]
    data = {"bitcoin": {"usd": 84000, "last_updated_at": 1793797195},
            "solana": {"usd": 133.3, "last_updated_at": 1793797200}}
    prices, provider_ts = feeds_mod._extract(data, wanted)
    assert prices == {"BTC": 84000.0, "SOL": 133.3}
    assert provider_ts == {"BTC": 1793797195, "SOL": 1793797200}


def test_fail_closed_blocks_new_orders_on_stale_mark(tmp_path):
    from datetime import datetime, timedelta, timezone
    eng = PaperEngine(ledger=Ledger(tmp_path / "ledger"))
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "t")).accepted
    # simulate a day with no refresh: the open SOL mark goes stale
    stale = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
    eng.marks["SOL"]["received_at"] = stale
    eng.update_prices({"GOOG": 350.0})  # GOOG fresh, SOL stale
    res = eng.submit_signal(
        Signal("GOOG", SignalSide.LONG, 350, 340, 370, "t"))
    assert not res.accepted
    assert "risk_indeterminate" in res.reason and "SOL" in res.reason


def test_fail_closed_blocks_new_orders_on_missing_mark(tmp_path):
    eng = PaperEngine(ledger=Ledger(tmp_path / "ledger"))
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(
        Signal("SOL", SignalSide.LONG, 130, 120, 150, "t")).accepted
    del eng.marks["SOL"]  # mark lost entirely
    eng.update_prices({"GOOG": 350.0})
    res = eng.submit_signal(
        Signal("GOOG", SignalSide.LONG, 350, 340, 370, "t"))
    assert not res.accepted
    assert "risk_indeterminate" in res.reason and "missing mark" in res.reason


# -- ledger replay -------------------------------------------------------
def test_replay_reconstructs_open_position(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    live_cash = eng.portfolio.cash
    live_pos = eng.portfolio.positions["SOL"]

    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    rpos = replayed.portfolio.positions["SOL"]
    assert replayed.portfolio.cash == pytest.approx(live_cash)
    assert rpos.quantity == pytest.approx(live_pos.quantity)
    assert rpos.avg_price == pytest.approx(live_pos.avg_price)
    assert rpos.side == live_pos.side
    assert rpos.stop == live_pos.stop and rpos.target == live_pos.target
    assert rpos.risk_amount == pytest.approx(live_pos.risk_amount)
    # mark-to-market matches the live engine
    replayed.update_prices({"SOL": 140.0})
    eng.update_prices({"SOL": 140.0})
    assert replayed.portfolio.equity({"SOL": 140.0}) == pytest.approx(
        eng.portfolio.equity({"SOL": 140.0})
    )


def test_replay_applies_close_and_realized_pnl(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.update_prices({"SOL": 140.0})
    live_pnl = eng.close("SOL")
    live_cash = eng.portfolio.cash

    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert "SOL" not in replayed.portfolio.positions
    assert replayed.portfolio.realized_pnl == pytest.approx(live_pnl)
    assert replayed.portfolio.cash == pytest.approx(live_cash)


def test_replay_skips_rejected_signals(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0, "LINK": 12.0, "BTC": 84000.0, "XRP": 1.78})
    assert eng.submit_signal(_sig(symbol="SOL", entry=130, stop=120, target=150)).accepted
    assert eng.submit_signal(_sig(symbol="LINK", entry=12, stop=11, target=14)).accepted
    assert eng.submit_signal(_sig(symbol="BTC", entry=84000, stop=80000, target=90000)).accepted
    res = eng.submit_signal(_sig(symbol="XRP", entry=1.78, stop=1.60, target=2.10))
    assert not res.accepted  # rejected on portfolio_heat

    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert set(replayed.portfolio.positions) == {"SOL", "LINK", "BTC"}
    assert replayed.portfolio.cash == pytest.approx(eng.portfolio.cash)


def test_replay_restores_peak_from_equity_snapshots(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.update_prices({"SOL": 150.0})
    eng.snapshot_equity()
    peak = eng.portfolio.peak_equity

    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert replayed.portfolio.peak_equity == pytest.approx(peak)


def test_replay_is_read_only(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    ledger = Ledger(tmp_path / "ledger")
    before = {s: len(ledger.read(s)) for s in ("signals", "fills", "risk_events", "equity")}
    replay_ledger(ledger)
    after = {s: len(ledger.read(s)) for s in ("signals", "fills", "risk_events", "equity")}
    assert before == after


# -- Codex P1 regression tests -------------------------------------------
def test_engine_sizes_from_fill_not_declared_entry(tmp_path):
    # stale declared entry: market is 200, signal still says 100
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 200.0})
    res = eng.submit_signal(_sig(entry=100, stop=90, target=120))
    assert res.accepted
    pos = eng.portfolio.positions["SOL"]
    probe = simulate_fill("SOL", SignalSide.LONG, 1.0, 200.0, by_symbol("SOL").tier)
    true_risk_per_unit = abs(probe.fill_price - 90)
    # risk accounts the ~110/unit fill-to-stop distance, not the 10/unit
    # entry-to-stop distance the old code used
    assert pos.risk_amount == pytest.approx(pos.quantity * true_risk_per_unit)
    assert pos.risk_amount == pytest.approx(0.02 * 100_000, rel=1e-3)
    assert pos.quantity < 100  # entry-based sizing would have taken 200 units


def test_engine_rejects_stop_at_fill_price(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    probe = simulate_fill("SOL", SignalSide.LONG, 1.0, 130.0, by_symbol("SOL").tier)
    res = eng.submit_signal(_sig(entry=140, stop=probe.fill_price, target=160))
    assert not res.accepted
    assert "per_trade_risk" in res.reason


def test_engine_rejects_second_fill_on_open_symbol(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    first_qty = eng.portfolio.positions["SOL"].quantity
    first_cash = eng.portfolio.cash
    res = eng.submit_signal(_sig(entry=132, stop=122, target=152))
    assert not res.accepted
    assert "single_position_per_symbol" in res.reason
    # original position untouched: still one position, same quantity, same cash
    assert list(eng.portfolio.positions) == ["SOL"]
    assert eng.portfolio.positions["SOL"].quantity == pytest.approx(first_qty)
    assert eng.portfolio.cash == pytest.approx(first_cash)


def test_day_roll_resets_baseline_on_new_day(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.portfolio.trading_day = "2026-09-01"
    eng.update_prices({"SOL": 140.0})
    assert eng.roll_day_if_new(today="2026-09-30")
    assert eng.portfolio.trading_day == "2026-09-30"
    assert eng.portfolio.day_start_equity == pytest.approx(
        eng.portfolio.equity({"SOL": 140.0}))
    assert not eng.roll_day_if_new(today="2026-09-30")
    rolls = [e for e in eng.ledger.read("risk_events") if e.get("event") == "day_roll"]
    assert len(rolls) == 1 and rolls[0]["trading_day"] == "2026-09-30"


def test_submit_signal_rolls_day_before_gating(tmp_path):
    # a stale baseline from yesterday must not halt today's trading
    eng = _engine(tmp_path)
    eng.portfolio.trading_day = "2026-09-01"
    eng.portfolio.day_start_equity = 110_000.0  # would read as -9% today
    eng.update_prices({"SOL": 130.0})
    res = eng.submit_signal(_sig())
    assert res.accepted
    assert eng.portfolio.trading_day == utcnow_iso()[:10]


def test_replay_restores_day_roll_marker(tmp_path):
    eng = _engine(tmp_path)
    eng.portfolio.trading_day = "2026-09-01"
    eng.update_prices({"SOL": 130.0})
    eng.roll_day_if_new(today="2026-09-30")
    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert replayed.portfolio.trading_day == "2026-09-30"
    assert replayed.portfolio.day_start_equity == pytest.approx(
        eng.portfolio.day_start_equity)


def test_replay_bootstraps_day_roll_when_none_recorded(tmp_path):
    # Fresh ledgers have no day_roll events: the funded portfolio claims
    # trading_day=today, which would suppress the first roll forever and
    # freeze day_start_equity at the initial funding.
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    rolls = [e for e in eng.ledger.read("risk_events")
             if e.get("event") == "day_roll"]
    assert not rolls

    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert replayed.portfolio.trading_day == ""
    replayed.update_prices({"SOL": 140.0})
    assert replayed.roll_day_if_new(today="2026-09-30")
    assert replayed.portfolio.day_start_equity == pytest.approx(
        replayed.portfolio.equity({"SOL": 140.0}))
    # the marker now persists across replays
    again = replay_ledger(Ledger(tmp_path / "ledger"))
    assert again.portfolio.trading_day == "2026-09-30"
    assert again.portfolio.day_start_equity == pytest.approx(
        replayed.portfolio.day_start_equity)


def test_close_applies_slippage(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    eng.update_prices({"SOL": 140.0})
    pnl = eng.close("SOL")
    close_rec = eng.ledger.read("fills")[-1]
    assert close_rec["event"] == "close"
    bps = SLIPPAGE_BPS[by_symbol("SOL").tier]
    assert close_rec["slippage_bps"] == bps
    # a long closes by selling into the bid: below mid, not at it
    assert close_rec["exit_price"] == pytest.approx(140.0 * (1 - bps / 10_000))
    assert close_rec["exit_price"] < 140.0
    assert pnl > 0  # 130 -> ~139.93 is still a win after slippage + fee
    assert "SOL" not in eng.portfolio.positions


def test_feed_cache_keyed_by_requested_ids(tmp_path, monkeypatch):
    import urllib.request as urlreq

    calls = []

    class _Resp:
        def __init__(self, raw):
            self._raw = raw
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return self._raw

    def fake_urlopen(req, timeout=20):
        calls.append(req.full_url)
        if "ids=solana" in req.full_url:
            return _Resp(b'{"solana":{"usd":130.0}}')
        if "ids=bitcoin" in req.full_url:
            return _Resp(b'{"bitcoin":{"usd":84000.0}}')
        raise AssertionError(f"unexpected url {req.full_url}")

    monkeypatch.setattr(urlreq, "urlopen", fake_urlopen)
    cache, ev = tmp_path / "cache", tmp_path / "evidence"
    px1, _ = feeds_mod.fetch_prices(["SOL"], cache_dir=cache, evidence_dir=ev)
    assert px1 == {"SOL": 130.0}
    # a BTC request within the TTL must NOT reuse the SOL-only cache file
    px2, _ = feeds_mod.fetch_prices(["BTC"], cache_dir=cache, evidence_dir=ev)
    assert px2 == {"BTC": 84000.0}
    assert len(calls) == 2
    assert len(list(cache.glob("coingecko_simple_*.json"))) == 2
    # repeat SOL request is served from its own cache entry
    px3, r3 = feeds_mod.fetch_prices(["SOL"], cache_dir=cache, evidence_dir=ev)
    assert px3 == {"SOL": 130.0} and len(calls) == 2
    assert r3.note == "served from cache"


def test_snapshot_filenames_are_content_addressed(tmp_path):
    ev = tmp_path / "evidence"
    ev.mkdir()
    r1 = feeds_mod._snapshot_receipt(b'{"a":1}', "http://x", ev, note="n1")
    r2 = feeds_mod._snapshot_receipt(b'{"a":2}', "http://x", ev, note="n2")
    r3 = feeds_mod._snapshot_receipt(b'{"a":1}', "http://x", ev, note="n3")
    # different payloads can never collide; identical bytes share one file
    assert r1.payload_path != r2.payload_path
    assert r1.payload_path == r3.payload_path
    assert r1.verify_payload()
    assert Path(r1.payload_path).read_bytes() == b'{"a":1}'


# -- Codex P1-1: CLI replays the ledger before risk gates ------------------
def _fake_prices(symbols=None, universe=None, cache_dir="paper/cache",
                 evidence_dir="paper/evidence"):
    canned = {"SOL": 130.0, "LINK": 12.0, "BTC": 84000.0, "XRP": 1.78}
    want = symbols if symbols is not None else list(canned)
    return ({s: canned[s] for s in want if s in canned}, None)


def test_cli_signal_replays_ledger_before_risk_gates(tmp_path, monkeypatch, capsys):
    from paper import cli as cli_mod

    monkeypatch.setattr("paper.feeds.fetch_prices", _fake_prices)
    base = ["--ledger", str(tmp_path / "ledger"), "--cache", str(tmp_path / "cache"),
            "--evidence", str(tmp_path / "evidence"), "signal"]

    def sig(sym, entry, stop, target):
        return base + [sym, "long", "--entry", str(entry), "--stop", str(stop),
                       "--target", str(target), "--thesis", "t"]

    # three separate invocations, each risking ~2%: heat accumulates to ~6%
    assert cli_mod.main(sig("SOL", 130, 120, 150)) == 0
    assert cli_mod.main(sig("LINK", 12, 11, 14)) == 0
    assert cli_mod.main(sig("BTC", 84000, 80000, 90000)) == 0
    # a 4th invocation must see the replayed positions and breach heat
    assert cli_mod.main(sig("XRP", 1.78, 1.60, 2.10)) == 1
    assert "portfolio_heat" in capsys.readouterr().out
    ledger = Ledger(tmp_path / "ledger")
    assert [f["symbol"] for f in ledger.read("fills")] == ["SOL", "LINK", "BTC"]
    assert ledger.read("signals")[-1]["disposition"] == "rejected"


# -- Nov 9, 2026 ledger fix: annotate, never delete ----------------------
# The Nov 4, 2026 phantom fills (four SOL longs in one second while a long
# was already open) and the broken day_start baselines (frozen $100,000
# Oct 5-13; GOOG leg missing Oct 24-Nov 3; negative Nov 4-8) are annotated
# in the ledger. These tests pin the fix: replay skips phantoms, the
# single-position gate sees fills logged by other engines, and the day-roll
# refuses an indeterminate mark set instead of recording a bad baseline.


def _seed_phantom_pair(tmp_path):
    """A ledger with one legit SOL fill and one phantom SOL fill.

    Mirrors Nov 4, 2026: the phantom is identical to its siblings except
    signal_id, and its signal is recorded accepted — so only the
    legitimacy annotation can tell replay to skip it.
    """
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    ledger = Ledger(tmp_path / "ledger")
    ledger.append("signals", {
        "signal_id": "phantom-1", "symbol": "SOL", "side": "long",
        "entry": 100.0, "stop": 95.0, "target": 110.0, "thesis": "t",
        "disposition": "accepted",
    })
    ledger.append("fills", {
        "signal_id": "phantom-1", "symbol": "SOL", "side": "long",
        "quantity": 249.87506246876563, "mid_price": 100.0,
        "fill_price": 100.05, "notional": 25000.0, "fee": 25.0,
        "slippage_bps": 5, "risk_amount": 762.1189405297345,
        "legitimacy": "phantom",
        "at": "2026-11-04T16:15:35+00:00",
    })
    return ledger


def test_replay_skips_phantom_fills(tmp_path):
    _seed_phantom_pair(tmp_path)
    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert list(replayed.portfolio.positions) == ["SOL"]
    # only the legit fill debited cash: the phantom's $25,000 never left
    assert replayed.portfolio.cash == pytest.approx(100_000 - 25000.0 - 25.0)
    assert replayed.portfolio.positions["SOL"].quantity < 210.0  # legit size
    assert replayed.portfolio.equity({"SOL": 130.0}) > 0


def test_submit_signal_sees_fills_logged_by_another_engine(tmp_path):
    # Nov 4, 2026: four SOL fills in one second from engines that never saw
    # each other's writes. An engine built before the first fill must still
    # reject the re-entry once the fill is in the ledger.
    ledger = Ledger(tmp_path / "ledger")
    first = PaperEngine(ledger=ledger)
    second = PaperEngine(ledger=ledger)  # built before any fill exists
    first.update_prices({"SOL": 130.0})
    assert first.submit_signal(_sig()).accepted
    second.update_prices({"SOL": 130.0})
    res = second.submit_signal(_sig(entry=132, stop=122, target=152))
    assert not res.accepted
    assert "single_position_per_symbol" in res.reason
    assert len(ledger.read("fills")) == 1


def _engine_with_sol_goog(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0, "GOOG": 350.0})
    assert eng.submit_signal(_sig()).accepted
    assert eng.submit_signal(
        _sig(symbol="GOOG", entry=350, stop=340, target=370)).accepted
    return eng


def test_day_roll_refuses_on_indeterminate_marks(tmp_path):
    eng = _engine_with_sol_goog(tmp_path)
    del eng.marks["GOOG"]  # the GOOG mark is lost before the next day's roll
    eng.portfolio.trading_day = "2026-09-01"
    old_baseline = eng.portfolio.day_start_equity
    assert not eng.roll_day_if_new(today="2026-09-30")
    assert eng.portfolio.trading_day == "2026-09-01"
    assert eng.portfolio.day_start_equity == pytest.approx(old_baseline)
    refusals = [e for e in eng.ledger.read("risk_events")
                if e.get("event") == "day_roll_refused"]
    assert len(refusals) == 1
    assert refusals[0]["trading_day"] == "2026-09-30"
    assert "GOOG" in refusals[0]["reason"]
    assert refusals[0]["mark_state"].startswith("indeterminate")
    assert not [e for e in eng.ledger.read("risk_events")
                if e.get("event") == "day_roll"
                and e.get("trading_day") == "2026-09-30"]


def test_day_roll_refused_logged_once_per_day(tmp_path):
    eng = _engine_with_sol_goog(tmp_path)
    del eng.marks["GOOG"]
    eng.portfolio.trading_day = "2026-09-01"
    assert not eng.roll_day_if_new(today="2026-09-30")
    assert not eng.roll_day_if_new(today="2026-09-30")
    refusals = [e for e in eng.ledger.read("risk_events")
                if e.get("event") == "day_roll_refused"]
    assert len(refusals) == 1


def test_baseline_correction_restores_day_start(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    # a broken day_roll (the Nov 3, 2026 shape: baseline missing a leg)
    eng.ledger.append("risk_events", {
        "event": "day_roll", "trading_day": "2026-11-03",
        "day_start_equity": 70094.32})
    # the correction supersedes it: the last marker event wins
    eng.ledger.append("risk_events", {
        "event": "baseline_correction", "trading_day": "2026-11-03",
        "day_start_equity": 89422.15,
        "reason": "reset to verified Nov 3 close"})
    replayed = replay_ledger(Ledger(tmp_path / "ledger"))
    assert replayed.portfolio.trading_day == "2026-11-03"
    assert replayed.portfolio.day_start_equity == pytest.approx(89422.15)


def test_new_fill_carries_legitimacy(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    fills = eng.ledger.read("fills")
    assert len(fills) == 1 and fills[0]["legitimacy"] == "legit"


def test_snapshot_carries_two_axis_classification(tmp_path):
    eng = _engine(tmp_path)
    eng.update_prices({"SOL": 130.0})
    assert eng.submit_signal(_sig()).accepted
    snap = eng.snapshot_equity()
    assert snap["legitimacy"] == "legit"
    assert snap["mark_state"] == "ok"
    assert snap["marks"]["SOL"]["price"] == pytest.approx(130.0)
    assert "received_at" in snap["marks"]["SOL"]
