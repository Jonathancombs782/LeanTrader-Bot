"""Optional dependency flags and helpers.

This module centralizes feature gating for heavy or optional libraries.
Always import these flags instead of importing the libraries at top-level
in business logic.
"""

from __future__ import annotations

from typing import Optional


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


TORCH_AVAILABLE = _has("torch")
TENSORFLOW_AVAILABLE = _has("tensorflow")
GYM_AVAILABLE = _has("gym")
SB3_AVAILABLE = _has("stable_baselines3")
TRANSFORMERS_AVAILABLE = _has("transformers")
KIVY_AVAILABLE = _has("kivy")
QISKIT_AVAILABLE = _has("qiskit")
OPENAI_AVAILABLE = _has("openai")
XGBOOST_AVAILABLE = _has("xgboost")
OPTUNA_AVAILABLE = _has("optuna")
PROM_AVAILABLE = _has("prometheus_client")
REDIS_AVAILABLE = _has("redis")


def check_or_raise(name: str, installed: bool, extra: Optional[str] = None) -> None:
    if not installed:
        hint = f" (pip install {extra})" if extra else ""
        raise RuntimeError(f"Optional dependency not installed: {name}{hint}")
