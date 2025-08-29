# brain_loop.py
# Orchestrates: scan → enrich/score → plan(size/targets) → (optional trade) → publish → remember

from __future__ import annotations

import os, time, random, traceback
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime

# ---- dependencies in your repo ----
import signals_scanner as scanner
from signals_publisher import publish_batch
from pattern_memory import features, record, set_outcome, recall, recompute_scores, get_score, FEATS

# session-weighted sizing/targets (+ optional OCO helpers)
try:
    from risk_engine import equity_from_router  # if you have it
except Exception:
    equity_from_router = None

try:
    from trade_planner import attach_plan, place_oco_ccxt_safe
except Exception:
    def attach_plan(sig: Dict[str,Any], equity: float) -> Dict[str,Any]: return sig
    def place_oco_ccxt_safe(*a, **k): pass

# Router for CCXT autotrade
try:
    from router import ExchangeRouter
except Exception:
    ExchangeRouter = None  # graceful offline

# ---- Telegram (optional) ----
try:
    from tg_utils import send_text  # def send_text(msg:str)->bool
except Exception:
    def send_text(_: str) -> None:  # no-op if unavailable
        pass

# =================== ENV HELPERS ===================
def env_b(k: str, d: bool) -> bool:
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","y","on")

def env_f(k: str, d: float) -> float:
    try: return float(os.getenv(k, str(d)))
    except: return d

def env_i(k: str, d: int) -> int:
    try: return int(float(os.getenv(k, str(d))))
    except: return d

# =================== CONFIG ===================
THINK_TOP          = env_i("THINK_TOP", env_i("TOP_N", 7))
THINK_MIN_CONF     = env_f("THINK_MIN_CONF", 0.20)
THINK_EPSILON      = env_f("THINK_EPSILON", 0.10)   # exploration prob
THINK_COOLDOWN_SEC = env_i("THINK_SYMBOL_COOLDOWN", 180)
THINK_REPEAT       = env_i("THINK_REPEAT", 60)

AUTO_TRADE         = env_b("LIVE_AUTOTRADE", False) # if True, place OCO on CCXT
AUTO_TRADE_MIN_QTY = env_f("AUTOTRADE_MIN_QTY", 0.0)

# =================== SCAN ARGS SHIM ===================
@dataclass
class ScanArgs:
    tf: str = os.getenv("SCAN_TF", "5m")
    top: int = THINK_TOP
    limit: int = env_i("SCAN_LIMIT", 200)
    repeat: int = 0
    publish: bool = False  # scanner never publishes

# =================== ENRICHMENT ===================
def _attach_feats(sig: Dict[str, Any]) -> None:
    if isinstance(sig.get("feats"), dict):
        return
    df = sig.get("df") or sig.get("df_now")
    if df is not None:
        try:
            sig["feats"] = {k: float(features(df).get(k, 0.0)) for k in FEATS}
        except Exception:
            pass

def _blend_confidence(sig: Dict[str, Any]) -> float:
    base = float(sig.get("confidence", sig.get("quality", 0.0)) or 0.0)
    prior = get_score(sig)  # {'winrate','avg_r','n'}
    pw = 0.4 if prior.get("n", 0) < 50 else 0.6
    prior_conf = 2.0 * (float(prior.get("winrate", 0.5)) - 0.5)
    try:
        ctx = recall(sig["symbol"], sig["tf"], sig.get("df") or sig.get("df_now"), k=200)
        prior_conf = max(prior_conf, 2.0 * (ctx.get("winrate", 50.0)/100.0 - 0.5))
        if ctx.get("note"): sig.setdefault("context", []).append(ctx["note"])
    except Exception:
        pass
    blended = max(0.0, min(1.0, (1.0 - pw) * base + pw * prior_conf))
    sig["confidence"] = blended
    sig.setdefault("quality", blended)
    return blended

# =================== NORMALIZE FOR PUBLISHER ===================
def _normalize_for_publisher(sig: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(sig)
    out["market"] = out.get("market") or ("fx" if out.get("symbol","").isalpha() else "crypto")
    out["tf"]     = out.get("tf") or os.getenv("SCAN_TF", "5m")
    side = out.get("side") or ("buy" if out.get("direction","long") in ("long","buy") else "sell")
    out["side"] = side

    px = float(out.get("entry") or out.get("price") or 0.0)
    sl = float(out.get("sl")    or out.get("stop")  or 0.0)
    out["entry"], out["sl"] = px, sl

    if not all(k in out for k in ("tp1","tp2","tp3")):
        R = abs(px - sl) if (px and sl) else max(0.001, abs(px) * 0.003)
        if side == "buy":
            out["tp1"], out["tp2"], out["tp3"] = px + 1.0*R, px + 2.0*R, px + 3.0*R
        else:
            out["tp1"], out["tp2"], out["tp3"] = px - 1.0*R, px - 2.0*R, px - 3.0*R

    out["confidence"] = float(out.get("confidence", out.get("quality", 0.0)) or 0.0)
    for k in ("entry","sl","tp1","tp2","tp3","confidence"):
        try: out[k] = float(out[k])
        except: out[k] = 0.0
    return out

# =================== COOLDOWN ===================
_last_symbol_ts: Dict[str, float] = {}

def _cooldown_ok(symbol: str, now: float, cd_sec: int) -> bool:
    t = _last_symbol_ts.get(symbol)
    if t is None or now - t >= cd_sec:
        _last_symbol_ts[symbol] = now
        return True
    return False

# =================== AUTOTRADE (CCXT) ===================
_ccxt_router: Optional[ExchangeRouter] = None
def _router() -> Optional[ExchangeRouter]:
    global _ccxt_router
    if _ccxt_router is None and ExchangeRouter is not None:
        try: _ccxt_router = ExchangeRouter()
        except Exception: _ccxt_router = None
    return _ccxt_router

def _equity_now_fallback(router: Optional[ExchangeRouter]) -> float:
    """Use risk_engine.equity_from_router if available, else do a cheap parse."""
    if equity_from_router and router:
        try:
            return float(equity_from_router(router))
        except Exception:
            pass
    try:
        bal = (router.account().get("balance", {}) if router else {}) or {}
        total = float(bal.get("total", {}).get("USDT", 0) or bal.get("total", 0) or 5000)
        if total <= 0 and "free" in bal:
            total = float(bal["free"].get("USDT", 0) or 5000)
        return total if total > 0 else 5000.0
    except Exception:
        return 5000.0

def _maybe_autotrade(picks: List[Dict[str,Any]]) -> None:
    if not AUTO_TRADE:
        return
    r = _router()
    if r is None:
        return
    ex = r.ex
    for s in picks:
        try:
            if str(s.get("market","")).lower().startswith("crypto") and float(s.get("qty",0)) > max(0.0, AUTO_TRADE_MIN_QTY):
                place_oco_ccxt_safe(
                    ex,
                    s["symbol"],
                    s["side"],
                    float(s["qty"]),
                    float(s["entry"]),
                    float(s["sl"]),
                    float(s["tp1"]),
                    leverage=s.get("leverage")
                )
        except Exception as e:
            send_text(f"⚠️ Autotrade error {s.get('symbol')}: {e}")

# =================== ONE THINK CYCLE ===================
def think_once() -> List[Dict[str, Any]]:
    raw = scanner.run_once(ScanArgs())
    if not raw:
        return []

    now = time.time()
    enriched: List[Dict[str, Any]] = []

    for s in raw:
        try:
            _attach_feats(s)
            c = _blend_confidence(s)
            if c >= THINK_MIN_CONF and _cooldown_ok(s["symbol"], now, THINK_COOLDOWN_SEC):
                enriched.append(s)
        except Exception:
            continue
    if not enriched:
        return []

    enriched.sort(key=lambda z: float(z.get("confidence", z.get("quality", 0.0))), reverse=True)
    picks: List[Dict[str, Any]] = []
    for s in enriched:
        if len(picks) >= THINK_TOP:
            break
        picks.append(s if random.random() >= THINK_EPSILON else s)  # hook for diversification

    # normalize -> plan (sizing/targets)
    router = _router()
    eq = _equity_now_fallback(router)
    planned = [attach_plan(_normalize_for_publisher(s), eq) for s in picks]

    # memory snapshot (if df present)
    for s in planned:
        try:
            df = s.get("df")
            if df is not None:
                record(s["symbol"], s.get("tf") or os.getenv("SCAN_TF","5m"), df, float(s["entry"]), meta={
                    "side": s["side"], "market": s.get("market","?"), "conf": float(s.get("confidence",0.0))
                })
        except Exception:
            pass

    # optional live autotrade (CCXT, with OCO)
    _maybe_autotrade(planned)

    # publish (Telegram/webhook/queue handled by publisher)
    publish_batch(planned)
    return planned

# =================== LEARNING (CLOSED TRADES) ===================
def learn_from_closed_trades(trades: Optional[List[Dict[str, Any]]] = None) -> None:
    if not trades:
        return
    upd = False
    for t in trades:
        try:
            ok = set_outcome(str(t["symbol"]), str(t["tf"]), int(t["entry_ts"]),
                             float(t.get("outcome", 0.0)), str(t.get("label", "")))
            upd = upd or ok
        except Exception:
            continue
    if upd:
        try: recompute_scores()
        except Exception: pass

# =================== HEARTBEAT ===================
def heartbeat(published: List[Dict[str, Any]]) -> None:
    if not env_b("TELEGRAM_ENABLED", True):
        return
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")
    lines = [
        f"🧠 Heartbeat {ts}",
        f"picked={len(published)}  repeat={THINK_REPEAT}s  eps={THINK_EPSILON:.2f}  minConf={THINK_MIN_CONF:.2f}",
    ]
    for s in published[:10]:
        q = float(s.get("confidence", s.get("quality", 0.0)))
        lines.append(f"• {s.get('market','?').upper()} {s['symbol']} {s['side']} tf={s['tf']} q={q:.2f} qty={s.get('qty','-')}")
    try:
        send_text("\n".join(lines))
    except Exception:
        pass

# =================== LOOP ===================
def main() -> None:
    if THINK_REPEAT <= 0:
        try:
            picks = think_once()
            heartbeat(picks)
        except Exception:
            traceback.print_exc()
        return

    while True:
        try:
            picks = think_once()
            heartbeat(picks)
        except Exception:
            traceback.print_exc()
        time.sleep(THINK_REPEAT)

if __name__ == "__main__":
    main()
