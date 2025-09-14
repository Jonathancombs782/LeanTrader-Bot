from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict


_STATE_DIR = os.getenv("KV_STATE_DIR", os.path.join(".state"))
_KV_PATH = os.path.join(_STATE_DIR, "kv.json")
_KV_PATH_OLD = os.path.join("runtime", "kv.json")
_LOCK = threading.Lock()

try:  # optional cross-process lock
    import portalocker  # type: ignore
except Exception:  # pragma: no cover
    portalocker = None


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


@contextmanager
def _file_lock():
    if portalocker is None:
        with _LOCK:
            yield
    else:  # pragma: no cover
        _ensure_dir(_KV_PATH)
        lock_path = _KV_PATH + ".lock"
        with open(lock_path, "a+", encoding="utf-8") as lf:
            portalocker.lock(lf, portalocker.LOCK_EX)
            try:
                yield
            finally:
                try:
                    portalocker.unlock(lf)
                except Exception:
                    pass


def load_all() -> Dict[str, Any]:
    # Prefer new .state store; fallback to legacy runtime/kv.json
    with _file_lock():
        try:
            if os.path.exists(_KV_PATH):
                with open(_KV_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        try:
            if os.path.exists(_KV_PATH_OLD):
                with open(_KV_PATH_OLD, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}


def save_all(data: Dict[str, Any]) -> None:
    with _file_lock():
        _ensure_dir(_KV_PATH)
        with open(_KV_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def get(key: str, default: Any = None) -> Any:
    return load_all().get(key, default)


def set(key: str, value: Any) -> None:
    data = load_all()
    data[key] = value
    save_all(data)


# New API as requested
def get_kv(key: str, default: Any = None) -> Any:
    return get(key, default)


def set_kv(key: str, value: Any) -> None:
    set(key, value)


__all__ = [
    "get",
    "set",
    "get_kv",
    "set_kv",
    "load_all",
    "save_all",
]
