from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict

from storage import kv


class StratPath(Enum):
    CLASSICAL = "classical"
    QUANTUM = "quantum"
    ENSEMBLE = "ensemble"


@dataclass
class EWMA:
    half_life: float = 5.0
    _v: float = 0.0
    _init: bool = False

    @property
    def alpha(self) -> float:
        # alpha for half-life h: exp(-ln2 / h) => decay per step; smoothing = 1 - decay
        try:
            h = max(1e-9, float(self.half_life))
            decay = math.exp(-math.log(2.0) / h)
            return 1.0 - decay
        except Exception:
            return 0.2

    def update(self, x: float) -> float:
        a = self.alpha
        if not self._init:
            self._v = float(x)
            self._init = True
        else:
            self._v = a * float(x) + (1.0 - a) * self._v
        return self._v

    def value(self) -> float:
        return float(self._v)


class BanditSelector:
    """Simple 3-armed bandit over CLASSICAL/QUANTUM/ENSEMBLE with EWMA rewards."""

    def __init__(self, key: str = "meta_selector", half_life: float = 5.0):
        self.key = key
        self.half_life = float(half_life)
        self.rewards: Dict[str, float] = kv.get(self.key, {}) or {}
        # initialize missing arms
        for arm in (p.value for p in StratPath):
            self.rewards.setdefault(arm, 0.0)

    def _save(self) -> None:
        kv.set(self.key, dict(self.rewards))

    def choose(self) -> StratPath:
        # argmax with stable tie-break: QUANTUM > ENSEMBLE > CLASSICAL by default order below
        order = [StratPath.QUANTUM, StratPath.ENSEMBLE, StratPath.CLASSICAL]
        best = max(order, key=lambda p: (self.rewards.get(p.value, 0.0), -order.index(p)))
        return best

    def update(self, path: StratPath, reward: float) -> None:
        name = path.value
        cur = float(self.rewards.get(name, 0.0))
        ew = EWMA(self.half_life, _v=cur, _init=True)
        new_v = ew.update(float(reward))
        self.rewards[name] = float(new_v)
        self._save()


def daily_reward(pnl: float, turnover: float, eps: float = 1e-6) -> float:
    # Penalty on churn via sqrt(turnover) so it's sublinear
    try:
        return float(pnl) / (eps + float(turnover) ** 0.5)
    except Exception:
        return 0.0


__all__ = ["StratPath", "EWMA", "BanditSelector", "daily_reward"]

