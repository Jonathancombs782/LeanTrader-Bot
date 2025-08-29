# signals_publisher.py
"""
Advanced signal publisher
- Validate & normalize
- Idempotent de-dupe (time window)
- Token-bucket rate limiting
- NDJSON queue (daily roll)
- Optional HTTPS webhook (HMAC-SHA256)
- Telegram push via tg_utils.send_signal(title, lines)

ENV (defaults):
  SIGNALS_QUEUE_DIR=runtime
  SIGNALS_QUEUE_PREFIX=signals
  SIGNALS_ROLL_DAILY=true
  SIGNALS_DEDUPE_WINDOW_SEC=300
  SIGNALS_RATE_PER_MIN=60
  SIGNALS_MIN_CONF=0.0
  SIGNALS_WEBHOOK_URL=
  SIGNALS_WEBHOOK_SECRET=
"""

from __future__ import annotations

import os, json, time, hmac, hashlib, threading
from typing import Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path

# requests is optional; we import lazily where used
import requests  # make sure it's installed in your venv

# ---- optional memory hooks (safe if absent) ----
try:
    from pattern_memory import record as pm_record  # (symbol, tf, df_on_entry, entry_price, meta)
except Exception:
    pm_record = None

try:
    # if you maintain outcomes elsewhere you can import your writer here
    from pattern_memory import set_outcome as pm_set_outcome  # (symbol, tf, entry_ts, outcome, label)
except Exception:
    pm_set_outcome = None

# ---- Telegram helper (safe no-op if disabled) ----
try:
    from tg_utils import send_signal as tg_send  # expects (title: str, lines: list[str])
except Exception:
    def tg_send(_: str, __: List[str]) -> bool:
        return False

# ------------ config ------------
Q_DIR: Path = Path(os.getenv("SIGNALS_QUEUE_DIR", "runtime"))
Q_PREF: str = os.getenv("SIGNALS_QUEUE_PREFIX", "signals")
ROLL: bool = os.getenv("SIGNALS_ROLL_DAILY", "true").lower() == "true"
DEDUP_S: int = int(os.getenv("SIGNALS_DEDUPE_WINDOW_SEC", "300"))
RATE_PM: int = int(os.getenv("SIGNALS_RATE_PER_MIN", "60"))
MINCONF: float = float(os.getenv("SIGNALS_MIN_CONF", "0.0"))

WEBHOOK_URL = os.getenv("SIGNALS_WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = os.getenv("SIGNALS_WEBHOOK_SECRET", "").strip()

SEEN_PATH = Q_DIR / "signals_seen.json"
Q_DIR.mkdir(parents=True, exist_ok=True)

# ------------ token bucket ------------
class _Bucket:
    def __init__(self, per_min: int):
        self.capacity = max(1, int(per_min))
        self.tokens = float(self.capacity)
        self.rate = self.capacity / 60.0  # tokens per second
        self.last = time.time()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            now = time.time()
            dt = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + dt * self.rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

_BUCKET = _Bucket(RATE_PM)

# ------------ de-dupe store ------------
def _load_seen() -> Dict[str, float]:
    try:
        if SEEN_PATH.exists():
            with open(SEEN_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_seen(seen: Dict[str, float]) -> None:
    try:
        cutoff = time.time() - DEDUP_S
        slim = {k: v for k, v in seen.items() if v >= cutoff}
        with open(SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(slim, f)
    except Exception:
        pass

# ------------ helpers ------------
def _fingerprint(sig: Dict[str, Any]) -> str:
    core = {
        "market": sig.get("market"),
        "symbol": sig.get("symbol"),
        "tf":     sig.get("tf"),
        "side":   sig.get("side"),
        "entry":  round(float(sig.get("entry", 0.0)), 6),
        "tp1":    round(float(sig.get("tp1",   0.0)), 6),
        "tp2":    round(float(sig.get("tp2",   0.0)), 6),
        "tp3":    round(float(sig.get("tp3",   0.0)), 6),
        "sl":     round(float(sig.get("sl",    0.0)), 6),
    }
    s = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _validate_and_normalize(sig: Dict[str, Any]) -> Dict[str, Any]:
    req = ["market","symbol","tf","side","entry","tp1","tp2","tp3","sl","confidence"]
    miss = [k for k in req if k not in sig]
    if miss:
        raise ValueError(f"missing keys: {miss}")
    out = dict(sig)
    out["market"] = str(out["market"]).lower()
    out["symbol"] = str(out["symbol"]).upper()
    out["tf"]     = str(out["tf"]).lower()
    out["side"]   = str(out["side"]).lower()
    for k in ["entry","tp1","tp2","tp3","sl","confidence"]:
        out[k] = float(out[k])
    if not (0.0 <= out["confidence"] <= 1.0):
        raise ValueError("confidence must be within [0,1]")
    # optional
    if "qty" in out: out["qty"] = float(out["qty"])
    if "context" not in out: out["context"] = []
    # passthrough extras: news bullets, reasons, df snapshot pointer, etc.
    return out

def _queue_path() -> Path:
    if ROLL:
        day = datetime.utcnow().strftime("%Y%m%d")
        return Q_DIR / f"{Q_PREF}-{day}.ndjson"
    return Q_DIR / f"{Q_PREF}.ndjson"

def _append_ndjson(payload: Dict[str, Any]) -> Path:
    path = _queue_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path

def _post_webhook(payload: Dict[str, Any]) -> bool:
    if not WEBHOOK_URL:
        return False
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Signature"] = sig
    try:
        r = requests.post(WEBHOOK_URL, data=body, headers=headers, timeout=10)
        ok = 200 <= r.status_code < 300
        if not ok:
            print("[webhook] failed:", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        print("[webhook] error:", e)
        return False

def _fmt_price(x: float) -> str:
    return f"{x:.6f}".rstrip("0").rstrip(".")

def _q_emoji(q: float) -> str:
    return "🟢" if q >= 0.75 else "🟡" if q >= 0.5 else "🟠" if q >= 0.25 else "🔘"

def _render_for_telegram(s: Dict[str, Any]) -> Tuple[str, List[str]]:
    mkt = s.get("market","").upper()
    title = f"🚀 Signal {s['symbol']} — {s['side'].upper()} ({mkt} {s.get('tf','?')})"
    lines = [
        f"Entry: {_fmt_price(s['entry'])} | SL: {_fmt_price(s['sl'])}",
        f"TP1: {_fmt_price(s['tp1'])} | TP2: {_fmt_price(s['tp2'])} | TP3: {_fmt_price(s['tp3'])}",
        f"Quality: {_q_emoji(s['confidence'])} {s['confidence']:.2f}",
    ]
    ctx = s.get("context") or s.get("reasons") or s.get("bullets")
    if ctx:
        lines.append("*Context*")
        for c in list(ctx)[:6]:
            lines.append("• " + str(c))
    # quick-tap helpers
    base = s["symbol"]
    side_l = "buy" if s["side"] == "buy" else "sell"
    lines.append("")
    lines.append(f"Tap: /{side_l} {base} <qty>   /flat {base}   /balance")
    src = "MT5" if mkt == "FX" else "CCXT"
    lines.append(f"_Source: {src} | TF: {s.get('tf','?')}_")
    return title, lines

# ------------ public API ------------
def publish_signal(sig: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish one signal (idempotent):
      - validate & normalize
      - de-dupe within DEDUP window
      - rate-limit Telegram/Webhook (queue always written)
      - NDJSON queue, webhook, Telegram
    Return: {"ok":bool, "id":fp, "path":file, "notified":{...}, "skipped_reason":str|None}
    """
    ts = int(time.time())
    try:
        s = _validate_and_normalize(sig)
    except Exception as e:
        return {"ok": False, "error": f"validate: {e}"}

    if s["confidence"] < MINCONF:
        return {"ok": False, "id": None, "skipped_reason": f"conf<{MINCONF}"}

    fp = _fingerprint(s)
    s = dict(s, id=fp, ts=ts)

    # de-dupe
    seen = _load_seen()
    last = seen.get(fp)
    nowf = float(ts)
    if last and nowf - last < DEDUP_S:
        return {"ok": False, "id": fp, "skipped_reason": "duplicate_window"}

    # always queue
    path = _append_ndjson(s)

    # optional memory snapshot at "publish-time" (best-effort)
    try:
        if pm_record and s.get("symbol") and s.get("tf"):
            # if caller embeds a small df snapshot in s.get("df"), pm_record will extract features
            df = s.get("df")
            if df is not None:
                pm_record(s["symbol"], s["tf"], df, float(s.get("entry", 0.0)),
                          {"side": s["side"], "conf": s.get("confidence", 0.0), "market": s.get("market","")})
    except Exception:
        pass

    # outbound notifications (rate limited)
    notified: Dict[str, Any] = {"rate_limited": False, "telegram": False, "webhook": False}
    if _BUCKET.allow():
        try:
            title, lines = _render_for_telegram(s)
            notified["telegram"] = bool(tg_send(title, lines))
        except Exception as e:
            print("[telegram] error:", e)
        notified["webhook"] = _post_webhook(s)
    else:
        notified["rate_limited"] = True

    # remember fp
    seen[fp] = nowf
    _save_seen(seen)

    return {"ok": True, "id": fp, "path": str(path), "notified": notified}

def publish_batch(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in signals:
        try:
            out.append(publish_signal(s))
        except Exception as e:
            out.append({"ok": False, "error": str(e)})
    return out

# ------------ CLI quick test ------------
if __name__ == "__main__":
    demo = {
        "market":"crypto","symbol":"BTC/USDT","tf":"5m","side":"buy",
        "entry": 60000.0, "tp1": 60100.0, "tp2": 60200.0, "tp3": 60400.0,
        "sl": 59880.0, "confidence": 0.78,
        "context": ["MTF aligned ↑", "ATR ok", "News tailwind"],
    }
    print(json.dumps(publish_signal(demo), indent=2))
