# CDP signing helper (`cdp_client.py`)

A stdlib-only Python client for the Coinbase Developer Platform (CDP)
Platform API — it mints the ES256 JWTs CDP requires, on the machine that
holds the key. It exists because the platform's credential vault cannot
reproduce CDP's per-request signature on egress (the signature, not the
key, is what CDP checks), so the signing has to happen locally.

## How it works

CDP server keys authenticate with a **fresh ES256 JWT per request**
(Bearer header, 2-minute expiry, `kid` = key name, `uri` =
`<METHOD> <host><path>`). The JWT is signed with the key's EC private
key (P-256, ECDSA).

This module implements the whole chain with the Python standard library
only — no `cryptography`, no `ecdsa`, no `openssl` CLI:

- **P-256 curve arithmetic** (`_ec_add`, `_ec_mul`) — double-and-add
  scalar multiplication in affine coordinates.
- **ECDSA sign/verify** (`_ecdsa_sign`, `_ecdsa_verify`) — SHA-256 hash,
  random `k` from `secrets`, low-S normalisation, raw `r || s` (64-byte)
  JWS signature format.
- **Key parsing** (`parse_private_key_pem`) — a minimal DER reader for
  SEC1 (`BEGIN EC PRIVATE KEY`) and PKCS8 (`BEGIN PRIVATE KEY`) PEMs.
  Only P-256 keys are accepted (CDP ES256).
- **JWT minting** (`mint_jwt`) — header `{"alg": "ES256", "kid": key_name,
  "nonce": <random hex>, "typ": "JWT"}`, payload `{"sub": key_name,
  "iss": "cdp", "nbf": now, "exp": now + 120, "uri": "METHOD host/path"}`.
- **HTTP** (`CDPClient.request`) — stdlib `urllib`, one fresh JWT per call.

## Key storage

The key lives in a restricted file, never in source or chat:

- `~/workspace/cdp/cdp_api_key.json` — 600 perms, directory 700. This is
  the CDP key file (`{"name": ..., "privateKey": ...}`), moved out of the
  shared upload folder (`~/workspace/user/files/`) on 2026-11-10.
- The client also accepts `CDP_API_KEY_NAME` + `CDP_API_KEY_PRIVATE_KEY`
  environment variables, or a `CDP_API_KEY_FILE` path.
- The private key is never printed, logged, or included in an error
  message.

## Endpoints

The CDP **Platform** API base is `https://api.cdp.coinbase.com/platform`
(all paths prefixed `/v2/`). The plain `/v2/accounts` path belongs to the
separate Coinbase App API on `api.coinbase.com`, not this host — using it
against `api.cdp.coinbase.com` returns 404.

Read-only methods (by design — no fund movement):

- `list_accounts()` — `GET /platform/v2/evm/accounts` (project's EVM accounts)
- `get_account(address)` — `GET /platform/v2/evm/accounts/{address}`
- `get(path)` / `request(method, path, body=None)` — any other endpoint
  on the configured host. The client derives the JWT `uri` host from its
  `base_url`, so pointing it at `api.coinbase.com` also signs correctly
  for that host.

**There is no send / transfer / withdraw / trade method.** Moving money
needs Jonathan's explicit word and a separate, reviewed addition.

## Usage

```python
from cdp_client import CDPClient

client = CDPClient.from_env_or_file()   # env vars, else the key file
accounts = client.list_accounts()       # {'accounts': [...]}
```

## Self-test

```bash
python3 cdp_client.py --selftest
```

No real key needed. It checks:

1. Pure-Python sign + verify with a throwaway key.
2. OpenSSL cross-check — the signature this code produces is verified
   by `openssl dgst -sha256 -verify` (independent implementation).
3. JWT structure — header/payload claims (`alg`, `kid`, `nonce`, `sub`,
   `iss`, `nbf`, `exp` = `nbf` + 120, `uri`) and the signature.
4. Live call — a request to the real CDP API with a dummy key. Expected:
   HTTP 401 (the JWT is well-formed enough for CDP to evaluate it, and
   the dummy key is rejected).

Verified 2026-11-10: all four checks pass, and a read-only call with the
real key returned `{'accounts': []}` (0 EVM accounts — none created yet).

## Related

- `binance_client.py` — the same pattern (stdlib-only HMAC signing) for
  Binance. CDP needs ECDSA instead of HMAC, which is why this module
  carries its own curve code.
