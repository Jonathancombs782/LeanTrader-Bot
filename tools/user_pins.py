"""Per-user PIN store.

Simple PBKDF2-HMAC backed PIN storage in `runtime/users.json`.
Provides generate_pin(user_id) and verify_pin(user_id, pin).

This is minimal and intended for small scale; for production use a secure KVS and proper secret handling.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "runtime" / "users.json"


def _load() -> Dict[str, Any]:
    try:
        if STORE.exists():
            return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(d: Dict[str, Any]) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _hash_pin(pin: str, salt: bytes) -> str:
    # use PBKDF2-HMAC-SHA256
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100_000)
    return dk.hex()


def generate_pin(user_id: str, length: int = 6) -> str:
    """Generate a numeric PIN, store its hash, and return the plain PIN once."""
    uid = str(user_id)
    pin = "".join(str(secrets.randbelow(10)) for _ in range(length))
    salt = secrets.token_bytes(16)
    ph = _hash_pin(pin, salt)
    d = _load()
    d[uid] = {
        "pin_hash": ph,
        "salt": salt.hex(),
        "created_at": int(time.time()),
        "active": True,
    }
    _save(d)
    return pin


def verify_pin(user_id: str, pin: str) -> bool:
    uid = str(user_id)
    d = _load()
    rec = d.get(uid)
    if not rec or not rec.get("active", False):
        return False
    try:
        salt = bytes.fromhex(rec.get("salt", ""))
        expected = rec.get("pin_hash", "")
        return _hash_pin(pin, salt) == expected
    except Exception:
        return False


def revoke_pin(user_id: str) -> None:
    uid = str(user_id)
    d = _load()
    if uid in d:
        d[uid]["active"] = False
        _save(d)


if __name__ == "__main__":
    import sys

    # CLI: generate, list, revoke
    if len(sys.argv) < 2:
        print("Usage: python tools/user_pins.py generate|list|revoke <user_id>")
        raise SystemExit(2)
    cmd = sys.argv[1]
    if cmd == "list":
        data = _load()
        for k, v in data.items():
            print(k, "active=" + str(v.get("active", True)), "created=" + str(v.get("created_at")))
        raise SystemExit(0)
    if cmd == "revoke":
        if len(sys.argv) < 3:
            print("Usage: python tools/user_pins.py revoke <user_id>")
            raise SystemExit(2)
        revoke_pin(sys.argv[2])
        print("revoked")
        raise SystemExit(0)
    if cmd == "generate":
        if len(sys.argv) < 3:
            print("Usage: python tools/user_pins.py generate <user_id>")
            raise SystemExit(2)
        uid = sys.argv[2]
        pin = generate_pin(uid)
        print(f"Generated PIN for {uid}: {pin}")
        raise SystemExit(0)
    print("Unknown command")
    raise SystemExit(2)
