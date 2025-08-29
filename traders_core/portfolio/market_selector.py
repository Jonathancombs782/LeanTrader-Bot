from __future__ import annotations
import math
from typing import List, Dict, Any, Tuple
import pandas as pd
from traders_core.features.pipeline import make_features
from traders_core.utils.ta import atr
from traders_core.connectors.crypto_ccxt import ohlcv_df, market_info
from traders_core.mt5_adapter import copy_rates_days
from traders_core.features.pipeline import rates_to_df

def _norm(x: pd.Series) -> pd.Series:
    if x.std() == 0: return x*0
    return (x - x.mean()) / (x.std() + 1e-9)

def _score_series(df: pd.DataFrame, w: Dict[str,float]) -> float:
    feats = make_features(df)
    px = df["close"]
    # Momentum: recent 20-bar change
    trend = feats["mom20"].iloc[-1]
    # Vol usable: ATR normalized by price (scaled)
    vol = float(atr(df.tail(200), 14).iloc[-1] / (px.iloc[-1] + 1e-9))
    # Liquidity proxy: rolling volume (normalized)
    liq = float(df["volume"].tail(100).mean())
    # naive cost proxy (we down-weight if cost high; supplied separately)
    return w["w_trend"] * float(trend) + w["w_vol"] * float(vol) + w["w_liq"] * float(liq)

def _affordable_crypto(exchange: str, symbol: str, price: float, equity: float, min_buffer_pct: float) -> bool:
    m = market_info(exchange, symbol, True if price==0 else False)  # testnet flag doesn’t change min_cost typically
    budget = equity * (1.0 - min_buffer_pct)
    return budget >= float(m["min_cost"])

def compute_selection(cfg: dict, equity_crypto: float, equity_mt5: float, crypto_dfs: Dict[str,pd.DataFrame], fx_dfs: Dict[str,pd.DataFrame], exchange: str) -> Dict[str,Any]:
    # tiered concurrency
    K = cfg["selection"]["max_concurrent_base"]
    for tier in sorted(cfg["selection"]["tiers"], key=lambda t: t["min_equity"]):
        if equity_crypto >= tier["min_equity"]:
            K = max(K, int(round(cfg["selection"]["max_concurrent_base"] * tier["k"])))

    scored: List[Tuple[str,float,str]] = []  # (symbol, score, venue)
    w = cfg["selection"]["score"]
    min_score = cfg["selection"]["min_score"]
    buf = cfg["selection"]["min_cash_buffer_pct"]

    # Score crypto
    for sym, df in crypto_dfs.items():
        if df is None or len(df) < 60: continue
        s = _score_series(df, w)
        price = float(df["close"].iloc[-1])
        if not _affordable_crypto(exchange, sym, price, equity_crypto, buf):
            continue
        # approx fee/cost penalty
        cost_pen = 0.0015  # ~15 bps
        s_adj = s - w["w_cost"] * cost_pen
        if s_adj >= min_score:
            scored.append((sym, float(s_adj), "crypto"))

    # Score MT5
    for sym, df in fx_dfs.items():
        if df is None or len(df) < 60: continue
        s = _score_series(df, w)
        # FX min affordability checked in router via lot sizes; we allow here but still limit K
        cost_pen = 0.0004
        s_adj = s - w["w_cost"] * cost_pen
        if s_adj >= min_score:
            scored.append((sym, float(s_adj), "mt5"))

    # Sort by score desc and pick top K
    scored.sort(key=lambda t: t[1], reverse=True)
    pick = scored[:K]
    return {"selected": pick, "K": K}
