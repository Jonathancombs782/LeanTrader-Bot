from __future__ import annotations

import os, json, time, argparse, concurrent.futures as cf
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from router import ExchangeRouter
from signals_publisher import publish_batch
from signals_hub import analyze_symbol_ccxt, analyze_symbol_mt5, mtf_confirm
from mt5_adapter import mt5_init, bars_df as mt5_bars

# ---------- env helpers ----------
def env_bool(k: str, d: bool) -> bool:
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","y","on")

def env_list(k: str, d: List[str]) -> List[str]:
    raw = os.getenv(k, "")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else d

TF_MAP_CCXT = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","1h":"1h"}
TF_MAP_MT5  = {"1m":"M1","5m":"M5","15m":"M15","1h":"H1"}

AUDIT_DIR = Path("runtime"); AUDIT_DIR.mkdir(parents=True, exist_ok=True)
KEPT_PATH = AUDIT_DIR / "scan_kept.ndjson"
REJ_PATH  = AUDIT_DIR / "scan_rejected.ndjson"

def _append(path: Path, row: Dict[str,Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

# ---------- discovery ----------
def discover_spot_symbols(r: ExchangeRouter, quote="USDT") -> List[str]:
    try:
        mkts = r.markets or {}
        return sorted([s for s, m in mkts.items() if isinstance(s, str) and s.endswith(f"/{quote}") and (isinstance(m, dict) and m.get("spot"))])
    except Exception:
        return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]

def discover_linear_symbols(r: ExchangeRouter, quote="USDT") -> List[str]:
    try:
        mkts = r.markets or r.ex.load_markets()
        out=[]
        for s,m in mkts.items():
            if not s.endswith(f"/{quote}"): continue
            if m.get("linear") or (m.get("swap") and m.get("contract") and m.get("quote")==quote):
                out.append(s)
        return sorted(out) or ["BTC/USDT","ETH/USDT"]
    except Exception:
        return ["BTC/USDT","ETH/USDT"]

# ---------- guard checks ----------
def check_liq(t: dict, min_qv: float) -> Tuple[bool,str]:
    try:
        qv = float(t.get("quoteVolume", 0.0) or 0.0)
        return (qv >= min_qv, f"liquidity {qv:.0f} < {min_qv:.0f}")
    except Exception:
        return (True, "")

def check_spread(t: dict, max_bp: float) -> Tuple[bool,str]:
    try:
        bid = float(t.get("bid") or 0); ask = float(t.get("ask") or 0)
        mid = (bid+ask)/2 if bid and ask else float(t.get("last") or t.get("close") or 0)
        if mid <= 0: return (False, "mid<=0")
        bp = (ask-bid)/mid*1e4 if bid and ask else 0.0
        return (bp <= max_bp, f"spread {bp:.1f}bp > {max_bp:.1f}bp")
    except Exception:
        return (True,"")

def quick_atr_bp(bars: List[List[float]]) -> float:
    n = min(20, len(bars))
    if n < 5: return 0.0
    highs=[b[2] for b in bars[-n:]]; lows=[b[3] for b in bars[-n:]]; closes=[b[4] for b in bars[-n:]]
    prev = closes[0]; trs=[]
    for h,l,c in zip(highs,lows,closes):
        trs.append(max(h-l, abs(h-prev), abs(l-prev))); prev=c
    mid = (max(closes[-5:]) + min(closes[-5:]))/2 or 1.0
    return (sum(trs)/len(trs))/mid*1e4

def check_atr(bars: List[List[float]], min_bp: float) -> Tuple[bool,str]:
    try:
        a = quick_atr_bp(bars)
        return (a >= min_bp, f"ATR {a:.1f}bp < {min_bp:.1f}bp")
    except Exception:
        return (True,"")

# ---------- workers ----------
def scan_ccxt_symbol(r: ExchangeRouter, sym: str, tf: str, limit: int,
                     min_qv_usd: float, max_spread_bp: float, min_atr_bp: float,
                     market_kind: str) -> Optional[Dict[str,Any]]:
    meta = {"market": f"crypto-{market_kind}", "symbol": sym, "tf": tf}
    try:
        bars = r.safe_fetch_ohlcv(sym, TF_MAP_CCXT.get(tf, "5m"), limit=limit) or []
        ticker = r.safe_fetch_ticker(sym) or {}

        ok, why = check_liq(ticker, min_qv_usd)
        if not ok:
            _append(REJ_PATH, dict(meta, reason=why))
            return None

        ok, why = check_spread(ticker, max_spread_bp)
        if not ok:
            _append(REJ_PATH, dict(meta, reason=why))
            return None

        ok, why = check_atr(bars, min_atr_bp)
        if not ok:
            _append(REJ_PATH, dict(meta, reason=why))
            return None

        sig = analyze_symbol_ccxt(bars, tf, sym, market=("linear" if market_kind == "linear" else "spot"))
        if not sig:
            _append(REJ_PATH, dict(meta, reason="strategy_none"))
            return None

        try:
            ok, ctx = mtf_confirm(sig)
            if not ok: _append(REJ_PATH, dict(meta, reason="mtf_reject", ctx=ctx)); return None
            if ctx: sig.setdefault("context", []).extend(ctx)
        except Exception:
            pass

        _append(KEPT_PATH, dict(meta, confidence=float(sig.get("confidence", sig.get("quality",0))), ctx=sig.get("context", [])))
        return sig
    except Exception as e:
        _append(REJ_PATH, dict(meta, reason=f"error:{str(e)[:140]}"))
        return None

def scan_fx_symbol(sym: str, tf: str, limit: int) -> Optional[Dict[str,Any]]:
    meta = {"market":"fx", "symbol":sym, "tf":tf}
    try:
        bars = mt5_bars(sym, TF_MAP_MT5.get(tf,"M5"), limit=limit) or []
        if not bars: _append(REJ_PATH, dict(meta, reason="no_bars")); return None
        sig = analyze_symbol_mt5(bars, tf, sym)
        if not sig: _append(REJ_PATH, dict(meta, reason="strategy_none")); return None
        try:
            ok, ctx = mtf_confirm(sig)
            if not ok: _append(REJ_PATH, dict(meta, reason="mtf_reject", ctx=ctx)); return None
            if ctx: sig.setdefault("context", []).extend(ctx)
        except Exception:
            pass
        _append(KEPT_PATH, dict(meta, confidence=float(sig.get("confidence", sig.get("quality",0))), ctx=sig.get("context", [])))
        return sig
    except Exception as e:
        _append(REJ_PATH, dict(meta, reason=f"error:{str(e)[:140]}")); return None

# ---------- one cycle ----------
def run_once(args) -> List[Dict[str,Any]]:
    # --- UltraCore god mode integration ---
    from ultra_core import UltraCore
    from universe import Universe
    r = ExchangeRouter()
    ultra_universe = Universe(r) if hasattr(r, 'markets') else None
    ultra = UltraCore(r, ultra_universe)

    # Scan markets and reason about signals
    scan_results = ultra.scan_markets()
    opportunities = ultra.scout_opportunities(scan_results)
    plans = ultra.plan_trades(opportunities)
    ultra.learn()
    ultra.sharpen()

    # Convert plans to signals format for compatibility
    out = []
    for plan in plans:
        sig = {
            'symbol': plan['market'],
            'side': plan['action'],
            'confidence': plan.get('size', 1.0),
            'tf': args.tf,
            'market': 'crypto',
            'context': [f"UltraCore god mode"]
        }
        out.append(sig)

    out.sort(key=lambda s: float(s.get('confidence', 0.0)), reverse=True)
    return out[:args.top]

# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description="Ultra multi-market scanner (debug)")
    p.add_argument("--tf", default=os.getenv("SCAN_TF","5m"), choices=["1m","3m","5m","15m","1h"])
    p.add_argument("--top", type=int, default=int(os.getenv("TOP_N","7")))
    p.add_argument("--limit", type=int, default=int(os.getenv("SCAN_LIMIT","200")))
    p.add_argument("--repeat", type=int, default=int(os.getenv("SCAN_REPEAT","0")))
    p.add_argument("--publish", action="store_true")
    args = p.parse_args()

    if env_bool("FX_ENABLE", True):
        try: mt5_init()
        except Exception as e: print("MT5 init warning:", e)

    def cycle():
        sigs = run_once(args)
        if not sigs:
            print("No signals.")
        else:
            for s in sigs:
                q = float(s.get("confidence", s.get("quality", 0.0)))
                print(f"[{s.get('market','?')}] {s['symbol']} {s['side']} tf={s['tf']} q={q:.2f}")
            if args.publish:
                publish_batch(sigs)

    if args.repeat > 0:
        while True:
            try: cycle()
            except Exception as e: print("scan error:", e)
            time.sleep(args.repeat)
    else:
        cycle()

if __name__ == "__main__":
    main()
