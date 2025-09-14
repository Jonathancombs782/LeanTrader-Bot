from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


try:
    from prometheus_client import Gauge  # type: ignore

    ATTRIBUTION_COMPONENT = Gauge(
        "attribution_component",
        "Daily PnL attribution per component (units of PnL)",
        ["component"],
    )
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

    ATTRIBUTION_COMPONENT = _Noop()  # type: ignore


def _normalize_series(x: Sequence[float] | None) -> List[float]:
    if not x:
        return []
    try:
        return [float(v) for v in x]
    except Exception:
        return []


def attribute_daily_pnl(
    pnl_series: Sequence[float],
    components: Mapping[str, Sequence[float]],
) -> Dict[str, float]:
    """Allocate PnL across components proportionally by absolute component activity.

    For each time t, allocate pnl[t] to component i by w_i(t) = |x_i(t)| / sum_j |x_j(t)|.
    This guarantees the sum of contributions equals total PnL and avoids overfitting.
    """
    pnl = _normalize_series(pnl_series)
    comp_vals: Dict[str, List[float]] = {k: _normalize_series(v) for k, v in components.items()}
    if not pnl or not comp_vals:
        return {k: 0.0 for k in components.keys()}

    T = min(len(pnl), *(len(v) for v in comp_vals.values()))
    if T <= 0:
        return {k: 0.0 for k in components.keys()}

    contr: Dict[str, float] = {k: 0.0 for k in comp_vals.keys()}
    for t in range(T):
        denom = 0.0
        for v in comp_vals.values():
            try:
                denom += abs(float(v[t]))
            except Exception:
                denom += 0.0
        if denom <= 0:
            # Even split when no activity/denom=0
            w = 1.0 / float(len(comp_vals))
            for k in comp_vals.keys():
                contr[k] += float(pnl[t]) * w
        else:
            for k, v in comp_vals.items():
                try:
                    w = abs(float(v[t])) / denom
                except Exception:
                    w = 0.0
                contr[k] += float(pnl[t]) * w

    # update metrics
    for k, v in contr.items():
        try:
            ATTRIBUTION_COMPONENT.labels(component=k).set(float(v))
        except Exception:
            pass
    return contr


def write_daily_attribution(
    date: str,
    pnl_series: Sequence[float],
    components: Mapping[str, Sequence[float]],
    out_dir: str = "reports/attribution",
) -> Dict[str, Any]:
    """Compute attribution and write JSON to reports/attribution/YYYY-MM-DD.json."""
    out = attribute_daily_pnl(pnl_series, components)
    total = float(sum(_normalize_series(pnl_series)))
    tops = sorted(out.items(), key=lambda kv: kv[1], reverse=True)
    negs = [kv for kv in tops if kv[1] < 0]
    tops_pos = [kv for kv in tops if kv[1] > 0]
    payload = {
        "date": date,
        "total_pnl": total,
        "contributions": out,
        "top_contributors": tops_pos[:5],
        "negative_drags": negs[:5],
    }
    p = Path(out_dir) / f"{date}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return payload


def load_daily_attribution(date: str, out_dir: str = "reports/attribution") -> Optional[Dict[str, Any]]:
    p = Path(out_dir) / f"{date}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


__all__ = [
    "ATTRIBUTION_COMPONENT",
    "attribute_daily_pnl",
    "write_daily_attribution",
    "load_daily_attribution",
]

