from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Tuple

_ROOT = Path(os.getenv("STATE_DIR", ".state"))
_ROOT.mkdir(parents=True, exist_ok=True)
_TRADES = _ROOT / "perf_trades.jsonl"
_EQUITY = _ROOT / "equity.json"


class PerfTracker:
    def __init__(self, window: int = 200) -> None:
        self.window = int(max(10, window))
        self._cache: Dict[str, Deque[Tuple[float, float]]] = {}
        self._equity: float = self._load_equity()

    def _load_equity(self) -> float:
        try:
            if _EQUITY.exists():
                j = json.loads(_EQUITY.read_text(encoding="utf-8"))
                return float(j.get("equity", 0.0))
        except Exception:
            pass
        return 0.0

    def _save_equity(self) -> None:
        try:
            _EQUITY.write_text(json.dumps({"ts": int(time.time()), "equity": self._equity}), encoding="utf-8")
        except Exception:
            pass

    def current_equity(self) -> float:
        return float(self._equity or 0.0)

    def set_equity(self, equity: float) -> None:
        try:
            self._equity = float(equity)
        except Exception:
            self._equity = 0.0
        self._save_equity()

    def update_after_fill(self, symbol: str, win: bool, r_multiple: float) -> None:
        dq = self._cache.setdefault(symbol, deque(maxlen=self.window))
        dq.append((1.0 if win else 0.0, float(r_multiple)))
        # append to file for persistence
        try:
            with open(_TRADES, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": int(time.time()),
                    "symbol": symbol,
                    "win": bool(win),
                    "R": float(r_multiple),
                }) + "\n")
        except Exception:
            pass

    def _roll(self, symbol: str) -> Tuple[float, float]:
        dq = self._cache.get(symbol)
        if not dq:
            # best-effort: try to lazy-load last window from file
            try:
                if _TRADES.exists():
                    items = []
                    for line in _TRADES.open("r", encoding="utf-8"):
                        try:
                            j = json.loads(line)
                        except Exception:
                            continue
                        if j.get("symbol") == symbol:
                            items.append((1.0 if j.get("win") else 0.0, float(j.get("R", 0.0))))
                    dq = deque(items[-self.window :], maxlen=self.window)
                    self._cache[symbol] = dq
                else:
                    dq = deque(maxlen=self.window)
                    self._cache[symbol] = dq
            except Exception:
                dq = deque(maxlen=self.window)
                self._cache[symbol] = dq
        if not dq:
            return 0.5, 1.0
        wins = sum(1.0 for w, _ in dq if w > 0.0)
        wr = wins / max(1, len(dq))
        avgR = sum(r for _, r in dq) / max(1, len(dq))
        return float(wr), float(avgR)

    def get_roll_winrate(self, symbol: str) -> float:
        return self._roll(symbol)[0]

    def get_roll_payoff(self, symbol: str) -> float:
        return self._roll(symbol)[1]


# module-level singleton
_PT = PerfTracker()


def current_equity() -> float:
    return _PT.current_equity()


def set_equity(equity: float) -> None:
    _PT.set_equity(equity)


def get_roll_winrate(symbol: str) -> float:
    return _PT.get_roll_winrate(symbol)


def get_roll_payoff(symbol: str) -> float:
    return _PT.get_roll_payoff(symbol)


def update_after_fill(fill: Dict[str, Any]) -> None:
    try:
        sym = fill.get("symbol") or fill.get("market") or ""
        win = bool(fill.get("win", False))
        r = float(fill.get("R", 0.0))
        _PT.update_after_fill(sym, win, r)
    except Exception:
        pass

