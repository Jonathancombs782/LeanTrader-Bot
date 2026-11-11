"""Binance signing helper for LeanTrader-Bot.

Runs on Jonathan's own machine. Muse cannot sign Binance requests (the
secret never leaves the vault), so this file does the signing locally.

Keys come from the environment (or a local ``.env`` file in this folder).
NEVER paste keys into this file. NEVER commit a filled-in ``.env``.
The loader reads ``.env`` next to this script first, then a ``.env`` in
the current working directory — so running it from another directory can
pick up that directory's ``.env``. Prefer the copy next to the script.

    BINANCE_API_KEY=<your key>            # X-MBX-APIKEY header
    BINANCE_API_SECRET=<your secret>      # HMAC-SHA256 signing key
    # (BINANCE_SECRET_KEY is also accepted — the repo template uses that name)
    BINANCE_BASE_URL=https://api.binance.us   # default; see below

Base URL — pick the one matching the account the key was made on:
    Binance.US (US-based, default):  https://api.binance.us
    Binance.com:                     https://api.binance.com
    Spot testnet (no real money):    https://testnet.binance.vision

What it does:
    Public (no key): ping, server time, ticker price, klines, order book.
    Signed, READ-ONLY: account balances, open orders, order history.
    Live orders: OFF unless BINANCE_ALLOW_LIVE_ORDERS=1 is set in the
    environment. Paper-first: leave it off until you explicitly decide
    otherwise. There is NO withdrawal function in this file, on purpose.

Usage:
    python3 binance_client.py ping
    python3 binance_client.py price BTCUSDT
    python3 binance_client.py klines BTCUSDT --interval 1h --limit 5
    python3 binance_client.py account
    python3 binance_client.py orders BTCUSDT
    python3 binance_client.py selftest

Stdlib only — no pip installs needed.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "https://api.binance.us"
TESTNET_BASE_URL = "https://testnet.binance.vision"
RECV_WINDOW_MS = 5000
REQUEST_TIMEOUT_S = 20


class BinanceError(RuntimeError):
    """Binance returned an error payload (code + msg)."""

    def __init__(self, code, msg):
        self.code = code
        self.msg = msg
        super().__init__(f"Binance error {code}: {msg}")


# ---------------------------------------------------------------------------
# Config: keys from environment / .env, never from this file
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a .env file next to this script (or cwd).

    Only fills variables not already set in the environment. Lines starting
    with # are comments. Values may be quoted. A missing .env is fine.
    """
    for path in (
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return  # first .env found wins


_load_dotenv()


def _api_key() -> str:
    key = (os.getenv("BINANCE_API_KEY") or "").strip()
    if not key:
        raise BinanceError(0, "BINANCE_API_KEY is not set (env or .env)")
    return key


def _api_secret() -> str:
    secret = (os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY") or "").strip()
    if not secret:
        raise BinanceError(0, "BINANCE_API_SECRET (or BINANCE_SECRET_KEY) is not set (env or .env)")
    return secret


def _base_url() -> str:
    return (os.getenv("BINANCE_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")


# ---------------------------------------------------------------------------
# Signing + requests
# ---------------------------------------------------------------------------

def _sign(query_string: str, secret: str) -> str:
    """HMAC-SHA256 of the query string, hex-encoded. The secret is the key."""
    return hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def _request(method: str, path: str, params: dict | None = None, *, signed: bool = False):
    """One Binance REST call. Returns parsed JSON. Raises BinanceError."""
    params = dict(params or {})
    headers = {"User-Agent": "LeanTrader-Bot/binance_client"}
    url = _base_url() + path
    data = None

    if signed:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW_MS
        query = urllib.parse.urlencode(params)
        params["signature"] = _sign(query, _api_secret())
        headers["X-MBX-APIKEY"] = _api_key()
        query = urllib.parse.urlencode(params)
    else:
        query = urllib.parse.urlencode(params)

    if method == "GET":
        full_url = url + ("?" + query if query else "")
    else:
        full_url = url
        data = query.encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            raise BinanceError(exc.code, f"HTTP {exc.code} with no JSON body")
        code = payload.get("code", exc.code)
        msg = payload.get("msg", f"HTTP {exc.code}")
        hint = ""
        if code == -1021:
            hint = " (clock skew — sync this machine's clock)"
        elif code == -1022:
            hint = " (bad signature — wrong secret or wrong base URL for this key)"
        elif code == -2015:
            hint = " (invalid API key, or IP restriction blocking this machine)"
        raise BinanceError(code, msg + hint)
    except urllib.error.URLError as exc:
        raise BinanceError(0, f"network error reaching {_base_url()}: {exc.reason}")


# ---------------------------------------------------------------------------
# Public endpoints (no key needed)
# ---------------------------------------------------------------------------

def ping():
    return _request("GET", "/api/v3/ping")


def server_time():
    return _request("GET", "/api/v3/time")


def ticker_price(symbol: str):
    return _request("GET", "/api/v3/ticker/price", {"symbol": symbol.upper()})


def klines(symbol: str, interval: str = "1h", limit: int = 5):
    return _request("GET", "/api/v3/klines", {
        "symbol": symbol.upper(), "interval": interval, "limit": limit,
    })


def depth(symbol: str, limit: int = 5):
    return _request("GET", "/api/v3/depth", {"symbol": symbol.upper(), "limit": limit})


# ---------------------------------------------------------------------------
# Signed, read-only endpoints
# ---------------------------------------------------------------------------

def account():
    """Account balances. Returns only assets with a non-zero balance."""
    data = _request("GET", "/api/v3/account", signed=True)
    balances = [
        {"asset": b["asset"], "free": b["free"], "locked": b["locked"]}
        for b in data.get("balances", [])
        if float(b["free"]) > 0 or float(b["locked"]) > 0
    ]
    return {"balances": balances, "canTrade": data.get("canTrade"),
            "canWithdraw": data.get("canWithdraw"), "canDeposit": data.get("canDeposit")}


def open_orders(symbol: str | None = None):
    params = {"symbol": symbol.upper()} if symbol else {}
    return _request("GET", "/api/v3/openOrders", params, signed=True)


def all_orders(symbol: str, limit: int = 10):
    return _request("GET", "/api/v3/allOrders", {
        "symbol": symbol.upper(), "limit": limit,
    }, signed=True)


# ---------------------------------------------------------------------------
# Live orders — OFF unless explicitly enabled. Paper-first.
# ---------------------------------------------------------------------------

def place_order(symbol: str, side: str, quantity: str, price: str | None = None,
                order_type: str = "LIMIT"):
    """Place a REAL order. Requires BINANCE_ALLOW_LIVE_ORDERS=1 in the env.

    Defaults to LIMIT / GTC when a price is given, MARKET when it is not.
    Raises unless the gate env var is set — paper-first, on purpose.
    """
    if os.getenv("BINANCE_ALLOW_LIVE_ORDERS", "").strip() != "1":
        raise BinanceError(
            0,
            "live orders are OFF — set BINANCE_ALLOW_LIVE_ORDERS=1 to enable "
            "(paper-first: leave it off until you explicitly decide otherwise)",
        )
    print("WARNING: placing a REAL order on Binance — "
          f"{side} {quantity} {symbol.upper()} {order_type}"
          + (f" @ {price}" if price else ""), file=sys.stderr)
    params = {
        "symbol": symbol.upper(),
        "side": side.upper(),
        "type": order_type.upper(),
        "quantity": quantity,
    }
    if order_type.upper() == "LIMIT":
        if not price:
            raise BinanceError(0, "LIMIT orders need a price")
        params["price"] = price
        params["timeInForce"] = "GTC"
    return _request("POST", "/api/v3/order", params, signed=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print(obj) -> None:
    print(json.dumps(obj, indent=2))


def selftest() -> None:
    """Public checks (no key) + signed read-only check (only if keys are set)."""
    print(f"base URL: {_base_url()}")
    ping()
    print("ping: ok")
    t = server_time()
    print(f"server time: {t['serverTime']} (local: {int(time.time() * 1000)})")
    px = ticker_price("BTCUSDT")
    print(f"BTCUSDT: {px['price']}")
    if os.getenv("BINANCE_API_KEY") and (os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")):
        acct = account()
        print(f"account: ok — {len(acct['balances'])} non-zero balances, "
              f"canTrade={acct['canTrade']}, canWithdraw={acct['canWithdraw']}")
        for b in acct["balances"]:
            print(f"  {b['asset']}: free {b['free']} locked {b['locked']}")
    else:
        print("no keys set — signed check skipped (public checks passed)")
    print("selftest: PASS")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Binance signing helper (LeanTrader-Bot)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", help="public connectivity check")
    sub.add_parser("time", help="Binance server time")
    sub.add_parser("selftest", help="public checks + signed account check if keys are set")

    p = sub.add_parser("price", help="ticker price")
    p.add_argument("symbol")

    p = sub.add_parser("klines", help="candles")
    p.add_argument("symbol")
    p.add_argument("--interval", default="1h")
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("depth", help="order book top levels")
    p.add_argument("symbol")
    p.add_argument("--limit", type=int, default=5)

    sub.add_parser("account", help="signed: non-zero balances")
    p = sub.add_parser("orders", help="signed: open orders")
    p.add_argument("symbol", nargs="?")
    p = sub.add_parser("allorders", help="signed: order history")
    p.add_argument("symbol")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("order", help="REAL order — needs BINANCE_ALLOW_LIVE_ORDERS=1")
    p.add_argument("symbol")
    p.add_argument("side", choices=["BUY", "SELL"])
    p.add_argument("quantity")
    p.add_argument("--price", default=None)
    p.add_argument("--type", default="LIMIT", choices=["LIMIT", "MARKET"])

    args = parser.parse_args(argv)
    try:
        if args.cmd == "ping":
            _print(ping())
        elif args.cmd == "time":
            _print(server_time())
        elif args.cmd == "selftest":
            selftest()
        elif args.cmd == "price":
            _print(ticker_price(args.symbol))
        elif args.cmd == "klines":
            _print(klines(args.symbol, args.interval, args.limit))
        elif args.cmd == "depth":
            _print(depth(args.symbol, args.limit))
        elif args.cmd == "account":
            _print(account())
        elif args.cmd == "orders":
            _print(open_orders(args.symbol))
        elif args.cmd == "allorders":
            _print(all_orders(args.symbol, args.limit))
        elif args.cmd == "order":
            _print(place_order(args.symbol, args.side, args.quantity,
                               args.price, args.type))
    except BinanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
