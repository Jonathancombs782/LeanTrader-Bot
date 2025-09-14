from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

STATE_PATH = Path(os.getenv("RISK_STATE_PATH", "runtime/risk_guard.json"))


def _read() -> Dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"dd_hit_at": 0, "equity_peak": None, "daily_loss": 0.0, "day": time.strftime("%Y-%m-%d")}


def _write(d: Dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


@dataclass
class GuardConfig:
    max_positions: int = 6
    max_per_symbol: int = 1
    max_exposure_frac: float = 0.35
    dd_limit_pct: float = 0.06
    dd_pause_min: int = 60
    daily_loss_stop: float = 0.08


class Guardrails:
    def __init__(self, cfg: GuardConfig | None = None):
        self.cfg = cfg or GuardConfig()

    def can_trade(self, equity: float, exposure: float, open_total: int, open_for_symbol: int) -> bool:
        st = _read()
        now = time.time()
        if now - st.get("dd_hit_at", 0) < self.cfg.dd_pause_min * 60:
            return False
        if open_total >= self.cfg.max_positions:
            return False
        if open_for_symbol >= self.cfg.max_per_symbol:
            return False
        if exposure >= equity * self.cfg.max_exposure_frac:
            return False
        # daily loss stop
        day = time.strftime("%Y-%m-%d")
        if st.get("day") != day:
            st["day"] = day
            st["daily_loss"] = 0.0
            _write(st)
        if st.get("daily_loss", 0.0) >= equity * self.cfg.daily_loss_stop:
            return False
        return True

    def update_peak_and_check_dd(self, equity: float) -> bool:
        st = _read()
        peak = st.get("equity_peak")
        if peak is None or equity > peak:
            st["equity_peak"] = float(equity)
            _write(st)
            return False
        drop = 0.0 if peak <= 0 else (peak - equity) / peak
        if drop >= self.cfg.dd_limit_pct:
            st["dd_hit_at"] = time.time()
            _write(st)
            return True
        return False
