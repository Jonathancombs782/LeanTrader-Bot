import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from ..utils.crypto import decrypt_str, encrypt_str

STORE_DIR = Path(os.getenv("STORE_DIR", "data/store"))
STORE_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = STORE_DIR / "users.json"

_lock = threading.Lock()


@dataclass
class UserProfile:
    user_id: str
    display_name: str = ""
    # Broker credentials (encrypted at rest)
    fx_api_key: str = ""
    fx_api_secret: str = ""
    ccxt_api_key: str = ""
    ccxt_api_secret: str = ""
    # Preferences
    base_currency: str = "USD"

    def to_public(self) -> Dict[str, Any]:
        d = asdict(self)
        # redact secrets
        for k in ["fx_api_key", "fx_api_secret", "ccxt_api_key", "ccxt_api_secret"]:
            if d.get(k):
                d[k] = "***"
        return d


def _read() -> Dict[str, Any]:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: Dict[str, Any]):
    USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def upsert_profile(p: UserProfile):
    with _lock:
        data = _read()
        data[p.user_id] = asdict(p)
        _write(data)


def get_profile(user_id: str) -> UserProfile | None:
    with _lock:
        data = _read()
        d = data.get(user_id)
        if not d:
            return None
        return UserProfile(**d)


def set_keys(
    user_id: str,
    fx_key: str | None = None,
    fx_secret: str | None = None,
    ccxt_key: str | None = None,
    ccxt_secret: str | None = None,
):
    with _lock:
        data = _read()
        d = data.get(user_id) or {"user_id": user_id}
        if fx_key is not None:
            d["fx_api_key"] = encrypt_str(fx_key)
        if fx_secret is not None:
            d["fx_api_secret"] = encrypt_str(fx_secret)
        if ccxt_key is not None:
            d["ccxt_api_key"] = encrypt_str(ccxt_key)
        if ccxt_secret is not None:
            d["ccxt_api_secret"] = encrypt_str(ccxt_secret)
        data[user_id] = d
        _write(data)


def get_keys(user_id: str) -> Dict[str, str]:
    with _lock:
        data = _read()
        d = data.get(user_id) or {}
        return {
            "fx_api_key": decrypt_str(d.get("fx_api_key", "")) if d.get("fx_api_key") else "",
            "fx_api_secret": decrypt_str(d.get("fx_api_secret", "")) if d.get("fx_api_secret") else "",
            "ccxt_api_key": decrypt_str(d.get("ccxt_api_key", "")) if d.get("ccxt_api_key") else "",
            "ccxt_api_secret": decrypt_str(d.get("ccxt_api_secret", "")) if d.get("ccxt_api_secret") else "",
        }
