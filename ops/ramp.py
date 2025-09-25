from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Tuple

from storage import kv


class Mode(Enum):
    PAPER = "PAPER"
    TINY_PROD = "TINY_PROD"
    FULL_PROD = "FULL_PROD"


@dataclass
class RampPolicy:
    min_paper_days: int = 10
    min_tiny_days: int = 10
    max_drawdown_paper: float = 0.05
    max_drawdown_tiny: float = 0.03
    slippage_bps_max: float = 30.0
    reject_rate_max: float = 0.05


@dataclass
class RampState:
    mode: Mode = Mode.PAPER
    start_date: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    stats: Dict[str, float] = field(default_factory=lambda: dict(days=0.0, drawdown=0.0, slippage_bps_p90=0.0, reject_rate=0.0))

    def _days_in_mode(self) -> int:
        try:
            d0 = datetime.fromisoformat(self.start_date).date()
        except Exception:
            d0 = datetime.now(timezone.utc).date()
        today = datetime.now(timezone.utc).date()
        return (today - d0).days

    def consider_promotion(self, policy: RampPolicy) -> bool:
        days = int(self.stats.get("days", self._days_in_mode()))
        dd = float(self.stats.get("drawdown", 0.0))
        slip = float(self.stats.get("slippage_bps_p90", 0.0))
        rej = float(self.stats.get("reject_rate", 0.0))
        if self.mode == Mode.PAPER:
            return (days >= policy.min_paper_days) and (dd <= policy.max_drawdown_paper) and (slip <= policy.slippage_bps_max) and (rej <= policy.reject_rate_max)
        if self.mode == Mode.TINY_PROD:
            return (days >= policy.min_tiny_days) and (dd <= policy.max_drawdown_tiny) and (slip <= policy.slippage_bps_max) and (rej <= policy.reject_rate_max)
        return False

    def consider_rollback(self, policy: RampPolicy) -> Tuple[bool, str]:
        dd = float(self.stats.get("drawdown", 0.0))
        slip = float(self.stats.get("slippage_bps_p90", 0.0))
        rej = float(self.stats.get("reject_rate", 0.0))
        # For FULL_PROD and TINY_PROD, use tighter tiny limits
        dd_lim = policy.max_drawdown_tiny if self.mode != Mode.PAPER else policy.max_drawdown_paper
        if dd > dd_lim:
            return True, f"drawdown_exceeded:{dd:.4f}>{dd_lim:.4f}"
        if slip > policy.slippage_bps_max:
            return True, f"slippage_exceeded:{slip:.2f}>{policy.slippage_bps_max:.2f}"
        if rej > policy.reject_rate_max:
            return True, f"reject_rate_exceeded:{rej:.4f}>{policy.reject_rate_max:.4f}"
        return False, ""


KV_KEY_STATE = "ops_ramp_state"


def load_state() -> RampState:
    raw = kv.get(KV_KEY_STATE, None)
    if not raw:
        return RampState()
    try:
        m = Mode(raw.get("mode", Mode.PAPER.value)) if isinstance(raw, dict) else Mode.PAPER
        start = (raw.get("start_date") if isinstance(raw, dict) else None) or datetime.now(timezone.utc).date().isoformat()
        stats = (raw.get("stats") if isinstance(raw, dict) else {}) or {}
        return RampState(mode=m, start_date=start, stats=stats)
    except Exception:
        return RampState()


def save_state(st: RampState) -> None:
    kv.set(KV_KEY_STATE, {"mode": st.mode.value, "start_date": st.start_date, "stats": st.stats})


def promote(st: RampState) -> RampState:
    if st.mode == Mode.PAPER:
        st.mode = Mode.TINY_PROD
    elif st.mode == Mode.TINY_PROD:
        st.mode = Mode.FULL_PROD
    st.start_date = datetime.now(timezone.utc).date().isoformat()
    save_state(st)
    return st


def demote(st: RampState) -> RampState:
    if st.mode == Mode.FULL_PROD:
        st.mode = Mode.TINY_PROD
    elif st.mode == Mode.TINY_PROD:
        st.mode = Mode.PAPER
    st.start_date = datetime.now(timezone.utc).date().isoformat()
    save_state(st)
    return st


__all__ = [
    "Mode",
    "RampPolicy",
    "RampState",
    "load_state",
    "save_state",
    "promote",
    "demote",
]

