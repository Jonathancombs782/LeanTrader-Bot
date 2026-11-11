#!/usr/bin/env python3
"""Coinbase Developer Platform (CDP) signing helper — stdlib only.

CDP authenticates server API calls with a fresh ES256 JWT minted from the
API key's EC private key (Bearer header, 2-minute expiry, ``kid`` = key
name, ``uri`` = ``<METHOD> <host><path>``). The platform's credential
vault cannot mint that signature on egress, so the signing has to happen
on Jonathan's own machine — this module does it with the Python standard
library only (no ``cryptography`` package, no ``ecdsa`` package, no
``openssl`` CLI dependency): the P-256 curve arithmetic and the SEC1/PKCS8
key parsing are implemented in pure Python below.

Safety rules (same posture as binance_client.py):
- Keys come from environment variables or a restricted key file only.
  Never paste a key into source, a chat message, or a log.
- Every request mints a FRESH JWT (new nonce, 2-minute expiry). A
  captured token is useless after 2 minutes.
- This client has NO fund-movement methods by design: no send, no
  transfer, no withdraw, no trade. It reads (accounts, balances) and can
  mint tokens for other read calls. Moving money needs Jonathan's explicit
  word and a separate, reviewed addition.
- The private key is never printed, logged, or included in an error
  message.

Key sources (in order):
- ``CDP_API_KEY_NAME`` + ``CDP_API_KEY_PRIVATE_KEY`` environment variables
  (the private key as a PEM string), or
- ``CDP_API_KEY_FILE`` — a JSON file ``{"name": ..., "privateKey": ...}``
  (the format CDP downloads), or
- the default key file ``~/workspace/cdp/cdp_api_key.json`` (600 perms).

Usage:
    from cdp_client import CDPClient
    client = CDPClient.from_env_or_file()
    accounts = client.list_accounts()  # GET /platform/v2/evm/accounts

Self-test (no real key needed — uses a throwaway test key):
    python3 cdp_client.py --selftest
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.cdp.coinbase.com"
DEFAULT_HOST = "api.cdp.coinbase.com"
DEFAULT_KEY_FILE = os.path.expanduser("~/workspace/cdp/cdp_api_key.json")
JWT_TTL_SECONDS = 120  # CDP JWTs expire 2 minutes after minting.


class CDPError(Exception):
    """An error returned by the CDP API (or a local signing failure)."""

    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# P-256 (secp256r1) elliptic-curve arithmetic — pure Python, stdlib only.
# Parameters are the standard NIST P-256 constants (FIPS 186-4).
# ---------------------------------------------------------------------------

_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_G = (_GX, _GY)
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

_INF = None  # the point at infinity


def _ec_add(p1, p2):
    """Add two P-256 points (affine coordinates)."""
    if p1 is _INF:
        return p2
    if p2 is _INF:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return _INF
    if p1 == p2:
        # Point doubling: slope = (3*x^2 + a) / (2*y)
        m = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        # Point addition: slope = (y2 - y1) / (x2 - x1)
        m = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (m * m - x1 - x2) % _P
    y3 = (m * (x1 - x3) - y1) % _P
    return (x3, y3)


def _ec_mul(k, point=_G):
    """Scalar multiplication k * point (double-and-add)."""
    result = _INF
    addend = point
    while k:
        if k & 1:
            result = _ec_add(result, addend)
        addend = _ec_add(addend, addend)
        k >>= 1
    return result


def _ecdsa_sign(private_scalar, message):
    """Sign ``message`` (bytes) with a P-256 private scalar.

    Returns (r, s) as ints. The hash is SHA-256, the signature is the
    raw (r, s) pair (JWS ES256 format: r || s, 32 bytes each). ``s`` is
    normalised to the low half of the curve order.
    """
    e = int.from_bytes(hashlib.sha256(message).digest(), "big")
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r_point = _ec_mul(k)
        r = r_point[0] % _N
        if r == 0:
            continue
        s = (pow(k, -1, _N) * (e + r * private_scalar)) % _N
        if s == 0:
            continue
        if s > _N // 2:  # low-S normalisation
            s = _N - s
        return r, s


def _ecdsa_verify(public_point, message, r, s):
    """Verify an (r, s) ECDSA signature over ``message``. Returns bool."""
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, _N)
    u1 = (e * w) % _N
    u2 = (r * w) % _N
    point = _ec_add(_ec_mul(u1), _ec_mul(u2, public_point))
    if point is _INF:
        return False
    return point[0] % _N == r


def _raw_sig_to_der(r, s):
    """Encode a raw (r, s) pair as a DER SEQUENCE (for openssl checks)."""
    def _der_int(x):
        b = x.to_bytes((x.bit_length() + 7) // 8 or 1, "big")
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b

    body = _der_int(r) + _der_int(s)
    return b"\x30" + bytes([len(body)]) + body


# ---------------------------------------------------------------------------
# Key parsing — minimal DER reader for SEC1 ("BEGIN EC PRIVATE KEY") and
# PKCS8 ("BEGIN PRIVATE KEY") PEM files. Returns the private scalar (int)
# and the public point (x, y). The secret bytes are never logged.
# ---------------------------------------------------------------------------

def _read_tlv(data, offset):
    """Read one DER tag-length-value at ``offset``. Returns (tag, value, next)."""
    tag = data[offset]
    offset += 1
    length = data[offset]
    offset += 1
    if length & 0x80:
        nbytes = length & 0x7F
        length = int.from_bytes(data[offset:offset + nbytes], "big")
        offset += nbytes
    return tag, data[offset:offset + length], offset + length


def _der_children(data):
    """Parse the children of a DER SEQUENCE. Returns [(tag, value), ...]."""
    tag, body, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise CDPError("expected a DER SEQUENCE in the key")
    children = []
    offset = 0
    while offset < len(body):
        t, v, offset = _read_tlv(body, offset)
        children.append((t, v))
    return children


def _sec1_private_scalar(der):
    """Extract the private scalar from a SEC1 ECPrivateKey DER blob."""
    children = _der_children(der)
    # children: [INTEGER version, OCTET STRING private key, ...]
    for tag, value in children:
        if tag == 0x04:  # OCTET STRING — the 32-byte private scalar
            if len(value) != 32:
                raise CDPError("EC private key is not 32 bytes (not P-256)")
            return int.from_bytes(value, "big")
    raise CDPError("no private key found in the SEC1 structure")


def parse_private_key_pem(pem):
    """Parse an EC private key PEM. Returns (private_scalar, public_point).

    Accepts SEC1 ("BEGIN EC PRIVATE KEY") and PKCS8 ("BEGIN PRIVATE KEY")
    forms. Only P-256 keys are supported (CDP ES256).
    """
    if "EC PRIVATE KEY" in pem:
        kind = "sec1"
    elif "PRIVATE KEY" in pem:
        kind = "pkcs8"
    else:
        raise CDPError("unrecognised private key PEM (expected EC PRIVATE KEY)")
    lines = [ln.strip() for ln in pem.strip().splitlines()
             if ln.strip() and not ln.strip().startswith("-----")]
    der = base64.b64decode("".join(lines))
    if kind == "sec1":
        scalar = _sec1_private_scalar(der)
    else:
        # PKCS8: SEQUENCE { INTEGER 0, SEQUENCE { OID, OID },
        #                 OCTET STRING (SEC1 DER) }
        children = _der_children(der)
        inner = None
        for tag, value in children:
            if tag == 0x04:
                inner = value
        if inner is None:
            raise CDPError("no private key found in the PKCS8 structure")
        scalar = _sec1_private_scalar(inner)
    if not (1 <= scalar < _N):
        raise CDPError("private scalar out of range for P-256")
    public_point = _ec_mul(scalar)
    return scalar, public_point


# ---------------------------------------------------------------------------
# JWT minting (JWS ES256) — CDP server-key format.
# ---------------------------------------------------------------------------

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_jwt(key_name, private_scalar, method, host, path, now=None):
    """Mint a fresh CDP JWT for one request.

    Header:  {"alg": "ES256", "kid": key_name, "nonce": <random hex>,
              "typ": "JWT"}
    Payload: {"sub": key_name, "iss": "cdp", "nbf": now,
              "exp": now + 120, "uri": "<METHOD> <host><path>"}
    """
    now = int(now if now is not None else time.time())
    header = {"alg": "ES256", "kid": key_name,
              "nonce": secrets.token_hex(16), "typ": "JWT"}
    payload = {"sub": key_name, "iss": "cdp", "nbf": now,
               "exp": now + JWT_TTL_SECONDS,
               "uri": f"{method.upper()} {host}{path}"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    ).encode("ascii")
    r, s = _ecdsa_sign(private_scalar, signing_input)
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input.decode("ascii") + "." + _b64url(signature)


# ---------------------------------------------------------------------------
# HTTP client.
# ---------------------------------------------------------------------------

class CDPClient:
    """Minimal CDP REST client. Read-only by design (no fund movement)."""

    def __init__(self, key_name, private_key_pem,
                 base_url=DEFAULT_BASE_URL, timeout=30):
        self.key_name = key_name
        self.base_url = base_url.rstrip("/")
        self.host = self.base_url.split("://", 1)[-1].split("/", 1)[0]
        self.timeout = timeout
        self._scalar, self._public_point = parse_private_key_pem(private_key_pem)

    # -- key sources -------------------------------------------------------

    @classmethod
    def from_env(cls):
        """Build a client from CDP_API_KEY_NAME + CDP_API_KEY_PRIVATE_KEY."""
        name = os.environ.get("CDP_API_KEY_NAME")
        pem = os.environ.get("CDP_API_KEY_PRIVATE_KEY")
        if not name or not pem:
            raise CDPError(
                "CDP_API_KEY_NAME and CDP_API_KEY_PRIVATE_KEY are not both set")
        return cls(name, pem)

    @classmethod
    def from_key_file(cls, path=None):
        """Build a client from a CDP key JSON file {"name", "privateKey"}."""
        path = path or os.environ.get("CDP_API_KEY_FILE") or DEFAULT_KEY_FILE
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise CDPError(f"CDP key file not found: {path}")
        except json.JSONDecodeError as exc:
            raise CDPError(f"CDP key file is not valid JSON: {path} ({exc})")
        if not data.get("name") or not data.get("privateKey"):
            raise CDPError(
                f"CDP key file {path} is missing 'name' or 'privateKey'")
        return cls(data["name"], data["privateKey"])

    @classmethod
    def from_env_or_file(cls, path=None):
        """Env vars first, then the key file."""
        if os.environ.get("CDP_API_KEY_NAME") and os.environ.get("CDP_API_KEY_PRIVATE_KEY"):
            return cls.from_env()
        return cls.from_key_file(path)

    # -- requests ----------------------------------------------------------

    def _auth_header(self, method, path):
        token = mint_jwt(self.key_name, self._scalar, method, self.host, path)
        return {"Authorization": f"Bearer {token}"}

    def request(self, method, path, body=None):
        """One authenticated request. Returns the parsed JSON body.

        A fresh JWT is minted for every call (2-minute expiry, fresh nonce).
        """
        url = self.base_url + path
        headers = self._auth_header(method, path)
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                parsed = {"message": raw.decode(errors="replace")}
            raise CDPError(
                f"CDP API error {exc.code} on {method.upper()} {path}: "
                f"{parsed.get('message') or parsed}",
                status=exc.code, body=parsed)
        except urllib.error.URLError as exc:
            raise CDPError(f"CDP API unreachable ({exc.reason})")
        if not raw:
            return {}
        return json.loads(raw.decode())

    def get(self, path):
        return self.request("GET", path)

    # -- read-only endpoints ----------------------------------------------
    # CDP Platform API base: https://api.cdp.coinbase.com/platform, all
    # paths prefixed /v2/. (The plain /v2/accounts path belongs to the
    # separate Coinbase App API on api.coinbase.com, not this host.)

    def list_accounts(self):
        """GET /platform/v2/evm/accounts — the project's EVM accounts."""
        return self.get("/platform/v2/evm/accounts")

    def get_account(self, address):
        """GET /platform/v2/evm/accounts/{address}."""
        return self.get(f"/platform/v2/evm/accounts/{address}")


# ---------------------------------------------------------------------------
# Self-test (no real key needed).
# ---------------------------------------------------------------------------

def _selftest_crypto():
    """Sign with a throwaway key and verify it two independent ways."""
    # Throwaway key: a random P-256 scalar (never leaves this process).
    scalar = secrets.randbelow(_N - 1) + 1
    public = _ec_mul(scalar)
    message = b"cdp selftest signing input"
    r, s = _ecdsa_sign(scalar, message)
    ok_self = _ecdsa_verify(public, message, r, s)
    print(f"  pure-python sign+verify: {'ok' if ok_self else 'FAILED'}")
    if not ok_self:
        raise SystemExit("selftest failed: pure-python verification")

    # Cross-check against openssl: write the test key + signature to /tmp
    # and let openssl verify them (independent implementation).
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # Rebuild the key as a SEC1 PEM so openssl can read it.
        def _der_len(n):
            return bytes([n]) if n < 128 else bytes([0x81, n])

        priv = scalar.to_bytes(32, "big")
        pub = b"\x04" + public[0].to_bytes(32, "big") + public[1].to_bytes(32, "big")
        content = (
            b"\x02\x01\x01"
            + b"\x04\x20" + priv
            + b"\xa0\x0a\x06\x08\x2a\x86\x48\xce\x3d\x03\x01\x07"
            + b"\xa1" + _der_len(3 + len(pub)) + b"\x03" + _der_len(len(pub) + 1) + b"\x00" + pub
        )
        sec1 = b"\x30" + _der_len(len(content)) + content
        pem = ("-----BEGIN EC PRIVATE KEY-----\n"
               + base64.encodebytes(sec1).decode()
               + "-----END EC PRIVATE KEY-----\n")
        key_path = os.path.join(td, "key.pem")
        with open(key_path, "w") as fh:
            fh.write(pem)
        msg_path = os.path.join(td, "msg.txt")
        with open(msg_path, "wb") as fh:
            fh.write(message)
        der_sig = _raw_sig_to_der(r, s)
        sig_path = os.path.join(td, "sig.der")
        with open(sig_path, "wb") as fh:
            fh.write(der_sig)
        pub_path = os.path.join(td, "pub.pem")
        subprocess.run(["openssl", "ec", "-in", key_path, "-pubout",
                        "-out", pub_path],
                       check=True, capture_output=True)
        res = subprocess.run(["openssl", "dgst", "-sha256", "-verify",
                              pub_path, "-signature", sig_path, msg_path],
                             capture_output=True, text=True)
        ok_ossl = "Verified OK" in res.stdout
        print(f"  openssl cross-check: {'ok' if ok_ossl else 'FAILED'} "
              f"({res.stdout.strip() or res.stderr.strip()})")
        if not ok_ossl:
            raise SystemExit("selftest failed: openssl cross-check")

    # JWT structure: mint with the throwaway key, decode and check claims.
    token = mint_jwt("organizations/test/apiKeys/test-key", scalar,
                     "GET", DEFAULT_HOST, "/v2/accounts")
    parts = token.split(".")
    assert len(parts) == 3, "JWT must have 3 parts"
    hdr = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
    pay = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    sig = base64.urlsafe_b64decode(parts[2] + "==")
    assert hdr["alg"] == "ES256" and hdr["kid"] == "organizations/test/apiKeys/test-key"
    assert hdr["typ"] == "JWT" and len(hdr["nonce"]) == 32
    assert pay["iss"] == "cdp" and pay["sub"] == hdr["kid"]
    assert pay["uri"] == f"GET {DEFAULT_HOST}/v2/accounts"
    assert pay["exp"] - pay["nbf"] == JWT_TTL_SECONDS
    assert len(sig) == 64
    r2 = int.from_bytes(sig[:32], "big")
    s2 = int.from_bytes(sig[32:], "big")
    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    ok_jwt = _ecdsa_verify(public, signing_input, r2, s2)
    print(f"  JWT claims + signature: {'ok' if ok_jwt else 'FAILED'}")
    if not ok_jwt:
        raise SystemExit("selftest failed: JWT signature")


def _selftest_live():
    """Hit the real CDP API with a dummy key.

    Expected: a 401 auth error — the JWT is well-formed enough for CDP to
    evaluate it, and the dummy key is rejected. A network error or a 200
    would both be wrong.
    """
    dummy_pem = None
    # Build a dummy P-256 key (random scalar, valid shape, not a real key).
    scalar = secrets.randbelow(_N - 1) + 1
    public = _ec_mul(scalar)
    priv = scalar.to_bytes(32, "big")
    pub = b"\x04" + public[0].to_bytes(32, "big") + public[1].to_bytes(32, "big")
    sec1 = (
        b"\x30\x77\x02\x01\x01\x04\x20" + priv
        + b"\xa0\x0a\x06\x08\x2a\x86\x48\xce\x3d\x03\x01\x07"
        + b"\xa1\x44\x03\x42\x00" + pub
    )
    dummy_pem = ("-----BEGIN EC PRIVATE KEY-----\n"
                 + base64.encodebytes(sec1).decode()
                 + "-----END EC PRIVATE KEY-----\n")
    client = CDPClient("organizations/dummy/apiKeys/dummy", dummy_pem)
    try:
        client.list_accounts()
    except CDPError as exc:
        print(f"  live CDP call with dummy key: HTTP {exc.status} "
              f"({exc.body.get('message') if isinstance(exc.body, dict) else exc.body})")
        if exc.status == 401:
            print("  -> expected: dummy key rejected, JWT evaluated by CDP")
            return
        raise SystemExit(f"selftest failed: unexpected live status {exc.status}")
    raise SystemExit("selftest failed: dummy key was ACCEPTED (unexpected 200)")


def selftest():
    print("CDP signing helper self-test (stdlib only, no real key)")
    print("crypto:")
    _selftest_crypto()
    print("live:")
    _selftest_live()
    print("self-test PASSED")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
    else:
        print(__doc__)
        print("Usage: python3 cdp_client.py --selftest")
