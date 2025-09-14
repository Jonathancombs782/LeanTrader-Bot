from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


# --------- Optional libsodium (PyNaCl) backend ---------
try:
    from nacl.secret import SecretBox  # type: ignore
    from nacl.utils import random as nacl_random  # type: ignore

    _NACL = True
except Exception:  # pragma: no cover
    _NACL = False


RUNTIME = Path(os.getenv("VAULT_RUNTIME", "runtime"))
RUNTIME.mkdir(parents=True, exist_ok=True)
KEYSTORE = RUNTIME / "vault_keys.json"
KV_FILE = RUNTIME / "vault_kv.json"
CURRENT_KID_KEY = "vault:current_kid"


def _kv_get(k: str) -> Optional[str]:
    try:
        if 'REDIS_URL' in os.environ and os.environ['REDIS_URL'].strip():
            import redis  # type: ignore

            r = redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
            return r.get(k)
    except Exception:
        pass
    try:
        data = json.loads(KV_FILE.read_text(encoding="utf-8")) if KV_FILE.exists() else {}
        v = data.get(k)
        return str(v) if v is not None else None
    except Exception:
        return None


def _kv_set(k: str, v: str) -> None:
    try:
        if 'REDIS_URL' in os.environ and os.environ['REDIS_URL'].strip():
            import redis  # type: ignore

            r = redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
            r.set(k, v)
            return
    except Exception:
        pass
    try:
        data = json.loads(KV_FILE.read_text(encoding="utf-8")) if KV_FILE.exists() else {}
        data[k] = v
        KV_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_keystore() -> Dict[str, Any]:
    if KEYSTORE.exists():
        try:
            return json.loads(KEYSTORE.read_text(encoding="utf-8"))
        except Exception:
            return {"keys": {}, "current_kid": ""}
    return {"keys": {}, "current_kid": ""}


def _save_keystore(data: Dict[str, Any]) -> None:
    try:
        KEYSTORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def rotate_keys() -> str:
    """Generate a new symmetric key (SecretBox) and set as current; return kid."""
    ks = _load_keystore()
    kid = f"k{int(time.time())}"
    if _NACL:
        key = nacl_random(SecretBox.KEY_SIZE)
        ks.setdefault("keys", {})[kid] = base64.b64encode(key).decode("ascii")
    else:  # pragma: no cover
        # Fallback to a random 32-byte base64 string; used only if PyNaCl missing.
        key = os.urandom(32)
        ks.setdefault("keys", {})[kid] = base64.b64encode(key).decode("ascii")
    ks["current_kid"] = kid
    _save_keystore(ks)
    _kv_set(CURRENT_KID_KEY, kid)
    return kid


def _current_key() -> Tuple[str, bytes]:
    ks = _load_keystore()
    kid = _kv_get(CURRENT_KID_KEY) or ks.get("current_kid")
    if not kid:
        kid = rotate_keys()
        ks = _load_keystore()
    k64 = (ks.get("keys") or {}).get(kid)
    if not k64:
        # key not present locally, rotate
        kid = rotate_keys()
        ks = _load_keystore()
        k64 = (ks.get("keys") or {}).get(kid)
    key = base64.b64decode(k64.encode("ascii")) if k64 else os.urandom(32)
    return kid, key


def encrypt_log(content: Union[str, bytes], key: bytes) -> Dict[str, str]:
    """Encrypt content using libsodium SecretBox if available; returns dict {nonce,b64}.

    The ciphertext is base64 encoded. If PyNaCl is not available, this performs
    a reversible XOR with the key for development-only storage (not secure).
    """
    if isinstance(content, str):
        content_b = content.encode("utf-8")
    else:
        content_b = content

    if _NACL:
        box = SecretBox(key)
        nonce = nacl_random(SecretBox.NONCE_SIZE)
        ct = box.encrypt(content_b, nonce)  # includes nonce prefix; we also store nonce separately
        # SecretBox.encrypt returns nonce+ciphertext; extract ciphertext part
        ct_only = ct.ciphertext
        return {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ct_only).decode("ascii"),
            "alg": "nacl-secretbox",
        }
    # Fallback: weak XOR for dev; DO NOT use in prod.
    kb = key
    x = bytes([b ^ kb[i % len(kb)] for i, b in enumerate(content_b)])
    return {"nonce": "", "ciphertext": base64.b64encode(x).decode("ascii"), "alg": "xor-dev"}


def pqc_encrypt(content: Union[str, bytes]) -> Dict[str, str]:  # pragma: no cover
    """Placeholder for PQC (Kyber/Dilithium). Returns a descriptor for future migration."""
    if isinstance(content, str):
        content_b = content.encode("utf-8")
    else:
        content_b = content
    return {"alg": "pqc-tbd", "note": "placeholder", "ciphertext": base64.b64encode(content_b).decode("ascii")}


def secure_write(path: str, data: Union[str, bytes, Dict[str, Any]]) -> str:
    """Encrypt data with current key and write JSON envelope to path ('.enc' recommended)."""
    kid, key = _current_key()
    payload = data if isinstance(data, (bytes, str)) else json.dumps(data, ensure_ascii=False)
    enc = encrypt_log(payload, key)
    env = {"kid": kid, **enc}
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return str(out)


__all__ = ["encrypt_log", "pqc_encrypt", "secure_write", "rotate_keys"]

