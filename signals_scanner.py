# signals_scanner.py
from __future__ import annotations

import os, time, argparse, concurrent.futures as cf
from typing import List, Dict, Any, Optional

from router import ExchangeRouter
from signals_publisher import publish_batch
from signals_hub import analyze_symbol_ccxt, analyze_symbol_mt5, mtf_confirm
from mt5_adapter import mt5_init, bars_df as mt5_bars
from news_adapter import fx_guard_for_symbol, fetch_crypto_sentiment  # NEW

def env_bool(k: str, d: bool) -> bool:
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","y","on")

def env_list(k: str, d: List[str]) -> List[str]:
    raw = os.getenv(k, "")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else d

TF_MAP_CCXT = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","1h":"1h"}
TF_MAP_MT5  = {"1m":"M1","5m":"M5","15m":"M15","1h":"H1"}

# ----- discovery -----
def _discover_spot(r: ExchangeRouter, quote="USDT") -> List[str]:
    try:
        return r.spot_symbols(quote) or ["BTC/USDT","ETH/USDT","XRP/USDT","SOL/USDT","DOGE/USDT"]
    except Exception:
        return ["BTC/USDT","ETH/USDT","XRP/USDT","SOL/USDT","DOGE/USDT"]

def _discover_linear(r: ExchangeRouter, quote="USDT") -> List[str]:
    try:
        return r.linear_symbols(quote) or ["BTC/USDT","ETH/USDT"]
    except Exception:
        return ["BTC/USDT","ETH/USDT"]

# ----- guards -----
def _ok_liquidity(t: Dict[str,Any], min_qv: float) -> bool:
    try: return float(t.get("quoteVolume", 0.0)) >= float(min_qv)
    except: return True

def _ok_spread_atr(t: Dict[str,Any], bars: List[List[float]], max_spread_bp: float, min_atr_bp: float) -> bool:
    try:
        bid = float(t.get("bid") or 0.0); ask = float(t.get("ask") or 0.0)
        last = float(t.get("last") or t.get("close") or 0.0)
        mid = (bid+ask)/2.0 if (bid and ask) else last
        if mid <= 0: return False
        spread_bp = ((ask-bid)/mid*1e4) if (bid and ask) else 0.0
        if spread_bp > float(max_spread_bp): return False
        n = min(20, len(bars))
        if n < 5: return False
        closes = [float(b[4]) for b in bars[-n:]]
        highs  = [float(b[2]) for b in bars[-n:]]
        lows   = [float(b[3]) for b in bars[-n:]]
        trs=[]; prev=closes[0]
        for h,l,c in zip(highs,lows,closes):
            trs.append(max(h-l, abs(h-prev), abs(l-prev))); prev=c
        atr_bp = (sum(trs)/len(trs))/mid*1e4
        return atr_bp >= float(min_atr_bp)
    except Exception:
        return False

# ----- workers -----
def _scan_ccxt(r: ExchangeRouter, sym: str, tf: str, limit: int, min_qv: float, max_spread_bp: float, min_atr_bp: float, kind: str) -> Optional[Dict[str,Any]]:
    try:
        bars = r.safe_fetch_ohlcv(sym, TF_MAP_CCXT.get(tf, "5m"), limit=limit)
        if not bars:
            return None
        t = r.safe_fetch_ticker(sym)
        if not _ok_liquidity(t, min_qv):
            return None
        if not _ok_spread_atr(t, bars, max_spread_bp, min_atr_bp):
            return None
        return analyze_symbol_ccxt(bars, tf, sym, market="linear" if kind == "linear" else "spot")
    except Exception:
        return None

def _scan_fx(sym: str, tf: str, limit: int) -> Optional[Dict[str,Any]]:
    try:
        bars = mt5_bars(sym, TF_MAP_MT5.get(tf,"M5"), limit=limit)
        if not bars: return None
        return analyze_symbol_mt5(bars, tf, sym)
    except Exception:
        return None

# ----- main one cycle -----
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
            'symbol': plan.get('market') or plan.get('symbol'),
            'side': plan.get('action') or plan.get('side'),
            'confidence': plan.get('size', plan.get('confidence', 1.0)),
            'tf': args.tf,
            'market': 'crypto',
            'context': plan.get('context', [f"UltraCore god mode"]) or [f"UltraCore god mode"]
        }
        out.append(sig)

    out.sort(key=lambda s: float(s.get('confidence', 0.0)), reverse=True)

    # Optional: when publishing, send Telegram messages with small chart images
    try:
        do_publish = bool(getattr(args, 'publish', False)) or os.getenv('TELEGRAM_ENABLED','false').lower()=='true'
        if do_publish:
            from notifier import TelegramNotifier
            import charting
            tg = TelegramNotifier()
            # Only proceed if notifier is enabled; otherwise skip heavy work
            if tg.enabled:
                for sig, plan in zip(out[: args.top], plans[: args.top]):
                    try:
                        sym = sig.get('symbol')
                        side = sig.get('side') or 'buy'
                        # fetch recent bars for chart
                        tf_map = TF_MAP_CCXT.get(args.tf, '5m')
                        bars = []
                        try:
                            bars = r.safe_fetch_ohlcv(sym, tf_map, limit=args.limit)
                        except Exception:
                            bars = []

                        # entry / qty / sl / tp best-effort
                        entry = float(plan.get('entry') or (bars[-1][4] if bars else 0.0))
                        qty = float(plan.get('qty') or plan.get('size') or 0)
                        sl = plan.get('sl')
                        tp = plan.get('tp1') or plan.get('tp') or None
                        reasons = plan.get('context') or []
                        quality = float(plan.get('confidence') or plan.get('quality') or 0.0)

                        # build a marker at the latest bar
                        entries = []
                        if bars:
                            try:
                                entries = [{'ts': bars[-1][0], 'price': float(bars[-1][4]), 'side': side}]
                            except Exception:
                                entries = []

                        chart_path = None
                        try:
                            chart_path = charting.plot_signal_chart(sym, bars, entries=entries, tps=([tp] if tp else None), sl=sl)
                        except Exception:
                            chart_path = None

                        # send textual signal
                        try:
                            tg.signal(sym, side, entry, qty, float(sl) if sl else 0.0, reasons=reasons, quality=quality, take_profit=tp)
                        except Exception:
                            pass

                        # attach chart image if available
                        if chart_path:
                            try:
                                tg.send_photo(chart_path, caption=f"{sym} {side.upper()} chart (tf={args.tf})")
                            except Exception:
                                pass
                    except Exception:
                        continue
    except Exception:
        pass

    return out[:args.top]


# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description="News-aware multi-market scanner (spot + futures + FX)")
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
                print(f"[{s.get('market','?').upper()}] {s['symbol']} {s['side']} tf={s['tf']} q={q:.2f} :: {', '.join(s.get('context',[])[:2])}")
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
