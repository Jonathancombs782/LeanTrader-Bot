# ledger.py
from __future__ import annotations
import csv, os, math, json, time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import pandas as pd

DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
LEDGER   = DATA_DIR / "ledger.csv"

HEADERS = [
    "ts_entry","date","venue","market","symbol","tf","side",
    "entry_px","qty","sl","tp","meta",
    "ts_exit","exit_px","pnl_raw","pnl_r","hold_min","status"  # status: open|closed|stopped|tp
]

def _utc_now() -> int:
    return int(time.time())

def _ensure_file():
    if not LEDGER.exists():
        with open(LEDGER, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADERS)

def log_entry(*, venue:str, market:str, symbol:str, tf:str, side:str,
              entry_px:float, qty:float, sl:float|None=None, tp:float|None=None,
              meta:Dict[str,Any]|None=None) -> str:
    """
    Returns trade_id = f"{symbol}|{tf}|{ts_entry}"
    """
    _ensure_file()
    ts = _utc_now()
    row = [
        ts,
        datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
        venue, market, symbol, tf, side.lower(),
        float(entry_px), float(qty), float(sl or 0.0), float(tp or 0.0),
        json.dumps(meta or {}),
        "", "", "", "", "", "open"
    ]
    with open(LEDGER, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    return f"{symbol}|{tf}|{ts}"

def log_exit(trade_id: str, *, exit_px: float, status: str = "closed") -> None:
    """
    id format: symbol|tf|ts_entry
    Computes pnl_raw (quote units) and pnl_r (R-multiple) from saved SL/TP.
    """
    _ensure_file()
    sym, tf, ts_s = trade_id.split("|")
    ts_entry = int(ts_s)
    df = pd.read_csv(LEDGER)
    idx = (df["ts_entry"] == ts_entry) & (df["symbol"] == sym) & (df["tf"] == tf)
    if not idx.any():
        return

    row = df[idx].iloc[0].copy()
    side    = str(row["side"])
    entry   = float(row["entry_px"])
    sl      = float(row.get("sl", 0.0))
    ts_now  = _utc_now()

    qty     = float(row["qty"])
    exit_px = float(exit_px)

    # raw PnL in quote currency for spot/futures (sign by side)
    pnl_raw = (exit_px - entry) * qty if side == "buy" else (entry - exit_px) * qty

    # R-multiple: distance to SL (if present); fallback to |entry|*0.003 (0.3%) to avoid /0
    risk_per_unit = abs(entry - sl) if sl and sl > 0 else max(1e-9, abs(entry) * 0.003)
    pnl_r = ((exit_px - entry) / risk_per_unit) if side == "buy" else ((entry - exit_px) / risk_per_unit)

    hold_min = max(0.0, (ts_now - ts_entry) / 60.0)

    # write back
    df.loc[idx, "ts_exit"]  = ts_now
    df.loc[idx, "exit_px"]  = exit_px
    df.loc[idx, "pnl_raw"]  = pnl_raw
    df.loc[idx, "pnl_r"]    = pnl_r
    df.loc[idx, "hold_min"] = hold_min
    df.loc[idx, "status"]   = status

    df.to_csv(LEDGER, index=False)

def daily_pnl_text(day: Optional[str] = None) -> str:
    """
    Returns a compact Markdown summary of today’s (or given YYYY-MM-DD) PnL.
    """
    _ensure_file()
    df = pd.read_csv(LEDGER)
    if df.empty:
        return "No trades yet."

    if not day:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sub = df[(df["date"] == day) & (df["status"] != "open")].copy()
    if sub.empty:
        return f"*Daily PnL — {day}*\nNo closed trades."

    wins = (sub["pnl_raw"] > 0).sum()
    losses = (sub["pnl_raw"] <= 0).sum()
    gross = float(sub["pnl_raw"].sum())
    rsum  = float(sub["pnl_r"].sum())
    wr    = (wins / max(1, (wins + losses))) * 100.0
    n     = len(sub)

    lines = [f"*Daily PnL — {day}*",
             f"Trades: `{n}` | Winrate: `{wr:.1f}%`",
             f"Gross PnL: `{gross:.4f}` (quote) | Sum R: `{rsum:.2f}`",
             "— Top 5:"]
    sub = sub.sort_values("pnl_raw", ascending=False).head(5)
    for _, r in sub.iterrows():
        lines.append(f"• `{r['symbol']}` {r['side']} tf=`{r['tf']}`  R=`{float(r['pnl_r']):.2f}`  PnL=`{float(r['pnl_raw']):.4f}`")
    return "\n".join(lines)

def open_positions() -> List[Dict[str,Any]]:
    _ensure_file()
    try:
        df = pd.read_csv(LEDGER)
        open_df = df[df["status"] == "open"].copy()
        return open_df.to_dict(orient="records")
    except Exception:
        return []
