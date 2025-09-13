# signals_publisher.py
"""
Advanced signal publisher
- Validate & normalize
- Idempotent de-dupe (time window)
- Token-bucket rate limiting
- NDJSON queue (daily roll)
- Optional HTTPS webhook (HMAC-SHA256)
- Telegram push via tg_utils.send_signal(title, lines)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

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

# Ultra Pro mode toggles (opt-in via env)
ULTRA_PRO_MODE: bool = os.getenv("ULTRA_PRO_MODE", "false").strip().lower() in ("1", "true", "yes")
ULTRA_PRO_MINCONF: float = float(os.getenv("ULTRA_PRO_MINCONF", "0.7"))
ULTRA_PRO_INLINE: bool = os.getenv("ULTRA_PRO_INLINE", "true").strip().lower() in ("1", "true", "yes")
ULTRA_PRO_PRIOR_WEIGHT: float = float(os.getenv("ULTRA_PRO_PRIOR_WEIGHT", "0.25"))

WEBHOOK_URL = os.getenv("SIGNALS_WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = os.getenv("SIGNALS_WEBHOOK_SECRET", "").strip()

SEEN_PATH = Q_DIR / "signals_seen.json"
Q_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR = Q_DIR / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Prefer clean confirm button helper if available
try:
    from tg_utils import build_confirm_buttons_clean as _build_confirm_buttons
except Exception:
    try:
        from tg_utils import build_confirm_buttons as _build_confirm_buttons  # type: ignore
    except Exception:
        _build_confirm_buttons = None  # type: ignore


# ------------ token bucket ------------
class _Bucket:
    def __init__(self, per_min: int):
        self.capacity = max(1, int(per_min))
        self.tokens = float(self.capacity)
        self.rate = self.capacity / 60.0  # tokens per second
        self.last = time.time()

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self.last
        # refill tokens
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# instantiate module-level bucket
_BUCKET = _Bucket(RATE_PM)


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
    except Exception as _e:
        print("[webhook] error:", _e)
        return False


def _fmt_price(x: float) -> str:
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _fingerprint(s: Dict[str, Any]) -> str:
    """Create a stable fingerprint for a signal dict."""
    try:
        j = json.dumps({k: s.get(k) for k in sorted(s.keys())}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(j.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha1(str(s).encode("utf-8")).hexdigest()


def _load_seen() -> Dict[str, float]:
    if SEEN_PATH.exists():
        try:
            return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_seen(seen: Dict[str, float]) -> None:
    try:
        SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _validate_and_normalize(sig: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal validation/normalization to keep behavior stable."""
    out = dict(sig)
    # ensure required fields exist with defaults
    out.setdefault("symbol", "")
    out.setdefault("side", "")
    out.setdefault("entry", 0.0)
    out.setdefault("sl", 0.0)
    out.setdefault("tp1", 0.0)
    out.setdefault("tp2", 0.0)
    out.setdefault("tp3", 0.0)
    out.setdefault("confidence", 0.0)
    out.setdefault("market", "")
    out.setdefault("tf", "")
    # normalize types
    try:
        out["confidence"] = float(out.get("confidence", 0.0))
    except Exception:
        out["confidence"] = 0.0
    return out


def _q_emoji2(q: float) -> str:
    """ASCII/emoji confidence badge based on env TELEGRAM_ASCII."""
    ascii_only = os.getenv("TELEGRAM_ASCII", "false").strip().lower() in ("1", "true", "yes")
    try:
        q = float(q)
    except Exception:
        q = 0.0
    q = max(0.0, min(1.0, q))
    if ascii_only:
        return f"Q{int(q*100):d}%"
    return "🟢" if q >= 0.75 else "🟡" if q >= 0.5 else "🟠" if q >= 0.25 else "⚪"


def _render_for_telegram2(s: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Clean renderer for Telegram message title + lines.

    Keeps strings ASCII-safe when TELEGRAM_ASCII=true; otherwise uses mild unicode.
    """
    mkt = str(s.get("market", "")).upper()
    tf = str(s.get("tf", "?"))
    side = str(s.get("side", "?")).upper()
    ascii_only = os.getenv("TELEGRAM_ASCII", "false").strip().lower() in ("1", "true", "yes")
    sep = " | " if ascii_only else " · "
    title = f"Signal{sep}{s.get('symbol', '')}{sep}{side}{sep}{tf}{sep}{mkt}"

    entry = float(s.get("entry", 0.0))
    sl = float(s.get("sl", 0.0))
    tp1 = float(s.get("tp1", 0.0))
    tp2 = float(s.get("tp2", 0.0))
    tp3 = float(s.get("tp3", 0.0))

    def _rr(tp: float) -> str:
        try:
            risk = abs(entry - sl)
            if risk == 0:
                return "n/a"
            reward = abs(tp - entry)
            return f"{(reward / risk):.2f}"
        except Exception:
            return "n/a"

    lines: List[str] = []
    lines.append(
        f"Entry: {_fmt_price(entry)}  |  SL: {_fmt_price(sl)}  |  Q: {_q_emoji2(s.get('confidence', 0.0))} {float(s.get('confidence', 0.0)):.2f}"
    )
    lines.append(
        f"TP1: {_fmt_price(tp1)} (RR {_rr(tp1)})  |  TP2: {_fmt_price(tp2)} (RR {_rr(tp2)})  |  TP3: {_fmt_price(tp3)} (RR {_rr(tp3)})"
    )

    ctx = s.get("context") or s.get("reasons") or s.get("bullets")
    if ctx:
        lines.append("")
        lines.append("*Why this trade?*")
        bullet = "- " if ascii_only else "• "
        for c in list(ctx)[:6]:
            lines.append(bullet + str(c))

    base = s.get("symbol", "")
    side_l = "buy" if str(s.get("side", "")).lower() == "buy" else "sell"
    lines.append("")
    lines.append(f"Quick: /{side_l} {base} <qty>   /flat {base}   /balance")

    src = "MT5" if mkt == "FX" else "CCXT"
    lines.append(f"_Source: {src} | TF: {tf}_")

    try:
        ts = int(s.get("ts", time.time()))
        from datetime import datetime as _dt

        lines.append(f"_Published: {_dt.utcfromtimestamp(ts).isoformat()}Z_")
    except Exception:
        pass

    return title, lines


def _q_emoji(q: float) -> str:
    return "🟢" if q >= 0.75 else "🟡" if q >= 0.5 else "🟠" if q >= 0.25 else "🔘"


def _render_for_telegram(s: Dict[str, Any]) -> Tuple[str, List[str]]:
    mkt = s.get("market", "").upper()
    tf = s.get("tf", "?")
    side = s.get("side", "?").upper()
    title = f"🚀 Signal — {s['symbol']} · {side} · {tf} · {mkt}"

    entry = float(s.get("entry", 0.0))
    sl = float(s.get("sl", 0.0))
    tp1 = float(s.get("tp1", 0.0))
    tp2 = float(s.get("tp2", 0.0))
    tp3 = float(s.get("tp3", 0.0))

    def _rr(tp: float) -> str:
        try:
            risk = abs(entry - sl)
            if risk == 0:
                return "n/a"
            reward = abs(tp - entry)
            return f"{(reward / risk):.2f}"
        except Exception:
            return "n/a"

    lines: List[str] = []
    # Header summary
    lines.append(
        f"Entry: {_fmt_price(entry)}  ·  SL: {_fmt_price(sl)}  ·  Q: {_q_emoji(s['confidence'])} {s['confidence']:.2f}"
    )
    lines.append(
        f"TP1: {_fmt_price(tp1)} (RR {_rr(tp1)})  ·  TP2: {_fmt_price(tp2)} (RR {_rr(tp2)})  ·  TP3: {_fmt_price(tp3)} (RR {_rr(tp3)})"
    )

    # Rationale / context
    ctx = s.get("context") or s.get("reasons") or s.get("bullets")
    if ctx:
        lines.append("")
        lines.append("*Why this trade?*")
        for c in list(ctx)[:6]:
            lines.append("• " + str(c))

    # Quick action helpers
    base = s["symbol"]
    side_l = "buy" if s["side"] == "buy" else "sell"
    lines.append("")
    lines.append(f"Quick: /{side_l} {base} <qty>   /flat {base}   /balance")

    src = "MT5" if mkt == "FX" else "CCXT"
    lines.append(f"_Source: {src} | TF: {tf}_")

    # Small footer (timestamped)
    try:
        ts = int(s.get("ts", time.time()))
        lines.append(f"_Published: {datetime.utcfromtimestamp(ts).isoformat()}Z_")
    except Exception:
        pass

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
    except Exception as _e:
        return {"ok": False, "error": f"validate: {_e}"}

    # Ultra Pro: read env toggles dynamically per-call (so tests and runtime can tweak without restart)
    ultra_mode = os.getenv("ULTRA_PRO_MODE", "false").strip().lower() in ("1", "true", "yes")
    ultra_minconf = float(os.getenv("ULTRA_PRO_MINCONF", str(ULTRA_PRO_MINCONF)))
    ultra_prior_w = float(os.getenv("ULTRA_PRO_PRIOR_WEIGHT", str(ULTRA_PRO_PRIOR_WEIGHT)))
    ultra_inline = os.getenv("ULTRA_PRO_INLINE", "true").strip().lower() in ("1", "true", "yes")

    eff_minconf = max(MINCONF, ultra_minconf) if ultra_mode else MINCONF
    if ultra_mode:
        try:
            from pattern_memory import get_score as _get_prior

            prior = _get_prior(s) or {}
            winrate = float(prior.get("winrate", 0.5))
            prior_conf = 0.5 + max(0.0, min(1.0, winrate)) * 0.5
            s["context"] = list(s.get("context") or [])
            s["context"].insert(
                0, f"Prior winrate {winrate*100:.1f}% avg_out {prior.get('avg_out', 0.0):.4f} n={prior.get('n', 0)}"
            )
            w = max(0.0, min(1.0, ultra_prior_w))
            s["confidence"] = max(0.0, min(1.0, (1 - w) * float(s.get("confidence", 0.0)) + w * prior_conf))
        except Exception:
            pass
    if s["confidence"] < eff_minconf:
        return {"ok": False, "id": None, "skipped_reason": f"conf<{eff_minconf}"}

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
                pm_record(
                    s["symbol"],
                    s["tf"],
                    df,
                    float(s.get("entry", 0.0)),
                    {
                        "side": s["side"],
                        "conf": s.get("confidence", 0.0),
                        "market": s.get("market", ""),
                    },
                )
    except Exception:
        pass

    # outbound notifications (rate limited)
    notified: Dict[str, Any] = {
        "rate_limited": False,
        "telegram": False,
        "telegram_chart": False,
        "webhook": False,
    }
    chart_url = None
    chart_path = None
    # --- chart generation (pro-grade candlestick) ---
    try:
        from charting import plot_candlestick

        # Try to fetch an ohlcv snapshot if caller provided 'df' or 'ohlcv'
        ohlcv = s.get("ohlcv") or s.get("df")
        # If absent, try to fetch a tiny recent window via router if included (best-effort)
        if ohlcv is None and s.get("market"):
            # many callers embed a 'df' or rely on external router; we won't attempt network here
            ohlcv = None

        fname = f"{s['symbol'].replace('/', '_')}_{int(time.time())}.png"
        chart_path = str((CHART_DIR / fname).resolve())
        # plot_candlestick will fallback to a simple chart if no mplfinance
        plot_candlestick(
            s.get("symbol", ""),
            ohlcv or [],
            entries=[{"ts": s.get("ts") * 1000, "price": s.get("entry"), "side": s.get("side")}],
            tps=[s.get("tp1"), s.get("tp2"), s.get("tp3")],
            sl=s.get("sl"),
            out_path=chart_path,
        )
        # local file path used for upload
        chart_url = chart_path
    except Exception:
        chart_url = None

    if _BUCKET.allow():
        try:
            # Use sanitized renderer
            try:
                title, lines = _render_for_telegram2(s)
            except Exception:
                title, lines = ("Signal", [])

            # market snapshot: try to generate an educative summary
            try:
                from charting import analyze_ohlcv

                ohlcv = s.get("ohlcv") or s.get("df") or []
                # best-effort: try to fetch a small OHLCV sample if missing
                if not ohlcv:
                    try:
                        from tools.market_data import fetch_ohlcv_multi

                        # try common exchanges quickly (best-effort)
                        ex_used, rows = fetch_ohlcv_multi(
                            ["binance", "bybit"], s.get("symbol"), timeframe=s.get("tf", "1m"), limit=150
                        )
                        ohlcv = rows
                    except Exception:
                        ohlcv = []
                snap = analyze_ohlcv(ohlcv)
                if snap:
                    lines.insert(0, "*Market Snapshot*")
                    lines.insert(
                        1,
                        f"Trend: {snap.get('trend')} ({snap.get('trend_score'):.4f}) | RSI: {snap.get('rsi')} | ATR: {snap.get('atr')}",
                    )
                    lines.insert(2, f"Momentum: {snap.get('momentum_pct')}% | Vol: {snap.get('volatility')}")
            except Exception:
                pass

            sent_ok = False
            if ultra_mode and ultra_inline and _build_confirm_buttons is not None:
                try:
                    from tg_utils import send_message_with_buttons, send_photo_with_buttons
                except Exception:
                    send_photo_with_buttons = None  # type: ignore
                    send_message_with_buttons = None  # type: ignore
                try:
                    buttons = _build_confirm_buttons(fp, include_simulate=True, include_subscribe=True)  # type: ignore
                except Exception:
                    buttons = []
                if buttons:
                    if chart_url and send_photo_with_buttons:
                        sent_ok = bool(send_photo_with_buttons(title, chart_url, buttons))
                    elif send_message_with_buttons:
                        text = title + ("\n\n" + "\n".join(lines) if lines else "")
                        sent_ok = bool(send_message_with_buttons(text, buttons))
            if not sent_ok:
                notified["telegram"] = bool(tg_send(title, lines))
            else:
                notified["telegram"] = True

            # Send chart image if available (skip if already sent with buttons in Ultra inline mode)
            if chart_url and not (ultra_mode and ultra_inline and sent_ok):
                try:
                    from tg_utils import send_photo

                    # photo caption: short trend overview
                    caption = title
                    try:
                        if snap:
                            caption = f"{title} — {snap.get('trend')} | RSI {snap.get('rsi')} | ATR {snap.get('atr')}"
                    except Exception:
                        pass
                    # If CHART_PUBLIC_URL is set, construct the remote URL and send that
                    public_base = os.getenv("CHART_PUBLIC_URL", "").strip()
                    if public_base:
                        import urllib.parse as _up

                        rel = _up.quote(os.path.basename(chart_url))
                        photo_remote = public_base.rstrip("/") + "/" + rel
                        notified["telegram_chart"] = bool(send_photo(caption, photo_remote))
                    else:
                        # fallback to local multipart upload
                        notified["telegram_chart"] = bool(send_photo(caption, chart_url))
                except Exception as _e:
                    print("[telegram chart] error:", _e)
        except Exception as _e:
            print("[telegram] error:", _e)
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
        except Exception as _e:
            out.append({"ok": False, "error": str(_e)})
    return out


# ------------ CLI quick test ------------
if __name__ == "__main__":
    demo = {
        "market": "crypto",
        "symbol": "BTC/USDT",
        "tf": "5m",
        "side": "buy",
        "entry": 60000.0,
        "tp1": 60100.0,
        "tp2": 60200.0,
        "tp3": 60400.0,
        "sl": 59880.0,
        "confidence": 0.78,
        "context": ["MTF aligned ↑", "ATR ok", "News tailwind"],
    }
    print(json.dumps(publish_signal(demo), indent=2))
