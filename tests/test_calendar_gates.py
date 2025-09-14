from __future__ import annotations

from datetime import datetime, timedelta, timezone

from risk.calendar_gates import is_high_impact_window, is_crypto_event_window, is_exchange_maintenance, risk_gate


def test_high_impact_window_future_event():
    now = datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc)
    assert is_high_impact_window(now, lookahead_min=60) is True


def test_crypto_event_window_future_event():
    now = datetime(2030, 1, 10, 0, 0, tzinfo=timezone.utc) - timedelta(minutes=10)
    assert is_crypto_event_window(now, lookahead_min=30) is True


def test_exchange_maintenance_window():
    now = datetime(2030, 2, 1, 1, 40, tzinfo=timezone.utc)
    assert is_exchange_maintenance("bybit", now, lookahead_min=30) is True


def test_risk_gate_block_and_throttle():
    now = datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc)
    g = risk_gate(now, exchange="bybit")
    assert isinstance(g, dict)
    assert g.get("block") in (True, False)
    assert "throttle" in g

