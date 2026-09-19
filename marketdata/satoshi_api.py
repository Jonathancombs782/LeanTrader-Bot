"""Coinbase "satoshi API" for LeanTrader-Bot.

What this is
------------
A small, focused Coinbase Advanced Trade client with a satoshi-denominated
view of BTC:

* **Public market data (no API key needed):** BTC-USD spot price, product
  stats, best bid/ask, and candles, plus BTC <-> satoshi conversion helpers.
* **Authenticated endpoints (CDP API key needed):** account balances,
  product listing.
* **Trading endpoints exist but are inert by default.** ``create_market_order``
  / ``cancel_order`` raise :class:`LiveTradingDisabledError` unless the
  ``LEANTRADER_LIVE_TRADING=1`` environment flag is set explicitly by the
  operator. Read-only behaviour is the default and requires no flag.

Security rules (read these before touching credentials)
------------------------------------------------------
* NEVER read, print, log, or commit the CDP API key JSON. Credentials are
  referenced only through environment variables:

  - ``COINBASE_CDP_KEY_PATH`` — path to the CDP key JSON file
    (``{"name": "...", "privateKey": "-----BEGIN EC PRIVATE KEY-----\\n..."}``)
  - or ``COINBASE_CDP_KEY_NAME`` + ``COINBASE_CDP_PRIVATE_KEY`` (PEM text)

* The key filename pattern is in ``.gitignore`` — the key file must never be
  committed.
* JWTs are minted per-request with ES256 (P-256), header
  ``{"alg": "ES256", "typ": "JWT", "kid": <key name>, "nonce": <random>}`` and
  payload ``{"iss": "cdp", "sub": <key name>, "nbf", "exp", "uri"}`` where
  ``uri`` is ``"<METHOD> <host><path>"`` (Advanced Trade REST convention).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

API_BASE = "https://api.coinbase.com"
API_HOST = "api.coinbase.com"
BROKERAGE_PREFIX = "/api/v3/brokerage"

DEFAULT_PRODUCT = "BTC-USD"

SATS_PER_BTC = Decimal(100_000_000)

LIVE_TRADING_ENV = "LEANTRADER_LIVE_TRADING"
KEY_PATH_ENV = "COINBASE_CDP_KEY_PATH"
KEY_NAME_ENV = "COINBASE_CDP_KEY_NAME"
KEY_PRIVATE_ENV = "COINBASE_CDP_PRIVATE_KEY"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CoinbaseAPIError(RuntimeError):
    """Raised when the Coinbase HTTP API returns an error or bad payload."""


class LiveTradingDisabledError(RuntimeError):
    """Raised when a live-trading call is attempted without the opt-in flag."""


class CredentialsError(RuntimeError):
    """Raised when CDP credentials are missing or malformed."""


# ---------------------------------------------------------------------------
# Satoshi conversion helpers  ("satoshi" angle of this module)
# ---------------------------------------------------------------------------

def _to_decimal(value: Any, name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be numeric, got {value!r}") from exc
    return d


def btc_to_sats(btc_amount: Any) -> int:
    """Convert a BTC amount to whole satoshis (1 BTC = 100,000,000 sats)."""
    return int((_to_decimal(btc_amount, "btc_amount") * SATS_PER_BTC).to_integral_value())


def sats_to_btc(sats: Any) -> Decimal:
    """Convert whole satoshis to a BTC Decimal."""
    return _to_decimal(sats, "sats") / SATS_PER_BTC


def usd_per_sat(btc_usd_price: Any) -> Decimal:
    """Price of a single satoshi in USD, given the BTC/USD price."""
    price = _to_decimal(btc_usd_price, "btc_usd_price")
    if price <= 0:
        raise ValueError("btc_usd_price must be positive")
    return price / SATS_PER_BTC


def sats_per_usd(btc_usd_price: Any) -> Decimal:
    """How many satoshis one USD buys, given the BTC/USD price."""
    price = _to_decimal(btc_usd_price, "btc_usd_price")
    if price <= 0:
        raise ValueError("btc_usd_price must be positive")
    return SATS_PER_BTC / price


# ---------------------------------------------------------------------------
# Public (unauthenticated) market data
# ---------------------------------------------------------------------------

def _http_get(url: str, headers: Optional[Dict[str, str]] = None,
              timeout: float = 15.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {"Accept": "application/json",
                                                          "User-Agent": "leantrader-satoshi-api/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        raise CoinbaseAPIError(f"GET {url} -> HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise CoinbaseAPIError(f"GET {url} failed: {exc}") from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CoinbaseAPIError(f"GET {url} returned non-JSON payload") from exc
    if not isinstance(data, dict):
        raise CoinbaseAPIError(f"GET {url} returned unexpected payload shape")
    return data


@dataclass
class PublicMarketData:
    """Unauthenticated Coinbase Advanced Trade market-data client.

    All calls are read-only. No API key, no signature, no account access.
    """

    base_url: str = API_BASE
    timeout: float = 15.0

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        qs = ("?" + urllib.parse.urlencode(params)) if params else ""
        return _http_get(f"{self.base_url}{path}{qs}", timeout=self.timeout)

    # -- products ------------------------------------------------------
    def list_products(self, limit: int = 250,
                      product_type: str = "SPOT") -> List[Dict[str, Any]]:
        """List public trading products (paginated by the API)."""
        products: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"limit": min(limit, 250), "product_type": product_type}
            if cursor:
                params["offset"] = cursor
            data = self._get(f"{BROKERAGE_PREFIX}/market/products", params)
            products.extend(data.get("products", []))
            cursor = data.get("offset")
            if not cursor or len(products) >= limit:
                break
        return products[:limit]

    def product(self, product_id: str = DEFAULT_PRODUCT) -> Dict[str, Any]:
        """Public product snapshot incl. current ``price`` (quote currency)."""
        return self._get(f"{BROKERAGE_PREFIX}/market/products/{product_id}")

    def ticker(self, product_id: str = DEFAULT_PRODUCT,
               limit: int = 1) -> Dict[str, Any]:
        """Most recent public trades + best bid/ask for a product."""
        return self._get(
            f"{BROKERAGE_PREFIX}/market/products/{product_id}/ticker",
            {"limit": limit},
        )

    def best_bid_ask(self, product_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Best bid/ask across products (defaults to BTC-USD)."""
        params = {"product_ids": ",".join(product_ids or [DEFAULT_PRODUCT])}
        return self._get(f"{BROKERAGE_PREFIX}/market/best_bid_ask", params)

    def candles(self, product_id: str = DEFAULT_PRODUCT, start: int = 0,
                end: int = 0,
                granularity: str = "ONE_DAY") -> List[Dict[str, Any]]:
        """Public OHLCV candles.

        ``start``/``end`` are UNIX seconds. ``granularity`` is one of
        ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR,
        TWO_HOUR, FOUR_HOUR, SIX_HOUR, ONE_DAY.
        """
        if end <= 0:
            end = int(time.time())
        if start <= 0:
            start = end - 86400
        data = self._get(
            f"{BROKERAGE_PREFIX}/market/products/{product_id}/candles",
            {"start": str(start), "end": str(end), "granularity": granularity},
        )
        return data.get("candles", [])


def fetch_btc_price(client: Optional[PublicMarketData] = None,
                    product_id: str = DEFAULT_PRODUCT) -> Decimal:
    """Return the latest BTC price in USD as a Decimal (public endpoint)."""
    client = client or PublicMarketData()
    payload = client.product(product_id)
    price = payload.get("price")
    if price is None:
        raise CoinbaseAPIError(f"product {product_id} payload missing 'price'")
    return _to_decimal(price, "price")


def btc_sats_snapshot(client: Optional[PublicMarketData] = None,
                      product_id: str = DEFAULT_PRODUCT) -> Dict[str, Any]:
    """One dict strategies can consume: price + satoshi-denominated stats.

    Example keys: product_id, price_usd (str), usd_per_sat (str),
    sats_per_usd (str), fetched_at (unix seconds).
    """
    price = fetch_btc_price(client, product_id)
    return {
        "product_id": product_id,
        "price_usd": str(price),
        "usd_per_sat": str(usd_per_sat(price)),
        "sats_per_usd": str(sats_per_usd(price)),
        "sats_per_btc": str(SATS_PER_BTC),
        "fetched_at": int(time.time()),
    }


# ---------------------------------------------------------------------------
# CDP credentials + ES256 JWT (authenticated calls only)
# ---------------------------------------------------------------------------

def _read_key_file(path: str) -> Tuple[str, str]:
    """Read a CDP key JSON file. Returns (key_name, private_key_pem).

    The file must stay out of git (see .gitignore). Its contents are never
    logged or printed by this module.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise CredentialsError(
            f"CDP key file not found at {path} "
            f"(set {KEY_PATH_ENV} to its location)"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialsError(f"Could not parse CDP key file at {path}") from exc
    name = data.get("name")
    private_key = data.get("privateKey") or data.get("private_key")
    if not name or not private_key:
        raise CredentialsError(
            f"CDP key file at {path} must contain 'name' and 'privateKey'"
        )
    return str(name), str(private_key)


def load_cdp_credentials() -> Tuple[str, str]:
    """Resolve (key_name, private_key_pem) from the environment.

    Prefers ``COINBASE_CDP_KEY_PATH`` (JSON file); falls back to
    ``COINBASE_CDP_KEY_NAME`` + ``COINBASE_CDP_PRIVATE_KEY``.
    Raises :class:`CredentialsError` when nothing usable is configured.
    """
    key_path = os.environ.get(KEY_PATH_ENV, "").strip()
    if key_path:
        return _read_key_file(key_path)
    name = os.environ.get(KEY_NAME_ENV, "").strip()
    private_key = os.environ.get(KEY_PRIVATE_ENV, "").strip()
    if name and private_key:
        return name, private_key
    raise CredentialsError(
        "No CDP credentials configured. Set COINBASE_CDP_KEY_PATH to the key "
        f"JSON file, or {KEY_NAME_ENV} + {KEY_PRIVATE_ENV}."
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_jwt(key_name: str, private_key_pem: str, method: str,
              host: str, path: str, expires_in: int = 120) -> str:
    """Mint a fresh ES256 JWT for one Advanced Trade REST request.

    Header:  {"alg": "ES256", "typ": "JWT", "kid": <key name>, "nonce": <rand>}
    Payload: {"iss": "cdp", "sub": <key name>, "nbf", "exp",
              "uri": "<METHOD> <host><path>"}
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
    except ImportError as exc:
        raise CredentialsError(
            "The 'cryptography' package is required for JWT signing: "
            "pip install cryptography"
        ) from exc

    try:
        key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
    except (ValueError, TypeError) as exc:
        raise CredentialsError(
            "Could not parse the CDP private key PEM "
            "(expected an EC P-256 key from portal.cdp.coinbase.com)"
        ) from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise CredentialsError(
            "CDP private key must be an EC P-256 (SECP256R1) key"
        )

    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": key_name,
        "nonce": secrets.token_hex(16),
    }
    now = int(time.time())
    payload = {
        "iss": "cdp",
        "sub": key_name,
        "nbf": now,
        "exp": now + int(expires_in),
        "uri": f"{method.upper()} {host}{path}",
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    der_sig = key.sign(signing_input.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input + "." + _b64url(raw_sig)


def live_trading_enabled() -> bool:
    """True only when the operator explicitly opts in via env flag."""
    return os.environ.get(LIVE_TRADING_ENV, "").strip() == "1"


def _require_live_trading() -> None:
    if not live_trading_enabled():
        raise LiveTradingDisabledError(
            "Live trading is DISABLED. Order placement/cancellation is inert "
            f"unless {LIVE_TRADING_ENV}=1 is set explicitly by the operator. "
            "Read-only endpoints remain available."
        )


@dataclass
class CoinbaseBrokerageClient:
    """Authenticated Coinbase Advanced Trade client.

    Read-only authenticated calls (balances, product listing) work with just
    CDP credentials. Order placement/cancellation additionally requires
    ``LEANTRADER_LIVE_TRADING=1`` — otherwise they raise instead of trading.
    """

    key_name: Optional[str] = None
    private_key_pem: Optional[str] = None
    base_url: str = API_BASE
    timeout: float = 15.0
    _creds: Tuple[str, str] = field(default=None, repr=False, init=False)  # type: ignore[assignment]

    def _credentials(self) -> Tuple[str, str]:
        if self._creds is None:
            if self.key_name and self.private_key_pem:
                self._creds = (self.key_name, self.private_key_pem)
            else:
                self._creds = load_cdp_credentials()
        return self._creds

    def _request(self, method: str, path: str,
                 body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        key_name, private_key = self._credentials()
        jwt = build_jwt(key_name, private_key, method, API_HOST, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method.upper(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {jwt}",
                "User-Agent": "leantrader-satoshi-api/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:500]
            except Exception:
                pass
            raise CoinbaseAPIError(
                f"{method.upper()} {path} -> HTTP {exc.code}: {detail}"
            ) from exc
        except OSError as exc:
            raise CoinbaseAPIError(f"{method.upper()} {path} failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise CoinbaseAPIError(f"{method.upper()} {path} unexpected payload")
        return payload

    # -- read-only authenticated --------------------------------------
    def list_accounts(self, limit: int = 250) -> List[Dict[str, Any]]:
        """List brokerage accounts with balances (read-only)."""
        accounts: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params = {"limit": str(min(limit, 250))}
            if cursor:
                params["cursor"] = cursor
            path = f"{BROKERAGE_PREFIX}/accounts?{urllib.parse.urlencode(params)}"
            data = self._request("GET", path)
            accounts.extend(data.get("accounts", []))
            cursor = data.get("cursor")
            if not cursor or not data.get("has_next") or len(accounts) >= limit:
                break
        return accounts[:limit]

    # -- trading (GATED) -----------------------------------------------
    def create_market_order(self, product_id: str, side: str,
                            size: str) -> Dict[str, Any]:
        """Place a market order. INERT unless LEANTRADER_LIVE_TRADING=1."""
        _require_live_trading()
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be 'BUY' or 'SELL'")
        body = {
            "client_order_id": secrets.token_hex(16),
            "product_id": product_id,
            "side": side,
            "order_configuration": {"market_market_ioc": {"base_size": str(size)}},
        }
        return self._request("POST", f"{BROKERAGE_PREFIX}/orders", body)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order. INERT unless LEANTRADER_LIVE_TRADING=1."""
        _require_live_trading()
        body = {"order_ids": [order_id]}
        return self._request("POST", f"{BROKERAGE_PREFIX}/orders/batch_cancel", body)
