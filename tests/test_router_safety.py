import logging

import pytest

from router import ExchangeRouter


def test_apply_runtime_order_block_blocks_methods(monkeypatch, caplog):
    # Ensure env disables live
    monkeypatch.setenv("ENABLE_LIVE", "false")
    caplog.set_level(logging.DEBUG)

    # Create an ExchangeRouter instance without calling __init__ to avoid ccxt imports
    r = object.__new__(ExchangeRouter)
    # minimal attributes expected by apply_runtime_order_block
    r.id = "dummy"
    r.live = False
    r.markets = {}
    r._exchange_malformed = False
    r._has_api_creds = False

    # Attach a fake exchange object with create_order to verify it gets stubbed
    class DummyEx:
        def create_order(self, *a, **k):
            return {"ok": True}

    r.ex = DummyEx()

    # Call apply_runtime_order_block explicitly
    r.apply_runtime_order_block()

    # After overlay, router create_order should be stubbed/dry-run
    res = r.create_order("BTC/USDT", "market", "buy", 0.01)
    assert isinstance(res, dict)
    assert res.get("dry_run") is True or res.get("ok") is False

    # Underlying exchange stub should also block
    ex_res = r.ex.create_order("BTC/USDT", "market", "buy", 0.01)
    assert isinstance(ex_res, dict)
    assert ex_res.get("dry_run") is True or ex_res.get("ok") is False

    # Ensure logs include the blocked message
    msgs = "\n".join([rec.message for rec in caplog.records])
    assert "blocked" in msgs.lower() or "live disabled" in msgs.lower()


def test_paper_mode_is_dry_run(monkeypatch):
    # Force paper exchange
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "false")
    r = ExchangeRouter()
    assert r.id == "paper"
    # safe_place_order should return dry_run when not live
    out = r.safe_place_order("BTC/USDT", "buy", 0.001)
    assert out.get("dry_run", False) is True
import os
import logging

from router import ExchangeRouter


def test_apply_runtime_order_block_blocks_methods(monkeypatch, caplog):
    # Ensure env disables live
    monkeypatch.setenv("ENABLE_LIVE", "false")
    caplog.set_level(logging.DEBUG)

    # Create an ExchangeRouter instance without calling __init__ to avoid ccxt imports
    r = object.__new__(ExchangeRouter)
    # minimal attributes expected by apply_runtime_order_block
    r.id = "dummy"
    r.live = False
    r.markets = {}
    r._exchange_malformed = False
    r._has_api_creds = False

    # Attach a fake exchange object with create_order to verify it gets stubbed
    class DummyEx:
        def create_order(self, *a, **k):
            return {"ok": True}

    r.ex = DummyEx()

    # Call apply_runtime_order_block explicitly
    r.apply_runtime_order_block()

    # After overlay, router create_order should be stubbed/dry-run
    res = r.create_order("BTC/USDT", "market", "buy", 0.01)
    assert isinstance(res, dict)
    assert res.get("dry_run") is True or res.get("ok") is False

    # Underlying exchange stub should also block
    ex_res = r.ex.create_order("BTC/USDT", "market", "buy", 0.01)
    assert isinstance(ex_res, dict)
    assert ex_res.get("dry_run") is True or ex_res.get("ok") is False

    # Ensure logs include the blocked message
    msgs = "\n".join([rec.message for rec in caplog.records])
    assert "blocked" in msgs.lower() or "live disabled" in msgs.lower()
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
