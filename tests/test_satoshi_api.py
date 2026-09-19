"""Tests for marketdata.satoshi_api (no network, no real credentials)."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
from decimal import Decimal

import pytest

from marketdata.satoshi_api import (
    CoinbaseAPIError,
    CoinbaseBrokerageClient,
    CredentialsError,
    LiveTradingDisabledError,
    PublicMarketData,
    btc_sats_snapshot,
    btc_to_sats,
    build_jwt,
    load_cdp_credentials,
    sats_per_usd,
    sats_to_btc,
    usd_per_sat,
)


# ---------------------------------------------------------------------------
# Satoshi conversion helpers
# ---------------------------------------------------------------------------

def test_btc_to_sats():
    assert btc_to_sats(1) == 100_000_000
    assert btc_to_sats("0.00000001") == 1
    assert btc_to_sats(Decimal("1.5")) == 150_000_000
    assert btc_to_sats(0) == 0


def test_sats_to_btc():
    assert sats_to_btc(100_000_000) == Decimal("1")
    assert sats_to_btc(1) == Decimal("0.00000001")


def test_usd_per_sat_and_sats_per_usd():
    # At $100,000/BTC: 1 sat = $0.001, $1 = 1,000 sats
    assert usd_per_sat(100_000) == Decimal("0.001")
    assert sats_per_usd(100_000) == Decimal("1000")


def test_conversion_helpers_reject_bad_input():
    with pytest.raises(ValueError):
        usd_per_sat(0)
    with pytest.raises(ValueError):
        sats_per_usd(-5)
    with pytest.raises(ValueError):
        btc_to_sats("not-a-number")


# ---------------------------------------------------------------------------
# Public market data (mocked HTTP)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen_factory(payload):
    def _fake_urlopen(req, timeout=None):
        return _FakeResp(payload)
    return _fake_urlopen


def test_fetch_btc_price_uses_product_endpoint(monkeypatch):
    import marketdata.satoshi_api as api

    seen = {}

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _FakeResp({"product_id": "BTC-USD", "price": "81227.78"})

    monkeypatch.setattr(api.urllib.request, "urlopen", _fake_urlopen)
    price = api.fetch_btc_price(product_id="BTC-USD")
    assert price == Decimal("81227.78")
    assert "/market/products/BTC-USD" in seen["url"]
    assert "ticker" not in seen["url"]


def test_public_client_http_error_maps_to_api_error(monkeypatch):
    import marketdata.satoshi_api as api

    def _boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _boom)
    with pytest.raises(CoinbaseAPIError, match="429"):
        PublicMarketData().product("BTC-USD")


def test_btc_sats_snapshot_shape(monkeypatch):
    import marketdata.satoshi_api as api

    monkeypatch.setattr(
        api.urllib.request, "urlopen",
        _fake_urlopen_factory({"product_id": "BTC-USD", "price": "100000"}),
    )
    snap = btc_sats_snapshot()
    assert snap["product_id"] == "BTC-USD"
    assert snap["price_usd"] == "100000"
    assert snap["usd_per_sat"] == "0.001"
    assert snap["sats_per_usd"] == "1000"
    assert snap["sats_per_btc"] == "100000000"
    assert isinstance(snap["fetched_at"], int)


def test_candles_passes_params(monkeypatch):
    import marketdata.satoshi_api as api

    seen = {}

    def _fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _FakeResp({"candles": [{"start": "1", "open": "2"}]})

    monkeypatch.setattr(api.urllib.request, "urlopen", _fake_urlopen)
    rows = PublicMarketData().candles("BTC-USD", start=1000, end=2000,
                                      granularity="ONE_HOUR")
    assert rows == [{"start": "1", "open": "2"}]
    assert "granularity=ONE_HOUR" in seen["url"]
    assert "start=1000" in seen["url"]


# ---------------------------------------------------------------------------
# ES256 JWT (generated throwaway key; signature verified with public key)
# ---------------------------------------------------------------------------

def _generate_ec_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode("utf-8")
    return pem, key


def test_build_jwt_claims_and_signature():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    pem, key = _generate_ec_pem()
    token = build_jwt("my-key-name", pem, "GET", "api.coinbase.com",
                      "/api/v3/brokerage/accounts")
    header_b64, payload_b64, sig_b64 = token.split(".")

    def _b64d(s):
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    header = json.loads(_b64d(header_b64))
    payload = json.loads(_b64d(payload_b64))
    assert header["alg"] == "ES256"
    assert header["typ"] == "JWT"
    assert header["kid"] == "my-key-name"
    assert "nonce" in header
    assert payload["iss"] == "cdp"
    assert payload["sub"] == "my-key-name"
    assert payload["uri"] == "GET api.coinbase.com/api/v3/brokerage/accounts"
    assert payload["exp"] - payload["nbf"] == 120

    # Verify the ES256 signature with the public key (JWS R||S -> DER)
    raw = _b64d(sig_b64)
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:], "big")
    der = utils.encode_dss_signature(r, s)
    key.public_key().verify(
        der, f"{header_b64}.{payload_b64}".encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )


def test_build_jwt_rejects_non_ec_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    bad = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = bad.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    with pytest.raises(CredentialsError):
        build_jwt("k", pem, "GET", "api.coinbase.com", "/x")


# ---------------------------------------------------------------------------
# Credential loading (never touches real secrets)
# ---------------------------------------------------------------------------

def test_load_cdp_credentials_from_file(tmp_path, monkeypatch):
    pem, _ = _generate_ec_pem()
    key_file = tmp_path / "cdp_api_key.json"
    key_file.write_text(json.dumps({"name": "test-key-id", "privateKey": pem}))
    monkeypatch.setenv("COINBASE_CDP_KEY_PATH", str(key_file))
    monkeypatch.delenv("COINBASE_CDP_KEY_NAME", raising=False)
    name, key = load_cdp_credentials()
    assert name == "test-key-id"
    assert "BEGIN EC PRIVATE KEY" in key


def test_load_cdp_credentials_from_env(monkeypatch):
    monkeypatch.delenv("COINBASE_CDP_KEY_PATH", raising=False)
    monkeypatch.setenv("COINBASE_CDP_KEY_NAME", "env-key-id")
    monkeypatch.setenv("COINBASE_CDP_PRIVATE_KEY", "PEM-BYTES")
    name, key = load_cdp_credentials()
    assert (name, key) == ("env-key-id", "PEM-BYTES")


def test_load_cdp_credentials_missing_raises(monkeypatch):
    monkeypatch.delenv("COINBASE_CDP_KEY_PATH", raising=False)
    monkeypatch.delenv("COINBASE_CDP_KEY_NAME", raising=False)
    monkeypatch.delenv("COINBASE_CDP_PRIVATE_KEY", raising=False)
    with pytest.raises(CredentialsError):
        load_cdp_credentials()


# ---------------------------------------------------------------------------
# Live-trading gating
# ---------------------------------------------------------------------------

def test_trading_inert_by_default(monkeypatch):
    monkeypatch.delenv("LEANTRADER_LIVE_TRADING", raising=False)
    client = CoinbaseBrokerageClient(key_name="k", private_key_pem="p")
    with pytest.raises(LiveTradingDisabledError):
        client.create_market_order("BTC-USD", "BUY", "0.001")
    with pytest.raises(LiveTradingDisabledError):
        client.cancel_order("some-order-id")


def test_trading_attempts_request_when_opted_in(monkeypatch):
    import marketdata.satoshi_api as api

    pem, _ = _generate_ec_pem()
    monkeypatch.setenv("LEANTRADER_LIVE_TRADING", "1")
    calls = {}

    def _fake_urlopen(req, timeout=None):
        calls["url"] = req.full_url
        calls["method"] = req.get_method()
        calls["auth"] = req.headers.get("Authorization", "")
        assert req.headers.get("Authorization", "").startswith("Bearer ")
        return _FakeResp({"success": True})

    monkeypatch.setattr(api.urllib.request, "urlopen", _fake_urlopen)
    client = CoinbaseBrokerageClient(key_name="k", private_key_pem=pem)
    out = client.create_market_order("BTC-USD", "BUY", "0.001")
    assert out == {"success": True}
    assert calls["method"] == "POST"
    assert calls["url"].endswith("/api/v3/brokerage/orders")


def test_authenticated_read_does_not_need_live_flag(monkeypatch):
    import marketdata.satoshi_api as api

    pem, _ = _generate_ec_pem()
    monkeypatch.delenv("LEANTRADER_LIVE_TRADING", raising=False)
    monkeypatch.setattr(
        api.urllib.request, "urlopen",
        _fake_urlopen_factory({"accounts": [{"currency": "BTC"}], "has_next": False}),
    )
    client = CoinbaseBrokerageClient(key_name="k", private_key_pem=pem)
    assert client.list_accounts() == [{"currency": "BTC"}]
