from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Tuple

from .metrics import Trade, write_trade

STATE = Path(os.getenv("LEARN_STATE_PATH", "runtime/learn_state.json"))


def _load() -> Dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "weights": {"session_tokyo": 1.0, "session_london": 1.0, "session_ny": 1.0},
            "tp_mult": {},
            "sl_mult": {},
        }


def _save(d: Dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def update_after_trade(symbol: str, side: str, r_mult: float, session: str) -> Dict:
    write_trade(Trade(ts=int(time.time()), symbol=symbol, side=side, r_mult=r_mult))
    st = _load()
    w = st.setdefault("weights", {})
    key = f"session_{session}"
    cur = float(w.get(key, 1.0))
    # bandit-like: push weight slightly toward outcome
    w[key] = max(0.5, min(2.0, cur + 0.05 * (1.0 if r_mult > 0 else -1.0)))
    # TP/SL tuning per (symbol, session)
    (tp_map, sl_map) = (st.setdefault("tp_mult", {}), st.setdefault("sl_mult", {}))
    tp_key = f"{symbol}|{session}"
    sl_key = tp_key
    tp_val = float(tp_map.get(tp_key, 1.0))
    sl_val = float(sl_map.get(sl_key, 1.0))
    # if win, allow slightly higher TP multiple and tighter SL; else the opposite
    if r_mult > 0:
        tp_val = min(3.0, tp_val + 0.05)
        sl_val = max(0.5, sl_val - 0.03)
    else:
        tp_val = max(0.8, tp_val - 0.05)
        sl_val = min(2.0, sl_val + 0.03)
    tp_map[tp_key] = tp_val
    sl_map[sl_key] = sl_val
    _save(st)
    return st


def get_tuned_multipliers(symbol: str, session: str) -> Tuple[float, float]:
    """Return (tp_mult, sl_mult) learned for symbol+session.

    Defaults to (1.0, 1.0) if unavailable.
    """
    st = _load()
    tp = float(st.get("tp_mult", {}).get(f"{symbol}|{session}", 1.0))
    sl = float(st.get("sl_mult", {}).get(f"{symbol}|{session}", 1.0))
    return (tp, sl)
