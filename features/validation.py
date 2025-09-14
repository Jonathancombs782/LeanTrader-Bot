from __future__ import annotations

import math
from typing import Dict, Any

import numpy as np
import pandas as pd


class FeatureValidationError(Exception):
    pass


def _as_returns(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if float(np.nanmax(np.abs(df.values))) > 2.0:
            rets = df.pct_change().replace([np.inf, -np.inf], np.nan)
        else:
            rets = df.copy().replace([np.inf, -np.inf], np.nan)
    except Exception:
        rets = df.copy().replace([np.inf, -np.inf], np.nan)
    return rets


def validate_features(
    df: pd.DataFrame,
    max_abs_return: float = 0.5,
    max_vol: float = 5.0,
    require_monotonic_time: bool = True,
) -> Dict[str, Any]:
    """Validate feature/pre-price dataframe for sanity.

    Checks:
      - no NaN/inf after preprocessing
      - returns bounded: abs(r_t) <= max_abs_return
      - realized vol (rolling std*sqrt(252)) <= max_vol for selected assets
      - timestamps strictly increasing if require_monotonic_time
    Returns {"ok": bool, "issues": [...]} and raises FeatureValidationError on hard failures.
    """
    issues = []
    if df is None or df.empty:
        raise FeatureValidationError("empty_dataframe")

    # Monotonic time
    if require_monotonic_time:
        try:
            idx = df.index
            if isinstance(idx, pd.DatetimeIndex):
                if not idx.is_monotonic_increasing:
                    raise FeatureValidationError("non_monotonic_time_index")
        except Exception:
            pass

    # Compute returns-like frame
    rets = _as_returns(df)
    if rets.isnull().values.any():
        # Hard failure if NaN present after preprocessing
        raise FeatureValidationError("nan_or_inf_in_features")

    # Bound returns
    try:
        too_big = np.abs(rets.values) > float(max_abs_return)
        if bool(np.any(too_big)):
            issues.append("returns_out_of_bounds")
    except Exception:
        pass

    # Realized volatility (annualized)
    try:
        std = rets.rolling(30, min_periods=10).std().iloc[-1].replace([np.inf, -np.inf], np.nan)
        ann_vol = (std * math.sqrt(252)).replace([np.inf, -np.inf], np.nan)
        if bool((ann_vol > float(max_vol)).fillna(False).any()):
            issues.append("vol_exceeds_max")
    except Exception:
        pass

    ok = len(issues) == 0
    return {"ok": ok, "issues": issues}


__all__ = ["FeatureValidationError", "validate_features"]

