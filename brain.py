# brain.py
from __future__ import annotations
import os, json, math, time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

# ---------- small utils ----------
def envf(name: str, default: float) -> float:
    try: return float(os.getenv(name, default))
    except: return float(default)

def envs(name: str, default: str) -> str:
    return os.getenv(name, default)

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

# ---------- features ----------
def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def regime(df: pd.DataFrame) -> str:
    """Very light regime tag: 'trend' vs 'range' + 'volatile' flag."""
    e12, e26 = ema(df["close"], 12), ema(df["close"], 26)
    bbw = (df["close"].rolling(20).std() / df["close"].rolling(20).mean()).iloc[-1]
    trending = abs((e12 - e26).iloc[-1]) > df["close"].rolling(20).std().iloc[-1] * 0.15
    volatile = bbw is not None and bbw > 0.02
    if trending and volatile: return "trend_volatile"
    if trending: return "trend"
    if volatile: return "range_volatile"
    return "range"

def session_weight(ts: datetime) -> float:
    # simple UTC windows; tweak per venue if you want
    hh = ts.hour
    if 23 <= hh or hh < 7:   # Asia
        return envf("SESSION_ASIA", 0.7)
    if 7 <= hh < 13:         # London
        return envf("SESSION_LONDON", 1.0)
    return envf("SESSION_NEWYORK", 1.2)  # NY

# ---------- memory (experience replay lite) ----------
class Memory:
    PATH = "runtime/brain_mem.json"
    def __init__(self) -> None:
        os.makedirs("runtime", exist_ok=True)
        try:
            with open(self.PATH, "r") as f: self.mem = json.load(f)
        except: self.mem = {"trades": [], "pnl_day": {}, "losers": 0}

    def save(self) -> None:
        with open(self.PATH, "w") as f: json.dump(self.mem, f, indent=2)

    def push_trade(self, sym: str, side: str, pnl: float) -> None:
        self.mem["trades"].append({"t": time.time(), "sym": sym, "side": side, "pnl": pnl})
        self.mem["trades"] = self.mem["trades"][-2000:]
        # daily pnl
        day = datetime.utcfromtimestamp(time.time()).strftime("%Y-%m-%d")
        self.mem["pnl_day"][day] = self.mem["pnl_day"].get(day, 0.0) + pnl
        # loser streak
        if pnl < 0: self.mem["losers"] = int(self.mem.get("losers", 0)) + 1
        else:       self.mem["losers"] = 0
        self.save()

    def pnl_today(self) -> float:
        day = datetime.utcfromtimestamp(time.time()).strftime("%Y-%m-%d")
        return float(self.mem.get("pnl_day", {}).get(day, 0.0))

    def losers(self) -> int:
        return int(self.mem.get("losers", 0))

# ---------- sizing ----------
class VolSizer:
    def __init__(self, balance_usd: float) -> None:
        self.mode = envs("SIZER_MODE", "fixed_usd")
        self.fixed = envf("FIXED_USD", 5)
        self.risk_bps = envf("RISK_PER_TRADE_BPS", 25)
        self.balance = balance_usd

    def fixed_usd(self) -> float:
        return max(1.0, self.fixed)

    def vol_target_usd(self, df: pd.DataFrame) -> float:
        # target position such that ATR move ≈ risk fraction of equity
        atrp = atr(df, int(envf("ATR_PERIOD", 14))).iloc[-1] / df["close"].iloc[-1]
        atrp = max(atrp, 0.001)  # floor
        risk_frac = self.risk_bps / 10000.0
        return max(1.0, self.balance * risk_frac / atrp)

    def usd(self, df: pd.DataFrame) -> float:
        if self.mode == "vol_target":
            return self.vol_target_usd(df)
        return self.fixed_usd()

# ---------- advice ----------
@dataclass
class Advice:
    side: Optional[str]      # "buy" | "sell" | None
    sl: Optional[float]
    tp: Optional[float]
    reason: str

class Brain:
    def __init__(self) -> None:
        self.tf = envs("BRAIN_TF", "1m")
        self.ap = int(envf("ATR_PERIOD", 14))
        self.slm = envf("ATR_SL_MULT", 1.2)
        self.tpm = envf("ATR_TP_MULT", 2.0)

    def decide(self, sym: str, df: pd.DataFrame) -> Advice:
        # minimal, robust signal: EMA cross + regime context
        df = df.copy()
        df["ema12"] = ema(df["close"], 12)
        df["ema26"] = ema(df["close"], 26)
        r = regime(df)
        last = df.iloc[-1]
        side = None
        if last["ema12"] > last["ema26"]:
            side = "buy"
        elif last["ema12"] < last["ema26"]:
            side = "sell"

        a = atr(df, self.ap).iloc[-1]
        if not np.isfinite(a) or a <= 0:
            return Advice(None, None, None, "no_atr")

        price = float(last["close"])
        if side == "buy":
            sl = price - self.slm * a
            tp = price + self.tpm * a
        elif side == "sell":
            sl = price + self.slm * a
            tp = price - self.tpm * a
        else:
            return Advice(None, None, None, "no_bias")

        # session throttle
        sess_w = session_weight(now_utc())
        reason = f"{r}|ema_cross|atr={a:.5f}|sess={sess_w:.2f}"
        return Advice(side, sl, tp, reason)

    def trail(self, side: str, entry: float, df: pd.DataFrame) -> Tuple[float, float]:
        """Return (new_sl, new_tp) trailing using ATR."""
        a = atr(df, self.ap).iloc[-1]
        price = float(df["close"].iloc[-1])
        if side == "buy":
            return max(entry - self.slm * a, price - self.slm * a), price + self.tpm * a
        else:
            return min(entry + self.slm * a, price + self.slm * a), price - self.tpm * a

# ---------- guards ----------
class Guards:
    def __init__(self, memory: Memory) -> None:
        self.mem = memory
        self.max_loss = envf("DAILY_MAX_LOSS_USD", 50)
        self.max_losers = int(envf("MAX_CONSEC_LOSERS", 3))
        self.max_abs_funding = envf("MAX_ABS_FUNDING", 0.05)

    def day_ok(self) -> Tuple[bool, str]:
        if self.mem.pnl_today() <= -abs(self.max_loss):
            return False, f"daily_loss_guard hit ({self.mem.pnl_today():.2f} <= {-abs(self.max_loss):.2f})"
        if self.mem.losers() >= self.max_losers:
            return False, f"loser_streak_guard hit ({self.mem.losers()} >= {self.max_losers})"
        return True, "ok"

    def funding_ok(self, funding: Optional[float]) -> Tuple[bool, str]:
        if funding is None: return True, "no_funding_data"
        if abs(funding) > self.max_abs_funding:
            return False, f"skip extreme funding {funding:.3f}"
        return True, "ok"
