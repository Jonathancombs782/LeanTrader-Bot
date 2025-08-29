# risk_guard.py
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict

STATE_PATH = Path("runtime/risk_state.json")

def _read() -> Dict:
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except: return {"dd_hit_at": 0, "equity_peak": None}

def _write(d: Dict):
    STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")

class RiskGuard:
    def __init__(self,
                 max_positions:int=6,
                 max_per_symbol:int=1,
                 max_exposure_frac:float=0.35,
                 dd_limit_pct:float=0.06,
                 dd_pause_min:int=60):
        self.max_positions = max_positions
        self.max_per_symbol = max_per_symbol
        self.max_exposure_frac = max_exposure_frac
        self.dd_limit_pct = dd_limit_pct
        self.dd_pause_min = dd_pause_min

    def can_trade(self, equity: float, exposure: float,
                  open_total:int, open_for_symbol:int) -> bool:
        st = _read()
        now = time.time()
        # enforce DD pause
        if now - st.get("dd_hit_at", 0) < self.dd_pause_min * 60:
            return False
        # exposure & count caps
        if open_total >= self.max_positions: return False
        if open_for_symbol >= self.max_per_symbol: return False
        if exposure >= equity * self.max_exposure_frac: return False
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
