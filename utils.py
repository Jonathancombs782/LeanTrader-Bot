# utils.py
# Lean, shared utilities for LeanTrader scripts.
# Place this file in the project root so imports like
# `from utils import setup_logger, load_config, bps_to_frac, ensure_dir`
# work from any of the runners.

import os
import sys
import math
import logging
from pathlib import Path
from typing import Any, Dict

# Optional YAML support for config files.
# If pyyaml isn't installed, load_config() will still return {} gracefully.
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# -------------------------
# Filesystem helpers
# -------------------------
def ensure_dir(path: str | os.PathLike) -> None:
    """Create the directory (and parents) if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


# -------------------------
# Logging
# -------------------------
def setup_logger(name: str, level="INFO", log_dir="logs"):
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    # remove old handlers to avoid duplicates on reruns
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # file
    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    fh.setLevel(logger.level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # console (this is what you were missing)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logger.level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.propagate = False
    return logger



# -------------------------
# Config
# -------------------------
def load_config(path: str = "config.yml") -> Dict[str, Any]:
    """
    Load a YAML config file if present. Returns {} if file or PyYAML is missing.
    """
    p = Path(path)
    if not p.exists() or yaml is None:
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# -------------------------
# Math / conversions
# -------------------------
def bps_to_frac(bps: float | int) -> float:
    """
    Convert basis points to a fraction.
    Example: 10 bps -> 0.001 (i.e., 0.10%)
    """
    try:
        return float(bps) / 10_000.0
    except Exception:
        return 0.0


# -------------------------
# Misc small helpers
# -------------------------
def read_env_bool(key: str, default: bool = False) -> bool:
    """
    Read boolean-ish env var values like 'true', '1', 'yes'.
    """
    val = os.getenv(key)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "t", "yes", "y"}


def safe_float(x: Any, fallback: float = 0.0) -> float:
    """
    Convert to float safely, returning fallback on failure.
    """
    try:
        return float(x)
    except Exception:
        return fallback
