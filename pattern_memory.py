# pattern_memory.py
from __future__ import annotations

import csv, math, json, time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

# ---------------- paths ----------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEM_PATH   = DATA_DIR / "pattern_memory.csv"   # point-in-time snapshots
SCORES_PATH= DATA_DIR / "pattern_scores.json"  # aggregated pattern stats

# ---------------- schema ----------------
FEATS = ["ret1", "ret3", "ret5", "atr", "rsi", "bb_bw", "ema_slope"]
HEAD  = ["symbol", "tf", "ts", "entry_price", *FEATS, "outcome", "label", "meta"]

def _ensure_header() -> None:
    if not MEM_PATH.exists():
        with open(MEM_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEAD)

# ---------------- feature engineering ----------------
def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
    d = series.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))

def features(df: pd.DataFrame) -> Dict[str, float]:
    """
    df columns expected: ['time','open','high','low','close','volume'] (extras ignored)
    Returns a small, cheap feature vector for similarity & bucketing.
    """
    d = df.copy()
    close = d["close"].astype(float)
    high  = d["high"].astype(float)
    low   = d["low"].astype(float)

    d["ret"] = close.pct_change()

    ema = close.ewm(span=20, adjust=False).mean()
    ma  = close.rolling(20).mean()
    sd  = close.rolling(20).std(ddof=0)
    # Bollinger Band width / mid
    bbw = (ma + 2 * sd - (ma - 2 * sd)) / ma.replace(0, np.nan)

    tr  = pd.concat(
        [(high - low),
         (high - close.shift()).abs(),
         (low  - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    rsi = _rsi(close, 14)

    f = {
        "ret1": float(d["ret"].iloc[-1]),
        "ret3": float(d["ret"].rolling(3).sum().iloc[-1]),
        "ret5": float(d["ret"].rolling(5).sum().iloc[-1]),
        "atr":  float(atr.iloc[-1] / max(1e-9, close.iloc[-1])),
        "rsi":  float(rsi.iloc[-1]),
        "bb_bw": float(bbw.iloc[-1]),
        "ema_slope": float(ema.iloc[-1] - ema.iloc[-5]) if len(ema) >= 5 else 0.0,
    }
    # sanitize NaN/inf
    return {k: (0.0 if (math.isnan(v) or math.isinf(v)) else v) for k, v in f.items()}

# ---------------- persistence ----------------
def record(symbol: str,
           tf: str,
           df_on_entry: pd.DataFrame,
           entry_price: float,
           meta: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """
    Take a point-in-time snapshot at entry. 'outcome' and 'label' can be set later.
    Returns the computed features so the caller can use them immediately.
    """
    _ensure_header()
    f = features(df_on_entry)
    row = [
        str(symbol).upper(),
        str(tf).lower(),
        int(time.time()),
        float(entry_price),
        *[f[k] for k in FEATS],
        0.0,                     # outcome (to be filled later, e.g., R multiple or pct)
        "",                      # label: "win" | "loss" | ""
        json.dumps(meta or {}, ensure_ascii=False),
    ]
    with open(MEM_PATH, "a", newline="", encoding="utf-8") as fp:
        csv.writer(fp).writerow(row)
    return f

def _load_memory() -> pd.DataFrame:
    _ensure_header()
    try:
        df = pd.read_csv(MEM_PATH)
        for k in FEATS + ["entry_price", "outcome"]:
            if k in df.columns:
                df[k] = pd.to_numeric(df[k], errors="coerce")
        if "ts" in df.columns:
            df["ts"] = pd.to_numeric(df["ts"], errors="coerce").fillna(0).astype("int64")
        return df.fillna({"label": ""})
    except Exception:
        return pd.DataFrame(columns=HEAD)

def set_outcome(symbol: str,
                tf: str,
                ts: int,
                outcome: float,
                label: str = "") -> bool:
    """
    Update a specific snapshot (by symbol/tf/ts) with realized outcome and label.
    'outcome' can be R multiple or % return; 'label' is optional ("win"/"loss").
    """
    df = _load_memory()
    if df.empty: return False
    m = (df["symbol"].astype(str).str.upper() == str(symbol).upper()) & \
        (df["tf"].astype(str).str.lower()    == str(tf).lower()) & \
        (df["ts"].astype(int)                == int(ts))
    if not m.any(): return False
    df.loc[m, "outcome"] = float(outcome)
    if label:
        df.loc[m, "label"] = str(label)
    df.to_csv(MEM_PATH, index=False)
    return True

# ---------------- similarity recall ----------------
def recall(symbol: str,
           tf: str,
           df_now: pd.DataFrame,
           k: int = 200,
           same_symbol_only: bool = False) -> Dict[str, Any]:
    """
    Find similar past snapshots and summarize their outcomes.
    """
    mem = _load_memory()
    if mem.empty:
        return {"note": "no memory"}

    # Optionally focus on same symbol/tf for tighter context
    q = mem[mem["tf"].astype(str).str.lower() == str(tf).lower()]
    if same_symbol_only:
        q = q[q["symbol"].astype(str).str.upper() == str(symbol).upper()]
    if q.empty:
        return {"note": "no memory for tf/symbol"}

    # ensure numeric
    for kf in FEATS:
        q[kf] = pd.to_numeric(q[kf], errors="coerce").fillna(0.0)

    f = features(df_now)
    x = np.array([f[k] for k in FEATS], dtype=float)
    X = q[FEATS].to_numpy(dtype=float)

    xnorm = np.linalg.norm(x) or 1.0
    Xnorm = np.linalg.norm(X, axis=1) + 1e-12
    sims = (X @ x) / (Xnorm * xnorm)

    q = q.assign(sim=sims).sort_values("sim", ascending=False).head(k)
    avg_outcome = float(pd.to_numeric(q["outcome"], errors="coerce").mean())
    winrate = float((q["label"].astype(str) == "win").mean() * 100.0)
    sim_med = float(q["sim"].median()) if len(q) else 0.0

    return {
        "avg_outcome": avg_outcome,
        "similarity": sim_med,
        "winrate": winrate,
        "n_top": int(len(q)),
        "note": f"mem={len(mem)} top={len(q)} sim≈{sim_med:.2f} avg_out≈{avg_outcome:.4f} winrate≈{winrate:.1f}%",
    }

# ---------------- pattern bucketing ----------------
def _bin(v: float, step: float, lo: float = None, hi: float = None) -> int:
    if math.isnan(v) or math.isinf(v): v = 0.0
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return int(round(v / step))

def pattern_key_from_feats(f: Dict[str, float]) -> str:
    """
    Coarse buckets for robust generalization across regimes.
    """
    return "|".join([
        f"r1:{_bin(f.get('ret1',0.0), 0.001, -0.05, 0.05)}",
        f"r3:{_bin(f.get('ret3',0.0), 0.003, -0.10, 0.10)}",
        f"r5:{_bin(f.get('ret5',0.0), 0.005, -0.15, 0.15)}",
        f"atr:{_bin(f.get('atr',0.0), 0.0005, 0.0, 0.1)}",
        f"rsi:{_bin((f.get('rsi',50.0)-50.0)/50.0, 0.1, -1.0, 1.0)}",  # center on 50
        f"bbw:{_bin(f.get('bb_bw',0.0), 0.05, 0.0, 2.0)}",
        f"ema:{_bin(f.get('ema_slope',0.0), 0.001, -0.05, 0.05)}",
    ])

def recompute_scores() -> None:
    """
    Aggregate outcomes per coarse pattern key across the entire memory
    to produce robust priors used by get_score().
    """
    df = _load_memory()
    if df.empty:
        with open(SCORES_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return

    for kf in FEATS + ["outcome"]:
        df[kf] = pd.to_numeric(df[kf], errors="coerce").fillna(0.0)

    # only rows with known outcome
    df = df[pd.to_numeric(df["outcome"], errors="coerce").notna()]

    wins: Dict[str, int] = defaultdict(int)
    total: Dict[str, int] = defaultdict(int)
    rsum: Dict[str, float] = defaultdict(float)

    for _, row in df.iterrows():
        f = {k: float(row[k]) for k in FEATS}
        key = pattern_key_from_feats(f)
        r   = float(row["outcome"])
        total[key] += 1
        rsum[key]  += r
        if str(row.get("label","")).lower() == "win" or r > 0:
            wins[key] += 1

    scores = {
        k: {
            "winrate": (wins[k] / total[k]) if total[k] else 0.5,
            "avg_out": (rsum[k] / total[k]) if total[k] else 0.0,
            "n": total[k],
        }
        for k in total.keys()
    }
    with open(SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)

def get_score(sig: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast prior from global pattern stats.
    'sig' should carry either:
      - 'feats' dict with FEATS; OR
      - the FEATS directly as keys.
    Returns dict with winrate/avg_out/n; falls back to neutral priors.
    """
    # extract features from the signal
    feats = sig.get("feats") if isinstance(sig.get("feats"), dict) else \
            {k: sig[k] for k in FEATS if k in sig}

    if len(feats) != len(FEATS):
        return {"winrate": 0.5, "avg_out": 0.0, "n": 0}

    key = pattern_key_from_feats({k: float(feats[k]) for k in FEATS})

    try:
        with open(SCORES_PATH, "r", encoding="utf-8") as f:
            scores = json.load(f)
        return scores.get(key, {"winrate": 0.5, "avg_out": 0.0, "n": 0})
    except Exception:
        return {"winrate": 0.5, "avg_out": 0.0, "n": 0}

# ---------------- module exports ----------------
__all__ = [
    "features",
    "record",
    "set_outcome",
    "recall",
    "recompute_scores",
    "get_score",
    "pattern_key_from_feats",
    "FEATS",
    "MEM_PATH",
    "SCORES_PATH",
]
