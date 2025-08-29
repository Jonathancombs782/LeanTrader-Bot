# tg_heartbeat.py
from __future__ import annotations
import os, time, json, argparse, pathlib, datetime as dt
from typing import List, Dict, Any
from dotenv import load_dotenv

from router import ExchangeRouter
from notifier import TelegramNotifier

RUNTIME = pathlib.Path("runtime"); RUNTIME.mkdir(exist_ok=True)
OPEN_TRADES = RUNTIME / "open_trades.json"

def _read_json(p: pathlib.Path, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return default

def _fmt_usd(x: float) -> str:
    s="-" if x<0 else ""; v=abs(x)
    if v>=1_000_000: return f"{s}${v/1_000_000:,.2f}M"
    if v>=1_000:     return f"{s}${v:,.0f}"
    return f"{s}${v:,.2f}"

def _equity(router: ExchangeRouter) -> float:
    acc = router.account()
    if "paper_cash" in acc: return float(acc["paper_cash"])
    bal = (acc.get("balance") or {}).get("total", {}) or {}
    eq = 0.0
    for k,v in bal.items():
        if k.upper() in ("USD","USDT","USDC"):
            eq += float(v or 0)
    return eq

def _open_pnl(router: ExchangeRouter, rows: List[Dict[str,Any]]) -> float:
    pnl = 0.0
    for t in rows:
        try:
            # Prefer safe wrapper if available
            # prefer safe wrapper, robustly guarded
            try:
                if hasattr(router, 'safe_fetch_ticker'):
                    tk = router.safe_fetch_ticker(t["symbol"])
                else:
                    try:
                        tk = router.ex.fetch_ticker(t["symbol"]) if hasattr(router, 'ex') else {}
                    except Exception as e:
                        print(f"[tg_heartbeat] fetch_ticker fallback failed for {t['symbol']}: {e}")
                        tk = {}
            except Exception as e:
                print(f"[tg_heartbeat] safe_fetch_ticker outer failed for {t['symbol']}: {e}")
                tk = {}
            last = float((tk.get("last") if isinstance(tk, dict) else None) or (tk.get("close") if isinstance(tk, dict) else None) or 0)
            side = 1 if t["side"] == "buy" else -1
            pnl += (last - float(t["entry"])) * side * (float(t["amount"]) if t.get("mode") == "spot" else 1.0)
        except Exception:
            continue
    return pnl

def heartbeat_once(router: ExchangeRouter, notif: TelegramNotifier):
    rows = _read_json(OPEN_TRADES, [])
    eq   = _equity(router)
    upnl = _open_pnl(router, rows)
    lines = [
        f"*Heartbeat* {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%MZ')}",
        f"Mode: `{os.getenv('EXCHANGE_MODE','spot')}`  Live: `{os.getenv('ENABLE_LIVE','false')}`  Paper: `{str(router.paper)}`",
        f"Equity: {_fmt_usd(eq)}   uPnL: {_fmt_usd(upnl)}",
        f"Open: {len(rows)}",
    ]
    if rows:
        for t in rows[:6]:
            lines.append(f"• `{t['symbol']}` {t['side']} qty={t['amount']} @ {t['entry']:.6f}")
        if len(rows)>6: lines.append(f"… and {len(rows)-6} more")
    notif.note("\n".join(lines))

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=30, help="minutes between heartbeats")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    router = ExchangeRouter()
    notif  = TelegramNotifier()
    if args.once:
        heartbeat_once(router, notif)
        return
    while True:
        try:
            heartbeat_once(router, notif)
        except Exception as e:
            print("[heartbeat error]", e)
        time.sleep(max(1, args.interval)*60)

if __name__ == "__main__":
    main()
