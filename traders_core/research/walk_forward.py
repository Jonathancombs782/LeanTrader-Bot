from __future__ import annotations
import os
import numpy as np, pandas as pd
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

def train_evaluate(...):
    # (unchanged core CV logic you pasted earlier)
    # ...
    model_id = save_model(symbol, timeframe, final, meta, models_dir)

    # === NEW: regime-specific models (optional) ===
    try:
        # Build regime labels over full history to train two “biased” models
        px = feats.index.to_series().map(lambda t: t)  # dummy to keep index
        reg = tag_regimes(df["close"], vol_window=120, calm_quantile=0.4).reindex(X.index)
        calm_idx  = reg == "calm"
        storm_idx = reg == "storm"
        if calm_idx.sum() > 200 and storm_idx.sum() > 200:
            # train two final models with same HP
            Mcalm  = GradientBoostingClassifier(learning_rate=best["lr"], max_depth=best["depth"]).fit(X[calm_idx],  y[calm_idx])
            Mstorm = GradientBoostingClassifier(learning_rate=best["lr"], max_depth=best["depth"]).fit(X[storm_idx], y[storm_idx])
            save_model_tagged(symbol, timeframe, "calm",  Mcalm,  {**meta, "regime":"calm"},  models_dir)
            save_model_tagged(symbol, timeframe, "storm", Mstorm, {**meta, "regime":"storm"}, models_dir)
    except Exception:
        pass
    # === END regime block ===

    ok = (
        best["metrics"]["oos_sharpe"] >= promotion_cfg["min_oos_sharpe"] and
        best["metrics"]["hit_rate"]   >= promotion_cfg["min_hit_rate"] and
        best["metrics"]["max_dd"]     >= promotion_cfg["max_drawdown"]
    )
    return {"model_id": model_id, "promote_ok": ok, "metrics": best["metrics"], "cv_acc": best["acc"]}

    # Train final on all history
    final = GradientBoostingClassifier(learning_rate=best["lr"], max_depth=best["depth"])
    final.fit(X, y)
    meta = {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon_bars": horizon_bars,
        "cv_acc": best["acc"],
        "metrics": best["metrics"],
        "features": list(X.columns),
    }
    model_id = save_model(symbol, timeframe, final, meta, models_dir)

    ok = (
        best["metrics"]["oos_sharpe"] >= promotion_cfg["min_oos_sharpe"] and
        best["metrics"]["hit_rate"]   >= promotion_cfg["min_hit_rate"] and
        best["metrics"]["max_dd"]     >= promotion_cfg["max_drawdown"]
    )
    return {"model_id": model_id, "promote_ok": ok, "metrics": best["metrics"], "cv_acc": best["acc"]}

def online_partial_fit(X: pd.DataFrame, y: pd.Series, prev: SGDClassifier | None = None) -> SGDClassifier:
    """Light online adapter you can call intraday on recent bars."""
    clf = prev or SGDClassifier(loss="log_loss", alpha=0.0001, learning_rate="optimal", max_iter=1, tol=None)
    # Ensure both classes seen
    if len(np.unique(y.values)) == 1:
        # fake one opposite sample to stabilize partial_fit
        X_aug = pd.concat([X, X.iloc[[0]]])
        y_aug = pd.concat([y, pd.Series([1 - y.iloc[0]], index=[y.index[0]])])
        clf.partial_fit(X_aug.values, y_aug.values, classes=np.array([0,1]))
    else:
        clf.partial_fit(X.values, y.values, classes=np.array([0,1]))
    return clf
