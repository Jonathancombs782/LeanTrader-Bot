from __future__ import annotations

import os
import numpy as np
import pandas as pd

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score

from traders_core.mt5_adapter import copy_rates_days
from traders_core.features.pipeline import rates_to_df, make_features, build_xy
from traders_core.storage.registry import save_model, save_model_tagged
from traders_core.risk.gates import compute_metrics
from traders_core.research.cv import PurgedKFold

def _apply_tcost(returns: pd.Series, side: pd.Series, bps: float) -> pd.Series:
    """Subtract costs when we flip from flat->long or long->flat (entry/exit).
       bps = cost in basis points roundtrip (applied half on entry, half on exit)."""
    side = side.fillna(0).astype(int)
    flips = side.diff().fillna(0).ne(0)  # entries/exits
    per_leg = (bps / 10000.0) / 2.0
    cost = flips.astype(float) * per_leg
    # cost deducted as negative returns on those bars
    return returns - cost

def train_evaluate(*args, **kwargs):
    """Placeholder for the train/evaluate routine.

    The original implementation contained a large, inlined CV and training
    logic that was partially pasted and caused a SyntaxError during import.
    Replace with a stub to keep the module importable; call sites should be
    updated to use a fully implemented function.
    """
    raise NotImplementedError("train_evaluate is not implemented in this branch")

def online_partial_fit(
    X: pd.DataFrame, y: pd.Series, prev: SGDClassifier | None = None
) -> SGDClassifier:
    """Light online adapter you can call intraday on recent bars."""
    clf = (
        prev
        or SGDClassifier(
            loss="log_loss",
            alpha=0.0001,
            learning_rate="optimal",
            max_iter=1,
            tol=None,
        )
    )
    # Ensure both classes seen
    if len(np.unique(y.values)) == 1:
        # fake one opposite sample to stabilize partial_fit
        X_aug = pd.concat([X, X.iloc[[0]]])
        y_aug = pd.concat([y, pd.Series([1 - y.iloc[0]], index=[y.index[0]])])
        clf.partial_fit(X_aug.values, y_aug.values, classes=np.array([0,1]))
    else:
        clf.partial_fit(X.values, y.values, classes=np.array([0,1]))
    return clf
