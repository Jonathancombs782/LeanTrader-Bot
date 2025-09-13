# awareness.py
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd
import time

@dataclass
class AwarenessConfig:
    atr_window: int = 14
    vol_spike_mult: float = 2.5       # ATR% vs median threshold
    ma_window: int = 50               # trend slope window
    max_risk_per_trade: float = 0.005  # 0.5% equity
    kelly_cap: float = 0.25           # use 25% of kelly fraction
    cooldown_minutes: int = 30
    max_dd_intraday: float = 0.03     # 3%
    news_blackout_min: int = 15

@dataclass
class GateDecision:
    allow: bool
    reason: str
    size_frac: float
    stop_atr: float
    take_atr: float

class SituationalAwareness:
    def __init__(self, cfg: AwarenessConfig):
        self.cfg = cfg
        self._cooldown_until = 0
        self._equity_high = None
        self._equity_start_day = None
        self._weights: Dict[str, float] = {}  # signal -> weight

    # ---------- features ----------
    def atr(self, close: pd.Series, high: pd.Series, low: pd.Series, n=14) -> pd.Series:
        # True range via pandas to preserve Series methods
        prev_close = close.shift(1)
        tr_components = pd.concat(
            [
                (high - low),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        )
        tr = tr_components.max(axis=1)
        return tr.rolling(int(n)).mean()

    def regime(self, close: pd.Series) -> str:
        ma = close.rolling(self.cfg.ma_window).mean()
        slope = (ma - ma.shift(5)) / 5.0
        atrp = (self.atr(close, close, close, self.cfg.atr_window) / close).fillna(0)
        med = atrp.rolling(100).median().iloc[-1] if len(atrp) >= 100 else atrp.median()
        spike = atrp.iloc[-1] > self.cfg.vol_spike_mult * (med or 1e-9)
        if spike:
            return "spike"
        if slope.iloc[-1] > 0:
            return "trend_up"
        if slope.iloc[-1] < 0:
            return "trend_down"
        return "range"

    # ---------- meta controls ----------
    def kelly(self, win_rate: float, payoff: float) -> float:
        p, b = win_rate, payoff
        if b <= 0:
            return 0.0
        f = (p - (1 - p) / b)
        return max(0.0, min(1.0, f))

    def throttle_size(self, base_conf: float, atrp: float, win_rate: float, payoff: float) -> float:
        k = self.kelly(win_rate, payoff) * self.cfg.kelly_cap
        vol_scale = max(0.25, 1.0 - 2.0 * (atrp - 0.01))  # reduce size when ATR% high
        return float(min(self.cfg.max_risk_per_trade, base_conf * k * vol_scale))

    def dynamic_levels(self, atr_val: float) -> Tuple[float, float]:
        return (1.5 * atr_val, 3.0 * atr_val)

    # ---------- state mgmt ----------
    def update_equity(self, equity: float):
        t = time.time()
        if self._equity_start_day is None or time.gmtime(t).tm_yday != time.gmtime(self._equity_start_day).tm_yday:
            self._equity_start_day = t
            self._equity_high = equity
        self._equity_high = max(self._equity_high or equity, equity)

    def intraday_dd(self, equity: float) -> float:
        if not self._equity_high:
            return 0.0
        return max(0.0, 1 - (equity / self._equity_high))

    def set_cooldown(self, minutes: Optional[int] = None):
        self._cooldown_until = max(self._cooldown_until, time.time() + 60 * (minutes or self.cfg.cooldown_minutes))

    def on_performance(self, rolling_win_rate: float, rolling_R: float):
        if rolling_win_rate < 0.4 or rolling_R < 0:
            self.set_cooldown()

    # ---------- main gate ----------
    def decide(self, df: pd.DataFrame, equity: float, base_conf: float,
               win_rate: float, payoff: float,
               high_impact_event_soon: bool = False) -> GateDecision:
        self.update_equity(equity)
        if time.time() < self._cooldown_until:
            return GateDecision(False, "cooldown", 0.0, 0.0, 0.0)

        if high_impact_event_soon:
            return GateDecision(False, "news_blackout", 0.0, 0.0, 0.0)

        dd = self.intraday_dd(equity)
        if dd > self.cfg.max_dd_intraday:
            self.set_cooldown(60)
            return GateDecision(False, "circuit_breaker_dd", 0.0, 0.0, 0.0)

        close = df["close"]
        high = df.get("high", df["close"])
        low = df.get("low", df["close"])
        atr_series = self.atr(close, high, low, self.cfg.atr_window)
        atr_val_raw = atr_series.iloc[-1]
        atr_val = float(atr_val_raw) if pd.notna(atr_val_raw) else 0.0
        last_px_raw = close.iloc[-1]
        last_px = float(last_px_raw) if pd.notna(last_px_raw) else 0.0
        if not np.isfinite(last_px) or last_px <= 0:
            last_px = 1e-9
        atrp = atr_val / last_px

        r = self.regime(close)
        conf = base_conf
        if r == "spike":
            conf *= 0.3
        elif r == "range":
            conf *= 0.8

        size = self.throttle_size(conf, atrp, win_rate, payoff)
        if size <= 0:
            return GateDecision(False, f"no_size_{r}", 0.0, 0.0, 0.0)

        sl_atr, tp_atr = self.dynamic_levels(atr_val)
        return GateDecision(True, f"ok_{r}", size, sl_atr, tp_atr)
