from __future__ import annotations

import numpy as np
import pandas as pd

from features.validation import validate_features, FeatureValidationError


def test_nan_inf_detection_raises():
    df = pd.DataFrame({"A": [1.0, np.nan, 1.2], "B": [1.0, 1.1, np.inf]})
    try:
        validate_features(df)
        assert False, "expected FeatureValidationError"
    except FeatureValidationError:
        pass


def test_returns_out_of_bounds_flag():
    # returns-like input with an outlier
    df = pd.DataFrame({"A": [0.0, 0.6, 0.0]})
    res = validate_features(df, max_abs_return=0.5)
    assert isinstance(res, dict)
    assert res["ok"] is False or ("returns_out_of_bounds" in res.get("issues", []))

