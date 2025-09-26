from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Dict

from strategies.meta_selector import StratPath


@dataclass
class LinUCB:
    d: int
    alpha: float = 1.0

    def __post_init__(self):
        self.A: Dict[StratPath, np.ndarray] = {a: np.eye(self.d) for a in StratPath}
        self.b: Dict[StratPath, np.ndarray] = {a: np.zeros((self.d, 1)) for a in StratPath}

    def choose(self, x: np.ndarray) -> StratPath:
        x = x.reshape(-1, 1)
        best_a = None
        best_u = -1e9
        for a in StratPath:
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv @ self.b[a]
            p = float((theta.T @ x) + self.alpha * np.sqrt(x.T @ A_inv @ x))
            if p > best_u:
                best_u = p
                best_a = a
        return best_a or StratPath.ENSEMBLE

    def update(self, a: StratPath, x: np.ndarray, r: float):
        x = x.reshape(-1, 1)
        self.A[a] = self.A[a] + x @ x.T
        self.b[a] = self.b[a] + float(r) * x


def features(regime: str, vol: float, spread: float, liquidity: float) -> np.ndarray:
    # simple one-hot for regime + normalized numeric feats
    r = (regime or "").lower()
    onehot = np.array([
        1.0 if r == "calm" else 0.0,
        1.0 if r == "storm" else 0.0,
        1.0 if r == "range" else 0.0,
    ])
    x = np.concatenate([onehot, np.array([vol, spread, liquidity], dtype=float)])
    return x


__all__ = ["LinUCB", "features"]

