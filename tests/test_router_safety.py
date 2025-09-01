import os  # noqa: F401  # intentionally kept

import pytest  # noqa: F401  # intentionally kept

from router import ExchangeRouter


def test_paper_mode_is_dry_run(tmp_path, monkeypatch):
    # Force paper exchange
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "false")
    r = ExchangeRouter()
    assert r.id == "paper"
    # safe_place_order should return dry_run when not live
    out = r.safe_place_order("BTC/USDT", "buy", 0.001)
    assert out.get("dry_run", False) is True


def test_live_requires_allow_and_confirm(monkeypatch):
    # Ensure that ENABLE_LIVE without ALLOW_LIVE and LIVE_CONFIRM stays dry-run
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "true")
    monkeypatch.setenv("ALLOW_LIVE", "false")
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    r = ExchangeRouter()
    assert r.live is False

    # With ALLOW_LIVE but without LIVE_CONFIRM it must still be disabled
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    r2 = ExchangeRouter()
    assert r2.live is False

    # Only with LIVE_CONFIRM=YES should live be allowed when ALLOW_LIVE set
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.setenv("LIVE_CONFIRM", "YES")
    # Use paper exchange to avoid real orders but confirm flags are respected on initialization
    r3 = ExchangeRouter()
    # When EXCHANGE_ID==paper we expect a PaperBroker backend, not live regardless, so live remains False
    assert r3.id == "paper"
    assert r3.live is False
