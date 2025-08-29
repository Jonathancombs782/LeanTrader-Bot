# gloaware.py
from __future__ import annotations
import math, time
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd

def _safe(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return default
        return float(val)
    except Exception:
        return default

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=int(n), adjust=False).mean()

def _trend_strength(df: pd.DataFrame, fast=20, slow=50) -> float:
    if len(df) < slow + 2: return 0.0
    ema_f = _ema(df["close"], fast)
    ema_s = _ema(df["close"], slow)
    spread = ema_f - ema_s
    # slope via last N returns on the spread
    z = spread.tail(60).pct_change().fillna(0.0)
    s = z.mean() / (z.std(ddof=0) + 1e-12)
    return float(np.tanh(3.0 * s))  # clamp to [-1,1]

def _market_heat(df: pd.DataFrame) -> float:
    # normalized ATR/price * volume zscore → activity proxy
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    vol = df["vol"].astype(float)
    pc = pd.Series(c).shift(1)
    tr = pd.concat([(pd.Series(h) - pd.Series(l)),
                    (pd.Series(h) - pc).abs(),
                    (pd.Series(l) - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1] if len(tr) >= 14 else 0.0
    px  = c[-1] if len(c) else 0.0
    atr_ratio = float(atr / max(px, 1e-12))
    vol_z = ((vol - vol.rolling(100).mean()) / (vol.rolling(100).std(ddof=0)+1e-9)).iloc[-1] if len(vol) >= 100 else 0.0
    heat = np.tanh(50*atr_ratio) + 0.15*float(vol_z)
    return float(np.clip(heat, -2.0, 2.0))

def _novelty(df: pd.DataFrame) -> float:
    # how "unusual" is the last candle vs 200-bar history
    feats = pd.DataFrame({
        "ret": pd.Series(df["close"]).pct_change(),
        "rng": pd.Series(df["high"]) - pd.Series(df["low"]),
        "dir": (pd.Series(df["close"]) - pd.Series(df["open"])) / (pd.Series(df["high"]) - pd.Series(df["low"]) + 1e-12),
    }).fillna(0.0)
    mu = feats.rolling(200).mean()
    sd = feats.rolling(200).std(ddof=0) + 1e-9
    z = ((feats - mu) / sd).tail(1).abs().mean(axis=1)
    return float(np.tanh(z.iloc[0])) if len(z) else 0.0

@dataclass
class AwarenessConfig:
    # risk/drawdown adaptation
    daily_dd_bps_caution: float = 150.0
    daily_dd_bps_stop: float    = 300.0
    upsize_max: float = 1.5
    downsize_min: float = 0.25
    # pacing
    sleep_base: float = 5.0
    sleep_fast: float = 2.0
    sleep_slow: float = 8.0
    # gating
    allow_when_calendar_risk_off: bool = False

@dataclass
class AwarenessDecision:
    mode: str
    size_mult: float
    sleep_secs: float
    notes: str
    confidence: float  # 0..1

class GloAware:
    """
    Computes a per-loop decision:
      - FOCUS when heat↑, trend↑, novelty moderate, no calendar risk, no heavy drawdown
      - CAUTION when drawdown or calendar risk
      - NEUTRAL otherwise
    Returns dynamic size multiplier and sleep seconds.
    """
    def __init__(self, cfg: AwarenessConfig):
        self.cfg = cfg
        self.day_pnl_bps = 0.0  # you can feed real value from guard/ledger

    def update_day_pnl_bps(self, bps: float):
        self.day_pnl_bps = float(bps)

    def assess(self, df: pd.DataFrame, last_row: Dict, pick_score: float) -> AwarenessDecision:
        if df is None or df.empty:
            return AwarenessDecision("NEUTRAL", 1.0, self.cfg.sleep_base, "no data", 0.4)

        heat = _market_heat(df)
        trend = _trend_strength(df)
        nov = _novelty(df)
        sent = _safe(last_row.get("news_sent", 0.0))
        cal_risk = int(last_row.get("risk_off_calendar", 0)) == 1

        # crude confidence blend
        conf = 0.55*max(0.0, trend) + 0.25*max(0.0, heat) + 0.10*np.tanh(sent) + 0.10*max(0.0, pick_score)
        conf = float(np.clip(conf, 0.0, 1.0))

        mode = "NEUTRAL"
        size_mult = 1.0
        sleep = self.cfg.sleep_base
        notes = []

        # drawdown gates
        if self.day_pnl_bps <= -self.cfg.daily_dd_bps_stop:
            mode = "STOP"
            size_mult = 0.0
            sleep = self.cfg.sleep_slow
            notes.append(f"hard stop dd={self.day_pnl_bps:.0f}bps")
        elif self.day_pnl_bps <= -self.cfg.daily_dd_bps_caution:
            mode = "CAUTION"
            size_mult = max(self.cfg.downsize_min, 0.5 * conf)
            sleep = self.cfg.sleep_slow
            notes.append(f"caution dd={self.day_pnl_bps:.0f}bps")

        # calendar risk
        if cal_risk and not self.cfg.allow_when_calendar_risk_off and mode != "STOP":
            mode = "CAUTION"
            size_mult = min(size_mult, max(self.cfg.downsize_min, 0.4 * conf))
            sleep = max(sleep, self.cfg.sleep_slow)
            notes.append("calendar risk-off")

        # opportunity boost
        if mode not in ("STOP",) and (heat > 0.5 and trend > 0.2 and nov < 0.6):
            mode = "FOCUS" if mode == "NEUTRAL" else mode
            size_mult = min(self.cfg.upsize_max, max(size_mult, 0.8 + 0.8*conf))
            sleep = min(sleep, self.cfg.sleep_fast)
            notes.append("focus: heat/trend")

        if not notes:
            notes.append("balanced")

        return AwarenessDecision(mode, float(size_mult), float(sleep), "; ".join(notes), conf)
