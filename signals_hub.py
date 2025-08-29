# signals_hub.py
# Ultra analyzers for CCXT (crypto) and MT5 (FX) + multi-TF confirmation.
from __future__ import annotations

import os
import math
from typing import Dict, Any, List, Tuple, Optional

# numpy only; pandas optional (we handle absence gracefully)
import numpy as np
try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # pandas is optional


# ==============================
# --------- UTILITIES ----------
# ==============================

def _envf(k: str, d: float) -> float:
    try:
        return float(os.getenv(k, str(d)))
    except Exception:
        return d

def _clip01(x: float) -> float:
    return 0.0 if not np.isfinite(x) else max(0.0, min(1.0, float(x)))

def _to_numpy_ohlcv(bars) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Accepts:
      - list[list] like ccxt: [ts, o, h, l, c, v]
      - pandas.DataFrame with columns (open,high,low,close,vol|tick_volume)
    Returns 6 numpy arrays (ts, o, h, l, c, v) with float dtype.
    Volume is 0.0 if missing.
    """
    if bars is None:
        return (np.array([]),)*6

    # DataFrame path
    if pd is not None and isinstance(bars, pd.DataFrame):
        cols = {c.lower(): c for c in bars.columns}
        ts = None
        for tkey in ("timestamp", "time", "ts"):
            if tkey in cols:
                ts = bars[cols[tkey]].astype("int64", errors="ignore").to_numpy()
                break
        if ts is None:
            # fabricate sequential timestamps if absent
            ts = np.arange(len(bars))

        vcol = cols.get("vol") or cols.get("tick_volume") or cols.get("volume") or cols.get("real_volume")
        vol = bars[vcol].astype(float).to_numpy() if vcol else np.zeros(len(bars), dtype=float)

        o = bars[cols.get("open", "open")].astype(float).to_numpy()
        h = bars[cols.get("high", "high")].astype(float).to_numpy()
        l = bars[cols.get("low", "low")].astype(float).to_numpy()
        c = bars[cols.get("close", "close")].astype(float).to_numpy()
        return ts.astype(float), o, h, l, c, vol

    # list-of-lists path (ccxt)
    arr = np.array(bars, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 5:
        return (np.array([]),)*6
    ts = arr[:, 0]
    o  = arr[:, 1]
    h  = arr[:, 2]
    l  = arr[:, 3]
    c  = arr[:, 4]
    v  = arr[:, 5] if arr.shape[1] >= 6 else np.zeros(arr.shape[0], dtype=float)
    return ts, o, h, l, c, v


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    if len(x) == 0:
        return np.array([])
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i-1]
    return out


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    if len(c) == 0:
        return np.array([])
    prev_c = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum.reduce([
        h - l,
        np.abs(h - prev_c),
        np.abs(l - prev_c)
    ])
    # Wilder's smoothing (EMA with alpha=1/n)
    alpha = 1.0 / float(n)
    atr = np.empty_like(tr, dtype=float)
    atr[0] = tr[:n].mean() if len(tr) >= n else tr[0]
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
    return atr


def _rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    if len(c) < 2:
        return np.zeros_like(c)
    delta = np.diff(c, prepend=c[0])
    up = np.clip(delta, 0, None)
    dn = -np.clip(delta, None, 0)
    # Wilder
    alpha = 1.0 / n
    roll_up = np.empty_like(c, dtype=float); roll_dn = np.empty_like(c, dtype=float)
    roll_up[0] = up[:n].mean() if len(up) >= n else up[0]
    roll_dn[0] = dn[:n].mean() if len(dn) >= n else dn[0]
    for i in range(1, len(c)):
        roll_up[i] = alpha * up[i] + (1 - alpha) * roll_up[i-1]
        roll_dn[i] = alpha * dn[i] + (1 - alpha) * roll_dn[i-1]
    rs = np.divide(roll_up, np.maximum(1e-12, roll_dn))
    return 100.0 - (100.0 / (1.0 + rs))


def _bbands(c: np.ndarray, n: int = 20, k: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(c) < n:
        m = np.full_like(c, np.nan)
        return m, m, m, m
    # moving average + std (simple)
    ma = np.convolve(c, np.ones(n)/n, mode="same")
    # naive rolling std
    pad = n // 2
    std = np.array([np.nanstd(c[max(0, i-pad):min(len(c), i+pad+1)], ddof=0) for i in range(len(c))])
    upper = ma + k * std
    lower = ma - k * std
    bbw = np.divide(upper - lower, np.maximum(1e-12, ma))
    return ma, upper, lower, bbw


def _macd(c: np.ndarray, fast: int = 12, slow: int = 26, sig: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(c) == 0:
        z = np.array([])
        return z, z, z
    ema_fast = _ema(c, fast)
    ema_slow = _ema(c, slow)
    macd = ema_fast - ema_slow
    signal = _ema(macd, sig)
    hist = macd - signal
    return macd, signal, hist


def _tf_minutes(tf: str) -> int:
    tf = str(tf).lower().strip()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    raise ValueError(f"Unsupported tf: {tf}")


def _aggregate_ohlc(
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray, step: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Downsample by grouping last 'step' bars. Keeps last incomplete group too.
    """
    if step <= 1 or len(c) < step:
        return o, h, l, c, v
    n = int(math.ceil(len(c) / step))
    O = np.empty(n); H = np.empty(n); L = np.empty(n); C = np.empty(n); V = np.empty(n)
    idx = 0
    for i in range(n):
        j0 = idx
        j1 = min(len(c), idx + step)
        O[i] = o[j0]
        H[i] = np.max(h[j0:j1])
        L[i] = np.min(l[j0:j1])
        C[i] = c[j1-1]
        V[i] = np.sum(v[j0:j1])
        idx = j1
    return O, H, L, C, V


def _hh_ll(h: np.ndarray, l: np.ndarray, lookback: int = 8) -> Tuple[bool, bool]:
    """Higher-high / lower-low structure over the last 'lookback' bars."""
    if len(h) < lookback + 2:
        return False, False
    hh = float(h[-1]) > float(np.max(h[-lookback-1:-1]))
    ll = float(l[-1]) < float(np.min(l[-lookback-1:-1]))
    return hh, ll


# ==================================
# ----- CORE SIGNAL CONSTRUCTION ----
# ==================================

def _build_signal_common(
    symbol: str, tf: str, market: str, side: str, c: np.ndarray, h: np.ndarray, l: np.ndarray,
    atr_last: float, ema_fast_last: float, ema_slow_last: float, bbw_last: float, rsi_last: float,
    macd_hist_last: float, reasons: List[str]
) -> Dict[str, Any]:
    price = float(c[-1])
    # SL/TP geometry
    # ATR multipliers tuned per tf
    tfm = _tf_minutes(tf)
    atr_mult = {
        1: 1.25, 3: 1.35, 5: 1.55, 15: 1.8, 60: 2.2
    }.get(tfm, 1.8)
    sl = price - atr_mult * atr_last if side == "buy" else price + atr_mult * atr_last
    R = abs(price - sl)
    tp1 = price + R if side == "buy" else price - R
    tp2 = price + 2*R if side == "buy" else price - 2*R
    tp3 = price + 3*R if side == "buy" else price - 3*R

    # Confidence scoring
    # components in [0,1]
    trend_align = 1.0 if ((side == "buy" and ema_fast_last > ema_slow_last) or
                          (side == "sell" and ema_fast_last < ema_slow_last)) else 0.0
    mom_align   = _clip01(0.5 + 0.5*np.sign(macd_hist_last) * (1 if side == "buy" else -1))
    vol_ok      = _clip01((bbw_last - _envf("VOL_BBW_MIN", 0.01)) / max(1e-6, _envf("VOL_BBW_MAX", 0.08)))
    # prefer RSI 45-65 for trend-follow longs; 35-55 for shorts
    if side == "buy":
        rsi_score = _clip01(1.0 - abs(rsi_last - 55.0)/35.0)
    else:
        rsi_score = _clip01(1.0 - abs(rsi_last - 45.0)/35.0)

    conf = 0.45*trend_align + 0.25*mom_align + 0.15*vol_ok + 0.15*rsi_score
    conf = _clip01(conf)

    return {
        "market": market,
        "symbol": symbol,
        "tf": tf,
        "side": side,
        "entry": price,
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "confidence": float(conf),
        "quality": float(conf),
        "context": reasons
    }


def _analyze_core(symbol: str, tf: str, market: str, bars) -> Optional[Dict[str, Any]]:
    ts, o, h, l, c, v = _to_numpy_ohlcv(bars)
    if len(c) < 60:
        return None

    # indicators
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    atr14 = _atr(h, l, c, 14)
    rsi14 = _rsi(c, 14)
    ma20, bbU, bbL, bbw = _bbands(c, n=20, k=2.0)
    macd, macs, hist = _macd(c, 12, 26, 9)

    # sanity guards
    last_price = float(c[-1])
    last_atr   = float(atr14[-1]) if np.isfinite(atr14[-1]) else 0.0
    last_bbw   = float(bbw[-1]) if np.isfinite(bbw[-1]) else 0.0
    if last_price <= 0 or last_atr <= 0:
        return None

    # basic regime choice: trend-follow if ema20 vs ema50 is clear, else fade extremes (disabled by default)
    slope = float(ema20[-1] - ema20[-5]) if len(ema20) >= 5 else 0.0
    trend_buy  = ema20[-1] > ema50[-1] and slope > 0
    trend_sell = ema20[-1] < ema50[-1] and slope < 0

    reasons: List[str] = []
    hh, ll = _hh_ll(h, l, lookback=8)
    if trend_buy:
        reasons.append("EMA20>EMA50 & rising")
    if trend_sell:
        reasons.append("EMA20<EMA50 & falling")
    if hh:
        reasons.append("HH structure")
    if ll:
        reasons.append("LL structure")
    reasons.append(f"ATR={last_atr:.6g}  BBw={last_bbw:.4f}  MACDhist={hist[-1]:.6g}  RSI={rsi14[-1]:.1f}")

    # pick side
    side = "buy" if trend_buy else ("sell" if trend_sell else None)
    if side is None:
        # momentum fallback if trend ambiguous
        side = "buy" if hist[-1] > 0 else "sell"
        reasons.append("Fallback to MACD momentum")

    return _build_signal_common(
        symbol, tf, market, side, c, h, l,
        atr_last=abs(last_atr),
        ema_fast_last=float(ema20[-1]),
        ema_slow_last=float(ema50[-1]),
        bbw_last=max(0.0, last_bbw),
        rsi_last=float(rsi14[-1]),
        macd_hist_last=float(hist[-1]),
        reasons=reasons
    )


# ==================================
# -------- PUBLIC ANALYZERS --------
# ==================================

def analyze_symbol_ccxt(bars, tf: str, symbol: str, market: str = "spot") -> Optional[Dict[str, Any]]:
    """
    bars: CCXT OHLCV arrays (or pandas DataFrame)
    Returns a normalized signal dict or None.
    """
    try:
        sig = _analyze_core(symbol, tf, f"crypto-{market}", bars)
        # attach small bar tail for MTF confirm (keep it light)
        if sig:
            _, o, h, l, c, v = _to_numpy_ohlcv(bars)
            tail = min(600, len(c))
            sig["bars_tail"] = np.column_stack([
                # ts omitted to reduce payload; MTF uses bar counts
                o[-tail:], h[-tail:], l[-tail:], c[-tail:], v[-tail:]
            ]).tolist()
        return sig
    except Exception as e:
        print(f"[analyze_symbol_ccxt error] {symbol}: {e}")
        return None


def analyze_symbol_mt5(bars, tf: str, symbol: str) -> Optional[Dict[str, Any]]:
    """
    bars: MT5 dataframe (copy_rates_from_pos) or list-like. We do **not** rely on a 'tid' column.
    """
    try:
        sig = _analyze_core(symbol, tf, "fx", bars)
        if sig:
            _, o, h, l, c, v = _to_numpy_ohlcv(bars)
            tail = min(600, len(c))
            sig["bars_tail"] = np.column_stack([o[-tail:], h[-tail:], l[-tail:], c[-tail:], v[-tail:]]).tolist()
        return sig
    except Exception as e:
        print(f"[analyze_symbol_mt5 error] {symbol}: {e}")
        return None


# ==================================
# --------- MTF CONFIRMATION -------
# ==================================

def _confirm_side_from_bars(tf_minutes: int, side: str, bars_tail: List[List[float]]) -> Tuple[bool, List[str]]:
    """
    Down-sample the provided tail to higher TFs and confirm trend alignment.
    bars_tail: list of [o,h,l,c,v] floats
    """
    try:
        arr = np.array(bars_tail, dtype=float)
        if arr.ndim != 2 or arr.shape[1] < 4 or len(arr) < 40:
            return True, ["MTF: skipped (insufficient bars)"]

        o, h, l, c, v = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], (arr[:, 4] if arr.shape[1] >= 5 else np.zeros(len(arr)))

        # pick two higher TF steps, e.g. 1m->(5m,15m), 5m->(15m,60m)
        if tf_minutes <= 1:
            steps = (5, 15)
        elif tf_minutes <= 3:
            steps = (5, 15)
        elif tf_minutes <= 5:
            steps = (3, 12)   # 5m*3=15m, *12=1h
        elif tf_minutes <= 15:
            steps = (4, 12)   # 15m*4=1h, *12=3h (approx)
        else:
            steps = (2, 4)

        for s in steps:
            O, H, L, C, V = _aggregate_ohlc(o, h, l, c, v, step=s)
            if len(C) < 30:
                continue
            ema20 = _ema(C, 20); ema50 = _ema(C, 50)
            slope = ema20[-1] - ema20[-5] if len(ema20) >= 5 else 0.0
            good = (side == "buy" and ema20[-1] > ema50[-1] and slope > 0) or \
                   (side == "sell" and ema20[-1] < ema50[-1] and slope < 0)
            if not good:
                return False, [f"MTF {s}x disagree (EMA20/50 slope)"]
        return True, [f"MTF aligned ({steps[0]}x & {steps[1]}x)"]
    except Exception:
        return True, ["MTF: error (ignored)"]


def mtf_confirm(sig: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Decide whether to keep the signal after higher-timeframe confirmation.
    Returns (ok, context_lines).
    If no bar tail present, we don't block — we just pass with a gentle note.
    """
    try:
        tfm = _tf_minutes(sig.get("tf", "5m"))
        side = sig.get("side", "buy")
        tail = sig.get("bars_tail")
        if not tail:
            return True, ["MTF: no bars_tail (skipped)"]

        ok, ctx = _confirm_side_from_bars(tfm, side, tail)
        # small confidence bump on strong agreement
        if ok and "aligned" in " ".join(ctx).lower():
            sig["confidence"] = _clip01(sig.get("confidence", 0.0) * 1.05 + 0.05)
            sig["quality"] = sig["confidence"]
        return ok, ctx
    except Exception:
        return True, []  # never hard-fail MTF
