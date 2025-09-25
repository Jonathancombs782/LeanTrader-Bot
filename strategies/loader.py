"""Simple strategy plugin loader.

Registers available strategy plugins and loads their YAML configs.

Usage:
    from strategies.loader import create_from_env
    strat = create_from_env(broker, marketdata, logger, metrics)
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from pathlib import Path
import importlib.util

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore


@dataclass(frozen=True)
class PluginSpec:
    name: str
    class_path: str
    default_config: str


REGISTRY: Dict[str, PluginSpec] = {
    # id -> spec
    "ratio_arb": PluginSpec(
        name="ratio_arb",
        class_path="strategies.ratio_arb.strategy.SolBtcRatioArb",
        default_config="strategies/ratio_arb/config.yaml",
    ),
}


def _import_by_path(path: str) -> Callable[..., Any]:
    mod_name, _, cls_name = path.rpartition(".")
    if not mod_name or not cls_name:
        raise ImportError(f"invalid class path: {path}")
    mod = importlib.import_module(mod_name)
    try:
        return getattr(mod, cls_name)
    except AttributeError as e:
        raise ImportError(f"class {cls_name} not found in module {mod_name}") from e


def _load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load strategy configs (pip install pyyaml)")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(name: str, path: Optional[str] = None) -> Dict[str, Any]:
    """Load YAML config for a registered strategy.

    If path is not provided, uses the spec's default_config.
    """
    key = (name or "").strip().lower()
    spec = REGISTRY.get(key)
    if not spec:
        raise KeyError(f"strategy plugin not registered: {name}")
    cfg_path = path or spec.default_config
    return _load_yaml(cfg_path)


def create(
    name: str,
    broker: Any,
    marketdata: Any,
    logger: Any,
    metrics: Any,
    cfg_path: Optional[str] = None,
):
    """Instantiate a registered strategy with loaded YAML config."""
    key = (name or "").strip().lower()
    spec = REGISTRY.get(key)
    if not spec:
        raise KeyError(f"strategy plugin not registered: {name}")
    cfg = load_config(key, cfg_path)
    # Try normal import first
    try:
        klass = _import_by_path(spec.class_path)
    except Exception:
        # Fallback: load from runtime/strategies/<name>/strategy.py next to cfg
        cfgp = Path(cfg_path or spec.default_config)
        strat_py = cfgp.parent / "strategy.py"
        if strat_py.exists():
            spec_name = f"runtime_strategies_{key}"
            mspec = importlib.util.spec_from_file_location(spec_name, str(strat_py))
            if mspec and mspec.loader:
                module = importlib.util.module_from_spec(mspec)
                mspec.loader.exec_module(module)
                klass = getattr(module, "SolBtcRatioArb")
            else:
                raise ImportError(f"cannot load strategy module from {strat_py}")
        else:
            raise
    return klass(broker, marketdata, logger, metrics, cfg)


def create_from_env(broker: Any, marketdata: Any, logger: Any, metrics: Any):
    """Create a strategy instance from env vars STRATEGY_PLUGIN and STRATEGY_CONFIG."""
    name = os.getenv("STRATEGY_PLUGIN", "ratio_arb").strip().lower()
    cfg = os.getenv("STRATEGY_CONFIG", "").strip() or None
    return create(name, broker, marketdata, logger, metrics, cfg_path=cfg)
