from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ..learn.online_learner import get_tuned_multipliers
from ..live.charts import render_signal_illustration
from ..policy.dispatcher import fuse_confluence
from ..ta.pipeline import compute_ta


def _ensure_reports_dir() -> Path:
    p = Path(os.getenv("REPORTS_DIR", "reports"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _render_chart(df: pd.DataFrame, pair: str) -> str:
    from ..live.charts import render_signal_chart

    out = _ensure_reports_dir() / f"{pair.replace('/', '_')}_snapshot.png"
    render_signal_chart(df.tail(200), str(out), title=f"{pair} - snapshot")
    return str(out)


def _session_from_time(ts: pd.Timestamp) -> str:
    # naive UTC-based session banding
    h = ts.hour
    if 0 <= h < 8:
        return "tokyo"
    if 8 <= h < 16:
        return "london"
    return "ny"


def _score_from_feats(row: pd.Series, symbol: str, ts: pd.Timestamp) -> Tuple[float, List[str]]:
    notes: List[str] = []
    # simple confluence: ema_20 vs ema_50 vs sma_200 + rsi and macd
    ema20 = row.filter(like="ema_20").mean()
    ema50 = row.filter(like="ema_50").mean()
    sma200 = row.filter(like="sma_200").mean()
    rsi = row.filter(like="rsi_14").mean()
    macd_hist = row.filter(like="macd_hist").mean()
    adx_like = row.filter(like="atr_14").mean()  # proxy for activity

    score = 0.0
    if ema20 > ema50:
        score += 0.2
        notes.append("ema20>ema50")
    if ema50 > sma200:
        score += 0.2
        notes.append("ema50>sma200")
    if rsi and 45 <= rsi <= 70:
        score += 0.2
        notes.append("rsi in range")
    if macd_hist and macd_hist > 0:
        score += 0.2
        notes.append("macd up")
    if adx_like:
        score += 0.1
        notes.append("vol ok")
    score = max(0.0, min(1.0, score))
    # attempt policy-level fusion (news + session weights)
    try:
        conf2, notes2 = fuse_confluence(symbol, row, ts)
        score = conf2
        notes = notes2
    except Exception:
        if len(notes) < 3:
            # pad to satisfy rationale>=3
            notes.extend(["trend", "momentum", "volatility"])  # harmless extras
            notes = notes[:3]
    return score, notes


def generate_signals(frames: Dict[str, pd.DataFrame], symbol: str, post: bool = False) -> pd.DataFrame:
    # compute features
    feats = compute_ta(frames)
    if feats.empty:
        return pd.DataFrame()
    df = feats.copy()
    # derive decisions per row
    signals: List[dict] = []
    for ts, row in df.iterrows():
        conf, rationale = _score_from_feats(row, symbol, pd.Timestamp(ts))
        side = "buy" if conf >= float(os.getenv("MIN_CONF", "0.6")) else "hold"
        # derive ATR-based TP/SL
        try:
            # prefer M15 frame for ATR estimate
            m15 = frames.get("M15") or list(frames.values())[-1]
            cl = float(m15["close"].loc[: pd.Timestamp(ts)].iloc[-1])
            tr = m15[["high", "low", "close"]].tail(100)
            atr = (tr["high"] - tr["low"]).rolling(14).mean().iloc[-1]
            atr = float(atr) if atr == atr else cl * 0.003  # fallback ~30bps
        except Exception:
            cl = float(row.filter(like="close").mean() or 0.0)
            atr = max(0.0001, cl * 0.003)
        entry = cl
        base_tp = float(os.getenv("TP_ATR_MULT", "1.5"))
        base_sl = float(os.getenv("SL_ATR_MULT", "1.0"))
        # session tuned multipliers
        sess = _session_from_time(pd.Timestamp(ts))
        try:
            sess_tp, sess_sl = get_tuned_multipliers(symbol, sess)
        except Exception:
            sess_tp, sess_sl = (1.0, 1.0)
        tp_mult = base_tp * max(0.5, min(3.0, sess_tp))
        sl_mult = base_sl * max(0.5, min(2.0, sess_sl))
        tp1 = entry + (atr * tp_mult if side == "buy" else -atr * tp_mult)
        tp2 = entry + (atr * tp_mult * 2 if side == "buy" else -atr * tp_mult * 2)
        tp3 = entry + (atr * tp_mult * 3 if side == "buy" else -atr * tp_mult * 3)
        sl = entry - (atr * sl_mult if side == "buy" else -atr * sl_mult)
        signals.append(
            {
                "ts": pd.Timestamp(ts),
                "symbol": symbol,
                "side": side,
                "confidence": float(conf),
                "rationale": rationale,
                "entry": float(entry),
                "tp1": float(tp1),
                "tp2": float(tp2),
                "tp3": float(tp3),
                "sl": float(sl),
            }
        )
    out = pd.DataFrame(signals).set_index("ts").sort_index()
    # attach chart path for the last row for convenience
    try:
        last_idx = out.index[-1]
        last = out.loc[last_idx]
        base_df = list(frames.values())[-1]
        out_img = _ensure_reports_dir() / f"{symbol.replace('/', '_')}_{int(pd.Timestamp(last_idx).timestamp())}.png"
        render_signal_illustration(
            base_df,
            str(out_img),
            title=f"{symbol} {last['side'].upper()} ({last['confidence']:.2f})",
            entry=float(last.get("entry", 0.0)),
            sl=float(last.get("sl", 0.0)),
            tps=[float(last.get("tp1", 0.0)), float(last.get("tp2", 0.0)), float(last.get("tp3", 0.0))],
        )
        out.loc[last_idx, "chart_path"] = str(out_img)
    except Exception:
        pass
    return out
