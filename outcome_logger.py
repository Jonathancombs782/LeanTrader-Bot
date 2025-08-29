# outcome_logger.py
from __future__ import annotations
import os, json, csv, time, math, hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

# Optional: feature snapshot at entry -> pattern_memory.csv
try:
    import pandas as pd  # only used if df_snapshot is provided
except Exception:
    pd = None

DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS  = Path("reports"); REPORTS.mkdir(parents=True, exist_ok=True)

LEDGER_CSV  = DATA_DIR / "ledger.csv"               # append all closed trades
MEMORY_CSV  = DATA_DIR / "pattern_memory.csv"       # features + outcome/label
TRADES_ROLL = REPORTS                                # NDJSON per day: trades-YYYYMMDD.ndjson

# ----------------- utils -----------------
def _utc_ts() -> int:
    return int(time.time())

def _day_key(ts: Optional[int] = None) -> str:
    dt = datetime.fromtimestamp(ts or _utc_ts(), tz=timezone.utc)
    return dt.strftime("%Y%m%d")

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def _ensure_ledgers():
    if not LEDGER_CSV.exists():
        with open(LEDGER_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "id","opened_at","closed_at","market","venue","symbol","tf","side",
                "entry","sl","tp1","tp2","tp3","qty","exit_price","exit_reason",
                "hold_sec","pnl","pnl_r","hit_tp1","hit_tp2","hit_tp3","win",
                "mem_ts"
            ])
    if not MEMORY_CSV.exists():
        with open(MEMORY_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "symbol","tf","ts","entry_price",
                "ret1","ret3","ret5","atr","rsi","bb_bw","ema_slope",
                "outcome","label","meta"
            ])

def _hash(obj: Dict[str, Any]) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",",":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ----------------- tiny feature snapshot (cheap, matches your pattern_memory schema) -----------------
def _features_from_df(df) -> Dict[str, float]:
    if pd is None or df is None or len(df) < 25:
        return {}
    d = df.copy()
    if "close" not in d.columns or "high" not in d.columns or "low" not in d.columns:
        return {}
    d["ret"] = d["close"].pct_change()
    ema = d["close"].ewm(span=20, adjust=False).mean()
    ma  = d["close"].rolling(20).mean()
    sd  = d["close"].rolling(20).std(ddof=0)
    bbw = (ma + 2*sd - (ma - 2*sd)) / ma.replace(0, 1.0)
    tr  = (pd.concat([(d["high"]-d["low"]),
                      (d["high"]-d["close"].shift()).abs(),
                      (d["low"]-d["close"].shift()).abs()], axis=1).max(axis=1))
    atr = tr.rolling(14).mean()
    # RSI
    delta = d["close"].diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean()
    rs = up / down.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))
    out = {
        "ret1": float(d["ret"].iloc[-1]),
        "ret3": float(d["ret"].rolling(3).sum().iloc[-1]),
        "ret5": float(d["ret"].rolling(5).sum().iloc[-1]),
        "atr":  float((atr.iloc[-1] or 0.0) / max(1e-9, d["close"].iloc[-1])),
        "rsi":  float(rsi.iloc[-1] if pd.notna(rsi.iloc[-1]) else 50.0),
        "bb_bw": float(bbw.iloc[-1]),
        "ema_slope": float((ema.iloc[-1] or 0.0) - (ema.iloc[-5] if len(ema) >= 5 else ema.iloc[-1] or 0.0)),
    }
    for k,v in out.items():
        if v is None or math.isnan(v) or math.isinf(v):
            out[k] = 0.0
    return out

def _append_ndjson(day: str, payload: Dict[str, Any]) -> None:
    path = TRADES_ROLL / f"trades-{day}.ndjson"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

# ----------------- main logger -----------------
class OutcomeLogger:
    """
    Usage:
      logger = OutcomeLogger()
      tid = logger.open_trade(market="fx", venue="mt5", symbol="EURUSD", tf="M5",
                              side="buy", entry=1.08500, qty=0.02, sl=1.08350,
                              tp1=1.0860, tp2=1.0870, tp3=1.0890,
                              df_snapshot=<bars df>, meta={"source":"brain"})
      ...
      logger.mark_exit(tid, exit_price=1.0862, reason="TP1")
    """
    def __init__(self):
        _ensure_ledgers()
        self._open: Dict[str, Dict[str, Any]] = {}

    # ---------- open ----------
    def open_trade(
        self,
        market: str, venue: str, symbol: str, tf: str,
        side: str, entry: float, qty: float,
        sl: Optional[float] = None, tp1: Optional[float] = None,
        tp2: Optional[float] = None, tp3: Optional[float] = None,
        df_snapshot=None, meta: Optional[Dict[str,Any]] = None
    ) -> str:
        ts = _utc_ts()
        base = {
            "t":"open","ts":ts,"iso":_now_iso(),
            "market":market,"venue":venue,"symbol":symbol,"tf":tf,"side":side,
            "entry":float(entry),"sl":float(sl or 0.0),
            "tp1":float(tp1 or 0.0),"tp2":float(tp2 or 0.0),"tp3":float(tp3 or 0.0),
            "qty":float(qty or 0.0),
            "meta":meta or {}
        }
        tid = _hash({k:base[k] for k in ("market","venue","symbol","tf","side","entry","ts")})
        base["id"] = tid

        # optional: snapshot features + write a pending memory row
        mem_ts = 0
        if df_snapshot is not None:
            feats = _features_from_df(df_snapshot)
            if feats:
                mem_ts = ts
                # append to MEMORY_CSV with blank outcome/label
                with open(MEMORY_CSV, "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        symbol, tf, mem_ts, float(entry),
                        feats.get("ret1",0.0), feats.get("ret3",0.0), feats.get("ret5",0.0),
                        feats.get("atr",0.0), feats.get("rsi",50.0), feats.get("bb_bw",0.0),
                        feats.get("ema_slope",0.0),
                        0.0, "", json.dumps(meta or {})
                    ])
        base["mem_ts"] = mem_ts

        # persist open event
        day = _day_key(ts)
        _append_ndjson(day, base)
        self._open[tid] = base
        return tid

    # ---------- exit ----------
    def mark_exit(self, trade_id: str, exit_price: float, reason: str) -> Dict[str, Any]:
        if trade_id not in self._open:
            return {"ok": False, "error": "unknown_trade_id"}

        o = self._open.pop(trade_id)
        ts_close = _utc_ts()
        hold = max(0, ts_close - int(o["ts"]))
        side = o["side"].lower()
        entry = float(o["entry"])
        sl    = float(o.get("sl", 0.0) or 0.0)
        qty   = float(o.get("qty", 0.0) or 0.0)

        # PnL absolute in quote currency (or account currency on MT5 if you pass that)
        pnl = (exit_price - entry) * qty if side == "buy" else (entry - exit_price) * qty

        # R-multiple (risk = |entry - sl|). If no SL, fall back to price percent.
        risk = abs(entry - sl) if sl > 0 else max(1e-9, entry * 0.002)  # 0.2% fallback
        pnl_r = ((exit_price - entry) / risk) if side == "buy" else ((entry - exit_price) / risk)

        # TP flags
        tp1_hit = (exit_price >= float(o["tp1"])) if (o.get("tp1") and o["tp1"]>0) else False
        tp2_hit = (exit_price >= float(o["tp2"])) if (o.get("tp2") and o["tp2"]>0) else False
        tp3_hit = (exit_price >= float(o["tp3"])) if (o.get("tp3") and o["tp3"]>0) else False
        win     = 1 if pnl > 0 else 0

        # NDJSON close event
        close_evt = {
            "t":"close","ts":ts_close,"iso":_now_iso(),"id":trade_id,
            "exit_price": float(exit_price), "exit_reason": reason,
            "pnl": float(pnl), "pnl_r": float(pnl_r),
            "hold_sec": hold, "hit_tp1": tp1_hit, "hit_tp2": tp2_hit, "hit_tp3": tp3_hit, "win": win
        }
        day = _day_key(ts_close)
        _append_ndjson(day, {**o, **close_evt})

        # Append to CSV ledger
        _ensure_ledgers()
        with open(LEDGER_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                trade_id, int(o["ts"]), ts_close, o["market"], o["venue"], o["symbol"], o["tf"], o["side"],
                float(o["entry"]), float(o["sl"]), float(o["tp1"]), float(o["tp2"]), float(o["tp3"]),
                float(o["qty"]), float(exit_price), reason, hold, float(pnl), float(pnl_r),
                int(tp1_hit), int(tp2_hit), int(tp3_hit), int(win), int(o.get("mem_ts",0))
            ])

        # Fill outcome/label back to pattern_memory if we recorded a snapshot
        if int(o.get("mem_ts", 0)) > 0:
            self._update_memory_outcome(
                symbol=o["symbol"], tf=o["tf"], ts=int(o["mem_ts"]),
                outcome=float(pnl_r), label=("win" if win == 1 else "loss")
            )

        return {"ok": True, "id": trade_id, "pnl": float(pnl), "pnl_r": float(pnl_r), "win": bool(win)}

    # ---------- memory updater ----------
    def _update_memory_outcome(self, symbol: str, tf: str, ts: int, outcome: float, label: str) -> None:
        try:
            # load all, update the matching row, rewrite
            rows: List[List[str]] = []
            hit = False
            with open(MEMORY_CSV, "r", encoding="utf-8") as f:
                rdr = csv.reader(f)
                header = next(rdr)
                for r in rdr:
                    rows.append(r)
            # column indices by header
            cols = {name: i for i, name in enumerate(header)}
            for r in rows:
                if len(r) < len(header):  # skip malformed
                    continue
                if r[cols["symbol"]] == symbol and r[cols["tf"]] == tf and int(r[cols["ts"]]) == ts:
                    r[cols["outcome"]] = f"{outcome:.6f}"
                    r[cols["label"]]   = label
                    hit = True
                    break
            if hit:
                with open(MEMORY_CSV, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(header)
                    w.writerows(rows)
        except Exception:
            # non-fatal
            pass

    # ---------- daily pnl summary ----------
    def daily_pnl_report(self, day: Optional[str] = None) -> str:
        """
        Returns a compact daily report string (sum pnl, R, wins/losses, avg hold).
        """
        day = day or _day_key()
        ndjson_path = TRADES_ROLL / f"trades-{day}.ndjson"
        n = 0; wins = 0; pnl_sum = 0.0; r_sum = 0.0; hold_sum = 0
        if ndjson_path.exists():
            with open(ndjson_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    ev = json.loads(line)
                    if ev.get("t") != "close": continue
                    n += 1
                    wins += 1 if ev.get("win") else 0
                    pnl_sum += float(ev.get("pnl", 0.0))
                    r_sum   += float(ev.get("pnl_r", 0.0))
                    hold_sum+= int(ev.get("hold_sec", 0))
        wl = f"{wins}/{n-wins}" if n > 0 else "0/0"
        avg_r = (r_sum / n) if n>0 else 0.0
        avg_hold = (hold_sum / n) if n>0 else 0
        return f"Day {day}: trades={n}, W/L={wl}, ΣPnL={pnl_sum:.2f}, avgR={avg_r:.2f}, avgHold={avg_hold//60}m"

# convenience singleton (optional)
LOGGER = OutcomeLogger()
