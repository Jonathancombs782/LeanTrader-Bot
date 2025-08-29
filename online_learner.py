# online_learner.py
from __future__ import annotations
from pathlib import Path
import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier
from typing import Dict
from alpha_engines import AlphaRouter

import json

def reward_from_exit(symbol: str, timeframe: str, decision_votes: Dict[str,float], pnl_usd: float):
    """
    Call when a trade is closed; allocates reward to the strongest voter.
    """
    if not decision_votes:
        return
    top = max(decision_votes, key=lambda k: decision_votes[k])
    r = AlphaRouter()
    r.update_reliability(symbol, timeframe, top, reward=float(pnl_usd))


MODEL_PATH = Path("data") / "pattern_lr.pkl"
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

FEATURE_ORDER = ["ret1","ret3","ret5","atr","rsi","bb_bw","ema_slope"]

def _ensure():
    if MODEL_PATH.exists():
        try:
            return joblib.load(MODEL_PATH)
        except Exception:
            pass
    # Log-loss SGD (online logistic regression)
    clf = SGDClassifier(loss="log_loss", penalty="l2", alpha=1e-4, learning_rate="optimal", random_state=42)
    # Initialize classes for partial_fit
    X0 = np.zeros((1, len(FEATURE_ORDER)), dtype=float)
    y0 = np.array([0], dtype=int)
    clf.partial_fit(X0, y0, classes=np.array([0,1], dtype=int))
    joblib.dump(clf, MODEL_PATH)
    return clf

def predict_proba(feat_dict: dict) -> float:
    clf = _ensure()
    x = np.array([[feat_dict.get(k, 0.0) for k in FEATURE_ORDER]], dtype=float)
    try:
        p = clf.predict_proba(x)[0,1]
    except Exception:
        p = 0.5
    return float(p)

def update_from_feats(feat_dict: dict, win: bool):
    clf = _ensure()
    x = np.array([[feat_dict.get(k, 0.0) for k in FEATURE_ORDER]], dtype=float)
    y = np.array([1 if win else 0], dtype=int)
    clf.partial_fit(x, y)
    joblib.dump(clf, MODEL_PATH)

    # online_learner.py — safe no-op hooks so imports never break
def memorize_entry(symbol: str, row: Dict[str, Any]) -> None:
    # TODO: store features from entry for later training
    return

def reward_from_exit(symbol: str, pnl: float, row: dict | None = None) -> None:
    # TODO: store realized PnL outcome
    return

# online_learner.py