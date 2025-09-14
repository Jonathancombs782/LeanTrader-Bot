from router import ExchangeRouter


def test_refuse_live_without_creds(monkeypatch):
    # Simulate environment where live flags are set but no API creds provided
    monkeypatch.setenv("EXCHANGE_ID", "paper")
    monkeypatch.setenv("ENABLE_LIVE", "true")
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.setenv("LIVE_CONFIRM", "YES")
    # Ensure no API_KEY/SECRET in env
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_SECRET", raising=False)

    r = ExchangeRouter()
    # Mutate instance to simulate a non-paper live router (avoid importing ccxt)
    r.id = "bybit"
    r.live = True
    r.allow_live = True
    # ensure instance captured no creds
    r._has_api_creds = False
    r._exchange_malformed = False

    # attach a dummy exchange object to avoid attribute errors if reached
    class _DummyEx:
        def create_order(self, *a, **k):
            raise RuntimeError("should not be called when creds missing")

    r.ex = _DummyEx()

    # Instance should refuse to place live orders because API creds are missing
    res = r.safe_place_order("BTC/USDT", "buy", 0.01, price=100.0)
    assert res.get("ok") is False and res.get("error")
