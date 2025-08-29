# tf_brains.py
from __future__ import annotations
import math
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

class TFBrain:
    def __init__(self, tf: str, strat, risk_cfg, news_fn=None):
        self.tf = tf
        self.strat = strat
        self.risk = risk_cfg
        self.news_fn = news_fn  # bullets_for(symbol,is_fx)
        self.state: Dict[str, Dict[str, Any]] = {}  # per-symbol open pos etc.

    def score_pick(self, d: pd.DataFrame, news_bullets: List[str]) -> float:
        # simple quality = trend strength + vol breakout + news mood count
        ema_fast = d["ema_fast"].iloc[-1]
        ema_slow = d["ema_slow"].iloc[-1]
        close = d["close"].iloc[-1]
        atr = float(d["atr"].iloc[-1]) if not math.isnan(d["atr"].iloc[-1]) else 0.0
        trend = 1.0 if ema_fast > ema_slow else 0.0
        bb = float(d["bb_bw"].iloc[-1])
        news = min(2.0, 0.5 * len(news_bullets or []))
        vol_norm = min(2.0, bb * 5.0)
        return trend + vol_norm + news

    def evaluate(self, symbol: str, df: pd.DataFrame, is_fx: bool) -> Optional[Dict[str, Any]]:
        d, info = self.strat.entries_and_exits(
            df[["timestamp","open","high","low","close","vol"]],
            self.risk.atr_stop_mult,
            self.risk.atr_trail_mult
        )
        if d["long_signal"].iloc[-1]:
            bullets = self.news_fn(symbol, is_fx, top_n=3) if self.news_fn else []
            q = self.score_pick(d, bullets)
            px = float(d["close"].iloc[-1])
            atr = float(d["atr"].iloc[-1]) if not math.isnan(d["atr"].iloc[-1]) else 0.0
            stop = px - self.risk.atr_stop_mult * atr
            tp   = px + self.risk.atr_trail_mult * atr
            return {"symbol":symbol, "price":px, "stop":stop, "tp":tp, "quality":q, "bullets":bullets, "df":d}
        return None
# Example risk_cfg: atr_stop_mult=1.5, atr_trail_mult=3.0
