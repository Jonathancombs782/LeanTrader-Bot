# hivemind.py
from __future__ import annotations
import math, statistics
from dataclasses import dataclass
from typing import Dict, List, Callable, Optional, Tuple

import pandas as pd

from alpha_engines import AlphaRouter, Decision, BaseStrategy
from news_service import bullets_for

# ---- small helpers ----
def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _tf_sort_key(tf: str) -> int:
    # rank shorter frames first
    order = {"1m":1, "3m":2, "5m":3, "15m":4, "30m":5, "1h":6, "2h":7, "4h":8}
    return order.get(tf.lower(), 99)

@dataclass
class FrameDecision:
    timeframe: str
    dec: Decision
    price: float
    atr_p: float    # ATR% of price for this frame (rough regime)
    df: pd.DataFrame

class HiveCoordinator:
    """
    A 'team' of timeframe agents. Each timeframe has its own AlphaRouter brain & memory.
    We aggregate per-symbol across frames into a consensus decision with:
      - Weighted probability (higher frames have more weight)
      - Balanced Sequence Score (BSS): alignment/consistency across frames
      - Size multiplier & adaptive sleep derived from consensus
    """
    def __init__(self, timeframes: List[str]):
        self.tfs = sorted([tf.strip().lower() for tf in timeframes if tf.strip()], key=_tf_sort_key)
        # one AlphaRouter per TF so they learn independently
        self.brains: Dict[str, AlphaRouter] = {tf: AlphaRouter() for tf in self.tfs}
        # default weights: longer TF weighs more
        base_w = {"1m":1.0, "3m":1.1, "5m":1.25, "15m":1.6, "30m":1.8, "1h":2.0, "2h":2.2, "4h":2.5}
        self.weights: Dict[str, float] = {tf: base_w.get(tf, 1.0) for tf in self.tfs}

    def _frame_decision(self,
                        symbol: str,
                        timeframe: str,
                        fetch_ohlcv: Callable[[str, int], pd.DataFrame],
                        is_fx: bool) -> Optional[FrameDecision]:
        # limit larger on short TF, smaller for long TF
        limit = 500 if timeframe in ("1m","3m","5m") else 400
        df = fetch_ohlcv(timeframe, limit)
        if df is None or df.empty:
            return None
        price = float(df["close"].iloc[-1])
        atr_abs = BaseStrategy._atr(df, 14).iloc[-1]
        atr_p = float(atr_abs / max(1e-9, price)) if pd.notna(atr_abs) else 0.0
        # news bullets once; only on shortest TF to avoid duplication
        bullets = bullets_for(symbol, is_fx=is_fx, top_n=3) if timeframe == self.tfs[0] else []
        dec = self.brains[timeframe].pick(df, symbol=symbol, timeframe=timeframe, base_reasons=bullets)
        return FrameDecision(timeframe, dec, price, atr_p, df)

    def _consensus(self, fds: List[FrameDecision]) -> Tuple[Decision, List[str]]:
        """
        Build a consensus Decision from per-timeframe decisions.
        """
        if not fds:
            # dummy neutral decision
            return Decision(side=None, prob=0.5, size_mult=0.5, sleep_secs=12,
                            reasons=["No data"], notes="", votes={}, features={}), []

        # weighted probability with heavier long TFs
        num, den = 0.0, 0.0
        probs: Dict[str, float] = {}
        for fd in fds:
            w = self.weights.get(fd.timeframe, 1.0)
            p = float(fd.dec.prob)
            probs[fd.timeframe] = p
            num += w * p
            den += w
        p_w = num / max(1e-12, den)

        # Balanced Sequence Score (BSS): reward monotonic agreement of probs across TFs
        # compute normalized probs centered at 0.5
        centered = [probs[fd.timeframe]-0.5 for fd in fds]
        same_sign = all(x >= 0 for x in centered) or all(x <= 0 for x in centered)
        var = statistics.pvariance([probs[fd.timeframe] for fd in fds]) if len(fds) > 1 else 0.0
        bss = 0.0
        if same_sign and p_w >= 0.55:
            bss = _clip(0.25 * (0.6 - var*2.0), 0.0, 0.25)  # lower variance = stronger boost
        # slight penalty if higher TF disagrees strongly
        ht = fds[-1].timeframe
        if probs.get(ht, 0.5) < 0.52 and p_w >= 0.6:
            bss -= 0.08

        p_final = _clip(p_w + bss, 0.0, 1.0)

        # side logic: require majority "buy" and higher timeframe neutral+ or better
        votes_buy = sum(1 for fd in fds if fd.dec.side == "buy")
        side = "buy" if (votes_buy / len(fds) >= 0.6 and p_final >= 0.58) else None

        # size & sleep derived from consensus
        size_mult = _clip(0.5 + 1.7*(p_final-0.5)/0.5, 0.5, 2.2)
        sleep = min(fd.dec.sleep_secs for fd in fds) if fds else 10

        # aggregate reasons (top 1 per TF, plus BSS note)
        reasons: List[str] = []
        for fd in fds:
            tag = f"[{fd.timeframe}] p={fd.dec.prob:.2f}"
            top = (fd.dec.reasons[:1] if fd.dec.reasons else [])
            for t in top:
                reasons.append(f"{tag} {t}")
        reasons.insert(0, f"🧩 BSS={bss:+.2f}  p*={p_w:.2f} → p={p_final:.2f}")

        # aggregate votes/features for transparency
        votes_all: Dict[str, float] = {}
        feats_all: Dict[str, float] = {}
        for fd in fds:
            for k,v in fd.dec.votes.items():
                votes_all[f"{fd.timeframe}.{k}"] = float(v)
            for k,v in fd.dec.features.items():
                feats_all[f"{fd.timeframe}.{k}"] = float(v)

        cons = Decision(side=side, prob=p_final, size_mult=size_mult, sleep_secs=int(sleep),
                        reasons=reasons[:6], notes="; ".join(rf"[{fd.timeframe}] {fd.dec.notes}" for fd in fds)[:240],
                        votes=votes_all, features=feats_all)
        return cons, [fd.timeframe for fd in fds]

    def decide(self,
               symbol: str,
               is_fx: bool,
               fetch_ohlcv: Callable[[str, int], pd.DataFrame]) -> Tuple[Decision, List[FrameDecision]]:
        frames: List[FrameDecision] = []
        for tf in self.tfs:
            fd = self._frame_decision(symbol, tf, fetch_ohlcv, is_fx=is_fx)
            if fd is not None:
                frames.append(fd)
        cons, _ = self._consensus(frames)
        return cons, frames
