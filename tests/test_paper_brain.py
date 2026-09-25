"""Milestone 1 tests for the paper-trading brain. Network-free."""
import json

import pytest

from paper import feeds as feeds_mod
from paper.engine import PaperEngine
from paper.fills import FEE_BPS, simulate_fill
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


def test_feed_extract():
    wanted = [by_symbol("BTC"), by_symbol("SOL")]
    data = {"bitcoin": {"usd": 84000}, "solana": {"usd": 133.3}}
    assert feeds_mod._extract(data, wanted) == {"BTC": 84000.0, "SOL": 133.3}
