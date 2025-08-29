# dashboard_reporter.py
from __future__ import annotations
import time, math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from cross_examiner import cross_examine
from notifier import TelegramNotifier
from pathlib import Path
import json

DASH = Path("runtime"); DASH.mkdir(exist_ok=True)
SNAP = DASH / "snapshot.json"

def update_snapshot(payload: dict) -> None:
    try:
        payload = {"ts": int(time.time()), **payload}
        SNAP.write_text(json.dumps(payload, indent=2))
    except Exception:
        # never break the live loop because of reporting
        pass


def _side_emoji(side: str|None) -> str:
    return "🟢" if side == "buy" else "⚪"

def _fmt_prob(p: float) -> str:
    return f"{p:0.2f}"

@dataclass
class TFView:
    prob: float         # 0..1
    side: str|None      # "buy" or None
    price: float        # last price

class DashboardReporter:
    """
    Collects latest per-timeframe decisions per symbol, and periodically
    posts a compact dashboard to Telegram summarizing alignment across TFs.
    """
    def __init__(self, every_sec: int = 900, max_symbols: int = 12):
        self.every_sec = int(max(60, every_sec))
        self.max_symbols = max_symbols
        self._last_emit = 0.0
        self._cache: Dict[str, Dict[str, TFView]] = {}   # symbol -> {tf -> TFView}
        self._tg = TelegramNotifier()

    def update(self, symbol: str, timeframe: str, prob: float, side: str|None, price: float):
        sym = symbol.upper(); tf = timeframe.lower()
        self._cache.setdefault(sym, {})[tf] = TFView(prob=float(prob), side=side, price=float(price))

    def _build_symbol_block(self, symbol: str, views: Dict[str, TFView]) -> str:
        # sort TFs by "importance" (short to long)
        order = {"1m":1,"3m":2,"5m":3,"15m":4,"30m":5,"1h":6,"2h":7,"4h":8,"1d":9}
        tfs = sorted(views.keys(), key=lambda x: order.get(x, 99))
        frame_probs = {tf: views[tf].prob for tf in tfs}
        frame_sides = {tf: views[tf].side for tf in tfs}

        lines: List[str] = []
        # Title line
        last_price = views[tfs[0]].price if tfs else float("nan")
        lines.append(f"*{symbol}*  price=`{last_price:.6f}`")

        # Per-TF lines with CrossTF headline and SUI
        for tf in tfs:
            cx = cross_examine(frame_probs, frame_sides, tf)
            emoji = _side_emoji(views[tf].side)
            p = _fmt_prob(views[tf].prob)
            lines.append(f"`{tf:>3}` {emoji} p={p}  {cx['headline']}")
        return "\n".join(lines)

    def maybe_emit(self):
        now = time.time()
        if (now - self._last_emit) < self.every_sec:
            return
        if not self._cache:
            self._last_emit = now
            return

        # Build one message per symbol (avoid Telegram’s 4096 char limit)
        count = 0
        for symbol, views in list(self._cache.items()):
            if count >= self.max_symbols: break
            try:
                block = self._build_symbol_block(symbol, views)
                self._tg.note(block)
            except Exception:
                # never let dashboard spam exceptions into the trading loop
                pass
            count += 1

        self._last_emit = now
        try:
            # clear cache after emitting
            self._cache.clear()
