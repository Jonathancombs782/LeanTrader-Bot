# risk_guard.py
from __future__ import annotations

import json
import os as _os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

STATE_PATH = Path("runtime/risk_state.json")
# Ultra Pro tighter defaults (opt-in via env ULTRA_PRO_MODE=true)
_ULTRA = _os.getenv("ULTRA_PRO_MODE", "false").strip().lower() in ("1", "true", "yes")


def _read() -> Dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"dd_hit_at": 0, "equity_peak": None}


def _write(d: Dict):
    STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")


class RiskGuard:
    def __init__(
        self,
        max_positions: int = 6,
        max_per_symbol: int = 1,
        max_exposure_frac: float = 0.35,
        dd_limit_pct: float = 0.06,
        dd_pause_min: int = 60,
    ):
        if _ULTRA:
            # tighten defaults in Ultra Pro mode unless explicitly overridden by caller
            max_positions = int(_os.getenv("ULTRA_MAX_POS", max_positions if max_positions else 6))
            max_per_symbol = int(_os.getenv("ULTRA_MAX_PER_SYMBOL", max_per_symbol if max_per_symbol else 1))
            max_exposure_frac = float(_os.getenv("ULTRA_MAX_EXPOSURE", 0.2))
            dd_limit_pct = float(_os.getenv("ULTRA_DD_LIMIT", 0.04))
            dd_pause_min = int(_os.getenv("ULTRA_DD_PAUSE_MIN", 120))
        self.max_positions = max_positions
        self.max_per_symbol = max_per_symbol
        self.max_exposure_frac = max_exposure_frac
        self.dd_limit_pct = dd_limit_pct
        self.dd_pause_min = dd_pause_min

    def can_trade(self, equity: float, exposure: float, open_total: int, open_for_symbol: int) -> bool:
        st = _read()
        now = time.time()
        # enforce DD pause
        if now - st.get("dd_hit_at", 0) < self.dd_pause_min * 60:
            return False
        # exposure & count caps
        if open_total >= self.max_positions:
            return False
        if open_for_symbol >= self.max_per_symbol:
            return False
        if exposure >= equity * self.max_exposure_frac:
            return False
        return True

    def update_peak_and_check_dd(self, equity: float) -> bool:
        """
        Track equity peak; return True if DD breach (and sets pause window).
        """
        st = _read()
        peak = st.get("equity_peak")
        if peak is None or equity > peak:
            st["equity_peak"] = float(equity)
            _write(st)
            return False
        drop = 0.0 if peak <= 0 else (peak - equity) / peak
        if drop >= self.dd_limit_pct:
            st["dd_hit_at"] = time.time()
            _write(st)
            return True
        return False

    def lift_pause(self):
        st = _read()
        st["dd_hit_at"] = 0
        _write(st)


# Compatibility shims -------------------------------------------------------


@dataclass
class RiskConfig:
    max_order_usd: float = 5.0
    max_positions: int = 6
    max_per_symbol: int = 1
    max_exposure_frac: float = 0.35
    dd_limit_pct: float = 0.06
    dd_pause_min: int = 60


class RiskManager:
    """Thin compatibility wrapper exposing the methods expected by older
    modules (allow_trade, size_spot, allow_trade) while delegating to the
    newer RiskGuard where appropriate.
    """

    def __init__(self, router=None, cfg: RiskConfig | None = None):
        self.router = router
        self.cfg = cfg or RiskConfig()
        self._guard = RiskGuard(
            max_positions=self.cfg.max_positions,
            max_per_symbol=self.cfg.max_per_symbol,
            max_exposure_frac=self.cfg.max_exposure_frac,
            dd_limit_pct=self.cfg.dd_limit_pct,
            dd_pause_min=self.cfg.dd_pause_min,
        )

    def allow_trade(self, symbol: str, side: str) -> dict:
        """Return a dict like {'ok': True} or {'ok': False, 'reason': '...'}"""
        try:
            # In paper/demo mode, perform lightweight checks only
            ok = self._guard.can_trade(10000.0, 0.0, 0, 0)
            return {"ok": bool(ok), "reason": "ok" if ok else "paused-dd"}
        except Exception:
            return {"ok": True, "reason": "allow_fallback"}

    def size_spot(self, symbol: str) -> float:
        # Return a naive size estimator based on cfg.max_order_usd; router
        # may be None during unit tests, so keep simple.
        try:
            usd = float(getattr(self.cfg, "max_order_usd", 5.0))
            return max(0.0, usd / 1000.0)
        except Exception:
            return 0.001


# Import-time trace to help diagnose supervisor child import issues
try:
    print(
        f"[risk_guard] imported: RiskConfig={hasattr(__import__(__name__), 'RiskConfig')} RiskManager={hasattr(__import__(__name__), 'RiskManager')} file={__file__}"
    )
except Exception:
    # Best-effort; avoid raising during import
    pass
