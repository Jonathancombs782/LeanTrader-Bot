# alpha_engines.py
from __future__ import annotations
import json, math, random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd

MEMO = Path("reports/alpha_memory.json")
MEMO.parent.mkdir(parents=True, exist_ok=True)

# ----------------- small utils -----------------
def _clip(x, lo, hi): return max(lo, min(hi, x))
def _sigmoid(x): return 1.0 / (1.0 + math.exp(-x))
def _softmax(xs: List[float]) -> List[float]:
    a = np.array(xs, dtype=float)
    a = a - np.max(a)
    e = np.exp(a)
    p = e / (np.sum(e) + 1e-12)
    return p.tolist()

def _load_memo() -> Dict[str, Any]:
    if MEMO.exists():
        try: return json.loads(MEMO.read_text())
        except Exception: pass
    return {"reliability": {}, "explore_eps": 0.08}

def _save_memo(obj: Dict[str, Any]):
    try: MEMO.write_text(json.dumps(obj, indent=2))
    except Exception: pass

# ----------------- Decision object -----------------
@dataclass
class Decision:
    side: Optional[str]          # 'buy' or None (flat)
    prob: float                  # calibrated probability 0..1
    size_mult: float             # 0.5 .. 2.0 (use to scale stake/lots)
    sleep_secs: int              # adaptive loop pacing
    reasons: List[str]           # bullets/news/strategy cues
    notes: str                   # short text about which strategies voted what
    votes: Dict[str, float]      # strategy->score
    features: Dict[str, float]   # useful for logging

# ----------------- Base class -----------------
class BaseStrategy:
    name = "base"

    def compute(self, df: pd.DataFrame, **kw) -> Dict[str, Any]:
        raise NotImplementedError

    # helpers
    @staticmethod
    def _ema(s: pd.Series, n: int) -> pd.Series:
        return s.ewm(span=n, adjust=False).mean()

    @staticmethod
    def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
        h, l, c = df["high"], df["low"], df["close"]
        pc = c.shift(1)
        tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        return tr.rolling(n).mean()

    @staticmethod
    def _rsi(s: pd.Series, n: int) -> pd.Series:
        d = s.diff()
        up = (d.clip(lower=0)).ewm(alpha=1/n, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = up / (dn + 1e-12)
        return 100 - (100/(1+rs))

# ----------------- “Naked” & Oscillator engines -----------------
class OscillatorConfluence(BaseStrategy):
    name = "osc_confluence"
    def __init__(self, rsi_len=10, stoch_k=9, stoch_d=3, stoch_smooth=3,
                 macd_fast=6, macd_slow=13, macd_signal=9):
        self.rsi_len=rsi_len; self.stoch_k=stoch_k; self.stoch_d=stoch_d; self.stoch_smooth=stoch_smooth
        self.macd_fast=macd_fast; self.macd_slow=macd_slow; self.macd_signal=macd_signal

    def _stoch(self, h,l,c):
        ll = l.rolling(self.stoch_k).min()
        hh = h.rolling(self.stoch_k).max()
        k = 100*(c-ll)/(hh-ll+1e-12)
        k = k.rolling(self.stoch_smooth).mean()
        d = k.rolling(self.stoch_d).mean()
        return k,d

    def _macd(self, s):
        f = self._ema(s, self.macd_fast)
        sl = self._ema(s, self.macd_slow)
        m = f - sl
        sig = self._ema(m, self.macd_signal)
        return m, sig, (m - sig)

    def compute(self, df: pd.DataFrame, **kw):
        d = df
        rsi = self._rsi(d["close"], self.rsi_len)
        k, q = self._stoch(d["high"], d["low"], d["close"])
        macd, sig, hist = self._macd(d["close"])
        kx = (k > q) & (k.shift(1) <= q.shift(1))
        stoch_low = (k < 80) & (q < 80)
        rsi_ok = (rsi > 50) | ((rsi >= 48) & (rsi.diff() > 0))
        macd_up = hist.diff() > 0
        raw = float((kx & stoch_low & rsi_ok & macd_up).astype(int).iloc[-1])
        s = 0.40*raw + 0.25*_sigmoid((rsi.iloc[-1]-50)/5) + 0.35*_sigmoid(hist.iloc[-1]*6)
        s = _clip(2*s-1, -1, 1)
        reasons = [f"Stoch K∧D, RSI={rsi.iloc[-1]:.1f}, MACDΔ={hist.iloc[-1]:.3f}"]
        feats = {"rsi": float(rsi.iloc[-1]), "macd_hist": float(hist.iloc[-1]),
                 "k": float(k.iloc[-1]), "d": float(q.iloc[-1])}
        return {"score": s, "reasons": reasons, "features": feats}

class NakedPriceAction(BaseStrategy):
    name = "naked_price"
    def __init__(self, body_mult=1.2):
        self.body_mult = body_mult
    def compute(self, df: pd.DataFrame, **kw):
        d = df.tail(5).copy()
        o, h, l, c = d["open"], d["high"], d["low"], d["close"]
        rng = (h - l).iloc[-1]
        body = abs(c - o).iloc[-1]
        upper_wick = (h - c).iloc[-1] if c >= o.iloc[-1] else (h - o).iloc[-1]
        lower_wick = (o - l).iloc[-1] if c >= o.iloc[-1] else (c - l).iloc[-1]
        score = 0.0; why = []
        if c.iloc[-2] < o.iloc[-2] and c.iloc[-1] > o.iloc[-1] and c.iloc[-1] > o.iloc[-2] and o.iloc[-1] < c.iloc[-2]:
            score += 0.6; why.append("Bullish engulfing")
        if lower_wick > self.body_mult * body and lower_wick > 0.6*rng:
            score += 0.5; why.append("Bullish pin bar")
        score = _clip(score, 0, 1); score = 2*score - 1
        feats = {"rng": float(rng), "body": float(body), "lw": float(lower_wick)}
        return {"score": score, "reasons": why, "features": feats}

# ----------------- Trend / Breakout engines -----------------
class TrendSqueeze(BaseStrategy):
    name = "trend_squeeze"
    def __init__(self, ema_fast=50, ema_slow=200, bb_period=20, bb_std=2.0):
        self.ema_fast=ema_fast; self.ema_slow=ema_slow; self.bb_period=bb_period; self.bb_std=bb_std
    def compute(self, df: pd.DataFrame, **kw):
        c = df["close"]
        ema_f = self._ema(c, self.ema_fast)
        ema_s = self._ema(c, self.ema_slow)
        ma = c.rolling(self.bb_period).mean()
        sd = c.rolling(self.bb_period).std(ddof=0)
        upper = ma + self.bb_std * sd
        lower = ma - self.bb_std * sd
        bw = (upper - lower) / (ma.replace(0, np.nan))
        squeeze = bw <= bw.rolling(120).quantile(0.5, interpolation="nearest")
        breakout = (c > upper.shift(1)) & squeeze.fillna(False)
        trend = (ema_f > ema_s)
        raw = float((breakout & trend).astype(int).iloc[-1])
        slope = float((ema_f - ema_s).iloc[-1])
        s = 0.6*raw + 0.4*_sigmoid(50*slope/(abs(c.iloc[-1])+1e-9))
        s = _clip(2*s-1, -1, 1)
        reasons = [f"EMA {self.ema_fast}/{self.ema_slow} up, BB breakout"]
        feats = {"ema_spread": float(ema_f.iloc[-1]-ema_s.iloc[-1]),
                 "bb_bw": float(bw.iloc[-1]) if pd.notna(bw.iloc[-1]) else 0.0}
        return {"score": s, "reasons": reasons, "features": feats}

class DonchianBreakout(BaseStrategy):
    name = "donchian"
    def __init__(self, lookback=55): self.lookback=lookback
    def compute(self, df: pd.DataFrame, **kw):
        hh = df["high"].rolling(self.lookback).max()
        ll = df["low"].rolling(self.lookback).min()
        c = df["close"]
        raw = float((c.iloc[-1] >= hh.iloc[-2]).astype(int))
        mid = (hh + ll)/2
        z = (c - mid) / ((hh-ll)/2 + 1e-12)
        s = 0.6*raw + 0.4*_sigmoid(float(z.iloc[-1]))
        s = _clip(2*s-1, -1, 1)
        return {"score": s, "reasons": [f"Donchian {self.lookback} breakout"],
                "features": {"z": float(z.iloc[-1])}}

class KeltnerBreakout(BaseStrategy):
    name = "keltner"
    def __init__(self, ema_len=20, atr_mult=2.0):
        self.ema_len=ema_len; self.atr_mult=atr_mult
    def compute(self, df: pd.DataFrame, **kw):
        ema = self._ema(df["close"], self.ema_len)
        atr = self._atr(df, 20)
        upper = ema + self.atr_mult*atr
        raw = float((df["close"].iloc[-1] > upper.iloc[-1]).astype(int))
        s = 0.7*raw + 0.3*_sigmoid((df["close"].iloc[-1]-ema.iloc[-1])/(atr.iloc[-1]+1e-12))
        s = _clip(2*s-1, -1, 1)
        return {"score": s, "reasons": [f"Keltner breakout {self.ema_len}/{self.atr_mult}"],
                "features": {"atr": float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0}}

# ----------------- Reversion / Flow engines -----------------
class VWAPBounce(BaseStrategy):
    name = "vwap_revert"
    def compute(self, df: pd.DataFrame, **kw):
        p = df["close"]; v = df["vol"]
        pv = (p*v).rolling(120).sum()
        vv = v.rolling(120).sum()
        vwap = pv/(vv+1e-12)
        dist = (vwap - p) / (p + 1e-12)
        rising = p.diff().iloc[-1] > 0 and p.iloc[-1] < vwap.iloc[-1]
        s = 0.5*_sigmoid(500*float(dist.iloc[-1])) + (0.5 if rising else 0.0)
        s = _clip(2*s-1, -1, 1)
        return {"score": s, "reasons": [f"VWAP revert {float(dist.iloc[-1])*100:.2f}%"],
                "features": {"vwap_dist": float(dist.iloc[-1])}}

class VolumeSpike(BaseStrategy):
    name = "vol_spike"
    def compute(self, df: pd.DataFrame, **kw):
        vol = df["vol"]
        z = (vol - vol.rolling(50).mean()) / (vol.rolling(50).std(ddof=0)+1e-9)
        strong = float((z.iloc[-1] > 2.0).astype(int))
        upbar = float((df["close"].iloc[-1] > df["open"].iloc[-1]).astype(int))
        s = _clip(2*(_sigmoid(0.7*z.iloc[-1]) * (0.6*upbar + 0.4)) - 1, -1, 1)
        return {"score": s, "reasons": [f"Vol spike z={z.iloc[-1]:.2f}"],
                "features": {"vol_z": float(z.iloc[-1])}}

# ----------------- Regime / Session filters -----------------
class VolRegime(BaseStrategy):
    name = "regime"
    def compute(self, df: pd.DataFrame, **kw):
        atr = self._atr(df, 14)
        vol_norm = (atr / (df["close"] + 1e-12)).rolling(50).mean()
        s = _clip(_sigmoid(200*float((vol_norm.iloc[-1] or 0))) - 0.5, -1, 1)  # prefer higher vol
        return {"score": s, "reasons": [f"Vol regime {(vol_norm.iloc[-1] or 0):.4f}"],
                "features": {"vol_norm": float(vol_norm.iloc[-1] or 0)}}

class SessionBias(BaseStrategy):
    name = "session_bias"
    def compute(self, df: pd.DataFrame, **kw):
        # approximate: use last 400 bars time drift to hour-of-day bias
        ts = pd.to_datetime(df["ts"], unit="ms")
        hour = ts.dt.hour.iloc[-1] if "ts" in df else 12
        # mild institutional bias: 13:00-17:00 UTC risk-on
        bias = 1.0 if 13 <= int(hour) <= 17 else 0.0
        s = 0.3*bias
        return {"score": s, "reasons": [f"Session hour={hour} bias={bias:.1f}"], "features": {"hour": float(hour)}}

# ----------------- Alpha Router -----------------
class AlphaRouter:
    """
    Fuses many strategies, calibrates to probability, adapts by (symbol,timeframe).
    Exploration via epsilon-greedy; reliability updated externally via update_reliability().
    """
    def __init__(self):
        self.strats: List[BaseStrategy] = [
            OscillatorConfluence(),
            TrendSqueeze(),
            NakedPriceAction(),
            DonchianBreakout(),
            KeltnerBreakout(),
            VWAPBounce(),
            VolumeSpike(),
            VolRegime(),
            SessionBias(),
        ]
        self.memo = _load_memo()

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def _weights_for(self, symbol: str, timeframe: str) -> Dict[str, float]:
        r = self.memo.get("reliability", {})
        key = self._key(symbol, timeframe)
        return r.get(key, {})

    def pick(self, df: pd.DataFrame, symbol: str, timeframe: str,
             base_reasons: Optional[List[str]] = None) -> Decision:
        base_reasons = base_reasons or []
        votes: Dict[str, float] = {}
        notes = []; feats: Dict[str, float] = {}

        for s in self.strats:
            try:
                out = s.compute(df)
                score = float(out.get("score", 0.0))
                votes[s.name] = _clip(score, -1, 1)
                for k,v in (out.get("features") or {}).items():
                    feats[f"{s.name}.{k}"] = float(v)
                if out.get("reasons"):
                    notes.append(f"{s.name}: " + "; ".join(out["reasons"][:2]))
            except Exception:
                votes[s.name] = 0.0

        # per-strategy probabilities
        probs = {k: _sigmoid(2.2*v) for k, v in votes.items()}
        # reliability weights
        ws = self._weights_for(symbol, timeframe)
        weights = {k: max(0.2, ws.get(k, 1.0)) for k in votes.keys()}

        # ensemble probability
        p = sum(probs[k]*weights[k] for k in votes) / (sum(weights.values()) + 1e-12)

        # exploration: occasionally trust a strong voter
        if random.random() < float(self.memo.get("explore_eps", 0.08)):
            k_max = max(votes, key=lambda k: votes[k])
            p = 0.65 + 0.25*votes[k_max]

        side = "buy" if p >= 0.58 else None
        size_mult = _clip(0.5 + 1.5*(p-0.5)/0.5, 0.5, 2.0)
        sleep = 5 if p > 0.7 else 8 if p > 0.6 else 12

        reasons = list(base_reasons)[:3]
        for n in notes[:2]:
            reasons.append("• " + n)

        note = " | ".join(notes[:3])
        return Decision(side=side, prob=float(p), size_mult=float(size_mult),
                        sleep_secs=int(sleep), reasons=reasons, notes=note,
                        votes=votes, features=feats)

    def update_reliability(self, symbol: str, timeframe: str, strat_name: str, reward: float):
        r = self.memo.setdefault("reliability", {})
        key = self._key(symbol, timeframe)
        row = r.setdefault(key, {})
        w = float(row.get(strat_name, 1.0))
        w = _clip(w + 0.1*np.tanh(reward/100.0), 0.2, 3.0)
        row[strat_name] = float(w)
        _save_memo(self.memo)
