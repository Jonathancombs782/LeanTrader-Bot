from __future__ import annotations

from typing import Optional

from storage.kv import get_kv, set_kv


KEY = "ensemble_lambda_cap"


def set_lambda_cap(cap: float) -> None:
    set_kv(KEY, float(cap))


def get_lambda_cap(default: Optional[float] = None) -> Optional[float]:
    v = get_kv(KEY, None)
    try:
        return float(v) if v is not None else default
    except Exception:
        return default


def clear_lambda_cap() -> None:
    set_kv(KEY, None)


__all__ = ["set_lambda_cap", "get_lambda_cap", "clear_lambda_cap"]

