import os
from router import ExchangeRouter


def test_live_order_usd_cap(monkeypatch):
    # Use paper backend to avoid real orders
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "true")
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.setenv("LIVE_CONFIRM", "YES")
    # set per-order USD cap very low
    monkeypatch.setenv("LIVE_ORDER_USD", "1")

    r = ExchangeRouter()
    # simulate place order where price * amount > LIVE_ORDER_USD
    # choose symbol that exists in paper markets (paper broker uses simple mapping)
    res = r.safe_place_order("BTC/USDT", "buy", 1.0, price=100.0)
    assert res.get("ok") is False or res.get("error"), "Orders exceeding LIVE_ORDER_USD must be blocked"


def test_max_order_size_enforced(monkeypatch):
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "true")
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.setenv("LIVE_CONFIRM", "YES")
    # set MAX_ORDER_SIZE to a small value
    monkeypatch.setenv("MAX_ORDER_SIZE", "0.1")

    r = ExchangeRouter()
    res = r.safe_place_order("BTC/USDT", "buy", 1.0)
    assert res.get("ok") is False or res.get("error"), "Orders exceeding MAX_ORDER_SIZE must be blocked"
