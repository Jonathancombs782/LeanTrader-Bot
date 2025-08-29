# cross_examiner.py
from __future__ import annotations
import math, statistics
from dataclasses import dataclass
from typing import Dict, List, Tuple

def _clip(x, lo, hi): return max(lo, min(hi, x))

_TF_ORDER = {"1m":1,"3m":2,"5m":3,"15m":4,"30m":5,"1h":6,"2h":7,"4h":8,"1d":9}

def _rank(tf: str) -> int:
    return _TF_ORDER.get(tf.lower(), 99)

def _hold_bins(tf: str) -> Tuple[str, str]:
    """Return (label, range) default hold per timeframe."""
    t = tf.lower()
    if t == "1m":  return ("scalp", "3–10m")
    if t == "3m":  return ("scalp", "5–20m")
    if t == "5m":  return ("intra", "15–45m")
    if t == "15m": return ("intra", "45–180m")
    if t == "30m": return ("intra", "2–4h")
    if t == "1h":  return ("swing", "4–10h")
    if t == "2h":  return ("swing", "8–20h")
    if t == "4h":  return ("swing", "1–3d")
    if t == "1d":  return ("position", "2–7d")
    return ("intra","1–4h")

@dataclass
class FrameView:
    tf: str
    prob: float   # 0..1
    side: str|None  # "buy" or None

def cross_examine(frame_probs: Dict[str, float], frame_sides: Dict[str, str|None], focus_tf: str) -> Dict[str, str|float]:
    """
    Given all timeframe probs/sides and the timeframe we're evaluating, return:
      - sui: Sequence Uniformity Index [0..1]
      - higher_support / lower_support: weighted agreement above/below focus TF
      - p_weighted: prob weighted by TF rank
      - hold_label / hold_range: suggested hold window (adjusted by higher TF support)
      - headline: compact one-liner for Telegram
    """
    # --- normalize & sort by rank ---
    tfs = sorted(frame_probs.keys(), key=_rank)
    probs = [frame_probs[tf] for tf in tfs]
    # SUI: 1 - normalized variance + sign-consistency bonus
    var = statistics.pvariance(probs) if len(probs) > 1 else 0.0
    sign = [1 if (p-0.5) >= 0 else -1 for p in probs]
    agree = sum(1 for s in sign if s == (1 if (frame_probs[focus_tf]-0.5)>=0 else -1))
    agree_frac = agree/len(sign)
    sui = _clip(1.0 - 2.0*var, 0.0, 1.0) * (0.7 + 0.3*agree_frac)

    # weighted prob by TF rank (longer TF slightly heavier)
    weights = [1.0 + 0.15*_rank(tf) for tf in tfs]
    wsum = sum(weights) or 1.0
    p_weighted = sum(w*p for w,p in zip(weights, probs)) / wsum

    # higher/lower support relative to focus_tf
    r_focus = _rank(focus_tf)
    hi = [(tf,frame_probs[tf]) for tf in tfs if _rank(tf) > r_focus]
    lo = [(tf,frame_probs[tf]) for tf in tfs if _rank(tf) < r_focus]
    def _support(parts):  # fraction of weight with p>=0.58
        if not parts: return 0.0
        ws = [1.0 + 0.15*_rank(tf) for tf,_ in parts]
        mask = [1.0 if p>=0.58 else 0.0 for _,p in parts]
        return sum(w*m for w,m in zip(ws,mask)) / (sum(ws) or 1.0)
    higher_support = _support(hi)
    lower_support  = _support(lo)

    # hold window: start with focus defaults and extend if higher TFs agree
    hold_label, hold_range = _hold_bins(focus_tf)
    if higher_support >= 0.6 and p_weighted >= 0.58:
        # extend a notch
        if hold_label == "scalp":   hold_label, hold_range = ("intra", "30–120m")
        elif hold_label == "intra": hold_label, hold_range = ("swing", "4–12h")
        elif hold_label == "swing": hold_label, hold_range = ("swing", "1–4d")
    # headline compact
    up_hi = int(round(higher_support*3))  # 0..3 blocks
    up_lo = int(round(lower_support*3))
    headline = f"CrossTF hi={'█'*up_hi+'·'*(3-up_hi)} lo={'█'*up_lo+'·'*(3-up_lo)} | SUI={sui:.2f} | Hold≈ {hold_range}"
    return {
        "sui": float(sui),
        "higher_support": float(higher_support),
        "lower_support": float(lower_support),
        "p_weighted": float(p_weighted),
        "hold_label": hold_label,
        "hold_range": hold_range,
        "headline": headline,
    }
