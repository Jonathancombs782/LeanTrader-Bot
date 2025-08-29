# strategy_zoo.py
from __future__ import annotations
import math
from typing import Dict, Any
import numpy as np
import pandas as pd

# ---------- common helpers ----------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=int(n), adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(int(n)).mean()

def bbands(close: pd.Series, n=20, k=2.0):
    ma = close.rolling(int(n)).mean()
    sd = close.rolling(int(n)).std(ddof=0)
    bw = (sd / ma).rolling(int(n)).mean()
    return ma, ma + k*sd, ma - k*sd, bw

def rsi(close: pd.Series, n=14):
    delta = close.diff()
    up, dn = (delta.clip(lower=0)), (-delta.clip(upper=0))
    rs = up.rolling(int(n)).mean() / dn.rolling(int(n)).mean().replace(0,np.nan)
    return 100 - (100/(1+rs))

def donchian(df: pd.DataFrame, n=20):
    return df["high"].rolling(int(n)).max(), df["low"].rolling(int(n)).min()

# swing points (fractals)
def swing_flags(h: pd.Series, l: pd.Series, sw_n=3):
    # True when the bar is the max/min in a window centered at it
    sw_n = int(sw_n)
    hh = h.rolling(2*sw_n+1, center=True).apply(lambda x: float(x[sw_n] == x.max()), raw=False).fillna(0).astype(bool)
    ll = l.rolling(2*sw_n+1, center=True).apply(lambda x: float(x[sw_n] == x.min()), raw=False).fillna(0).astype(bool)
    return hh, ll

def bullish_pinbar(o,h,l,c, tail_min_frac=0.6, body_max_frac=0.35):
    rng = (h - l) + 1e-12
    body = abs(c - o) / rng
    lower = (min(o,c) - l) / rng
    return (lower >= tail_min_frac) and (body <= body_max_frac)

def bullish_engulf(prev_o, prev_c, o, c):
    return (c > o) and (o < prev_c) and (c > prev_o)

def structure_uptrend(h: pd.Series, l: pd.Series, look=5):
    # Higher highs and higher lows over last window
    hh = h.iloc[-look:].dropna()
    ll = l.iloc[-look:].dropna()
    return (len(hh) >= 2 and len(ll) >= 2 and (hh.iloc[-1] > hh.iloc[0]) and (ll.iloc[-1] > ll.iloc[0]))

def nearest_support_distance(close_val: float, support_levels: np.ndarray) -> float:
    if support_levels.size == 0:
        return np.inf
    return float(np.min(np.abs(support_levels - close_val)))

# ---------- base API ----------
class BaseStrategy:
    name = "base"
    default: Dict[str, Any] = {}

    def _resolve(self, p: Dict[str, Any] | None) -> Dict[str, Any]:
        # defaults -> instance attributes -> passed overrides
        params = dict(self.default)
        for k in self.default.keys():
            if hasattr(self, k):
                params[k] = getattr(self, k)
        if p:
            params.update(p)
        return params

    def fit(self, df: pd.DataFrame):  # placeholder
        return self

    def apply(self, df: pd.DataFrame, **p) -> pd.DataFrame:
        raise NotImplementedError

# ---------- 1) EMA + BB squeeze ----------
class EMAbbSqueeze(BaseStrategy):
    name = "ema_bb_squeeze"
    default = dict(ema_fast=12, ema_slow=26, bb_n=20, bb_k=2.0, bw_q=0.3, atr_n=14)
    def apply(self, df, **p):
        p = self._resolve(p)
        out = df.copy()
        out["ema_f"] = ema(out["close"], p["ema_fast"])
        out["ema_s"] = ema(out["close"], p["ema_slow"])
        ma, ub, lb, bw = bbands(out["close"], p["bb_n"], p["bb_k"])
        out["bw"] = bw
        thresh = out["bw"].quantile(p["bw_q"])
        out["squeeze"] = out["bw"] <= thresh
        out["long_signal"] = (out["ema_f"] > out["ema_s"]) & out["squeeze"]
        out["atr"] = atr(out, p["atr_n"])
        return out

# ---------- 2) RSI mean-reversion ----------
class RSIMeanRev(BaseStrategy):
    name = "rsi_meanrev"
    default = dict(rsi_n=14, buy_th=30, exit_th=50, min_atr=0.0, atr_n=14)
    def apply(self, df, **p):
        p = self._resolve(p)
        out = df.copy()
        out["rsi"] = rsi(out["close"], p["rsi_n"])
        out["atr"] = atr(out, p["atr_n"])
        out["long_signal"] = (out["rsi"] < p["buy_th"]) & (out["atr"] > p["min_atr"])
        out["exit_signal"] = (out["rsi"] > p["exit_th"])
        return out

# ---------- 3) Donchian breakout ----------
class DonchianBreakout(BaseStrategy):
    name = "donchian_breakout"
    default = dict(ch_n=20, atr_n=14)
    def apply(self, df, **p):
        p = self._resolve(p)
        out = df.copy()
        hh, ll = donchian(out, p["ch_n"])
        out["long_signal"] = out["close"] > hh.shift()
        out["atr"] = atr(out, p["atr_n"])
        return out

# ---------- 4) MA pullback + zscore ----------
class MAPullback(BaseStrategy):
    name = "ma_pullback"
    default = dict(ma_n=50, z_n=50, z_th=-1.0, atr_n=14)
    def apply(self, df, **p):
        p = self._resolve(p)
        out = df.copy()
        out["ma"] = ema(out["close"], p["ma_n"])
        z = (out["close"] - out["ma"]).rolling(int(p["z_n"]))\
            .apply(lambda x: (x[-1]-x.mean())/(x.std(ddof=0)+1e-9), raw=False)
        out["z"] = z
        out["long_signal"] = (out["close"] > out["ma"]) & (out["z"] < p["z_th"])
        out["atr"] = atr(out, p["atr_n"])
        return out

# ---------- 5) Evo combo (random linear combo of indicators) ----------
class EvoCombo(BaseStrategy):
    name = "evo_combo"
    default = dict(seed=42, atr_n=14)
    def apply(self, df, **p):
        p = self._resolve(p)
        rng = np.random.default_rng(int(p["seed"]))
        out = df.copy()
        feats = pd.DataFrame({
            "ema12": ema(out["close"],12),
            "ema26": ema(out["close"],26),
            "rsi14": rsi(out["close"],14),
            "atr14": atr(out,14),
        }, index=out.index)
        z = (feats - feats.rolling(100).mean()) / (feats.rolling(100).std(ddof=0)+1e-9)
        w = pd.Series(rng.normal(size=z.shape[1]), index=z.columns)
        score = (z * w).sum(axis=1)
        thr = score.rolling(200).quantile(0.7)
        out["score"] = score
        out["long_signal"] = score > thr
        out["atr"] = atr(out, p["atr_n"])
        return out

# ---------- 6) Naked Forex price-action ----------
class NakedFXPriceAction(BaseStrategy):
    """
    Price-action blend:
      - context: EMA trend or swing structure
      - S/R zones from recent swing-lows (support)
      - Bullish pin bar OR bullish engulfing near support
      - Optional breakout above last swing high + buffer
      - ATR-based stop/trail handled by runner
    """
    name = "naked_fx"
    default = dict(
        ema_fast=20, ema_slow=50,
        use_context="ema",      # 'ema' or 'structure'
        sw_n=3,                 # fractal width for swing flags
        swings_back=30,         # how many recent swings to build zones
        atr_n=14,
        zone_atr_mult=0.8,      # zone half-width in ATRs
        zone_touch_atr=0.5,     # consider "near support" if within this ATR distance
        pin_tail_min=0.6,       # >= 60% lower tail
        pin_body_max=0.35,      # <= 35% body
        use_engulfing=True,
        breakout_buffer_atr=0.15  # breakout above last swing high by this ATR buffer
    )

    def apply(self, df: pd.DataFrame, **p) -> pd.DataFrame:
        p = self._resolve(p)
        d = df.copy()
        d["atr"] = atr(d, p["atr_n"])

        # context: ema or structure
        d["ema_f"] = ema(d["close"], p["ema_fast"])
        d["ema_s"] = ema(d["close"], p["ema_slow"])
        ema_up = d["ema_f"] > d["ema_s"]

        HH, LL = swing_flags(d["high"], d["low"], p["sw_n"])
        d["swing_high"] = HH
        d["swing_low"]  = LL

        # collect recent support levels (last N swing lows)
        sup_levels = []
        for i in range(len(d)):
            if LL.iloc[i]:
                sup_levels.append(float(d["low"].iloc[i]))
        sup_levels_arr = np.array(sup_levels[-int(p["swings_back"]):], dtype=float)

        # last swing high level
        last_sh = d.loc[d["swing_high"], "high"]
        last_sh_level = float(last_sh.iloc[-1]) if not last_sh.empty else np.nan

        # compute proximity to support (per bar)
        dist_support = []
        for i in range(len(d)):
            dist_support.append(nearest_support_distance(float(d["close"].iloc[i]), sup_levels_arr))
        d["dist_support"] = np.array(dist_support)

        # pattern detections
        o, h, l, c = d["open"], d["high"], d["low"], d["close"]
        prev_o, prev_c = o.shift(1), c.shift(1)

        pin_bull = []
        eng_bull = []
        for i in range(len(d)):
            if i == 0:
                pin_bull.append(False); eng_bull.append(False); continue
            pin_bull.append(bullish_pinbar(o.iloc[i], h.iloc[i], l.iloc[i], c.iloc[i],
                                           p["pin_tail_min"], p["pin_body_max"]))
            eng_bull.append(bullish_engulf(prev_o.iloc[i], prev_c.iloc[i], o.iloc[i], c.iloc[i]))
        d["pin_bull"] = pd.Series(pin_bull, index=d.index)
        d["eng_bull"] = pd.Series(eng_bull, index=d.index)

        # near support?
        d["near_sup"] = d["dist_support"] <= (p["zone_touch_atr"] * d["atr"].clip(lower=1e-9))

        # breakout above last swing high + buffer
        buffer_px = p["breakout_buffer_atr"] * d["atr"]
        d["breakout"] = False
        if not math.isnan(last_sh_level):
            d["breakout"] = d["close"] > (last_sh_level + buffer_px)

        # context selection
        if str(p["use_context"]).lower() == "structure":
            ctx = d.index.map(lambda idx: structure_uptrend(d["high"].loc[:idx], d["low"].loc[:idx], look=5))
            ctx = pd.Series(ctx.values, index=d.index)
        else:
            ctx = ema_up

        # final signal: context + (pin OR engulf) near support  OR breakout
        d["long_signal"] = (ctx & d["near_sup"] & (d["pin_bull"] | (d["eng_bull"] if p["use_engulfing"] else False))) | d["breakout"]

        return d

# ---------- registry ----------
REGISTRY = {
    c.name: c for c in [EMAbbSqueeze, RSIMeanRev, DonchianBreakout, MAPullback, EvoCombo, NakedFXPriceAction]
}

def get_strategy(name: str) -> BaseStrategy:
    return REGISTRY[name]() if name in REGISTRY else EMAbbSqueeze()
