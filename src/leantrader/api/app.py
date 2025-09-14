import json
import json as _json
import os
import threading
import time as _time
from pathlib import Path
from typing import Dict

import pandas as pd
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..api.admin_ui import router as admin_router
from ..api.trade_ui import router as trade_router
from ..execution.router import route_order
from ..live.notifier import publish_signal as tg_publish
from ..live.signal_service import generate_signals
from ..optional_deps import PROM_AVAILABLE
from ..users.store import UserProfile, get_keys, get_profile, set_keys, upsert_profile

# load .env for local runs
load_dotenv()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def require_admin(token: str = Query("")):
    if ADMIN_TOKEN and token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="invalid admin token")
    return True


app = FastAPI(title="LeanTrader API", version="0.4")
app.include_router(trade_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _csv_path(pair: str, tf: str) -> str:
    p = pair.replace("/", "")
    return f"data/ohlc/{p}_{tf}.csv"


def _load_frames(pair: str):
    frames = {}
    for tf in ["D1", "H4", "H1", "M15"]:
        fp = _csv_path(pair, tf)
        if os.path.exists(fp):
            df = pd.read_csv(fp, parse_dates=["time"], index_col="time")
            frames[tf] = df[["open", "high", "low", "close"]].sort_index()
    return frames


@app.get("/signal")
def signal(pair: str = Query("EURUSD"), post: bool = Query(False), preview: bool = Query(False)):
    frames = _load_frames(pair)
    if not frames:
        return {"error": "No data found. Place CSVs in data/ohlc/<PAIR>_<TF>.csv with time,open,high,low,close."}
    sigs = generate_signals(frames, pair, post=False)
    last = sigs.tail(1).to_dict(orient="records")[0] if len(sigs) else {}
    # Ensure required keys exist
    last.setdefault("confidence", 0.0)
    last.setdefault("rationale", ["trend", "momentum", "volatility"])  # minimal placeholder
    last.setdefault("chart_path", "")
    # Optional: publish to Telegram immediately
    if post and last:
        try:
            # Build signal_id
            import hashlib
            import time as _t

            sid_src = f"{pair}|{int(_t.time())}|{last.get('entry', 0.0)}|{last.get('side', '')}"
            signal_id = hashlib.sha256(sid_src.encode("utf-8")).hexdigest()[:16]
            _publish_signal(
                symbol=pair,
                side=str(last.get("side") or "hold"),
                confidence=float(last.get("confidence", 0.0)),
                rationale=list(last.get("rationale") or []),
                chart_path=str(last.get("chart_path") or ""),
                signal_id=signal_id,
                chat_id_override=(os.getenv("TELEGRAM_PREVIEW_CHAT_ID") if preview else None),
            )
        except Exception:
            pass
    return {"pair": pair, "signal": last}


@app.post("/telegram/callback")
async def telegram_callback(req: Request):
    body = await req.json()
    # Expect callback query payload
    data = body.get("data") or body.get("callback_query", {}).get("data")
    if not data:
        # also accept direct json with action
        data = json.dumps(body)
    try:
        payload = json.loads(data)
        action = payload.get("action")
        if action == "trade":
            order = {
                "symbol": payload.get("pair"),
                "side": payload.get("side"),
                "qty": float(payload.get("qty", 1.0)),
                "price": float(payload.get("price", 0.0)),
            }
            res = route_order(order, os.getenv("BROKER_MODE", "emu"))
            _log_order({"user": payload.get("user", "demo"), "req": order, "res": res})
            return {"ok": True, "routed": True, "payload": payload, "exec": res}
        elif action == "mute":
            # TODO: store mute preference
            return {"ok": True, "muted": payload.get("pair")}
    except Exception:
        pass
    return {"ok": True}


def _orders_path() -> Path:
    p = Path(os.getenv("ORDERS_LOG_PATH", "runtime/orders.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log_order(obj: Dict) -> None:
    p = _orders_path()
    try:
        items = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        items = []
    items.append(obj)
    p.write_text(json.dumps(items, indent=2), encoding="utf-8")


@app.get("/orders")
def list_orders(user: str = Query("demo")):
    try:
        items = json.loads(_orders_path().read_text(encoding="utf-8"))
    except Exception:
        items = []
    out = [x for x in items if str(x.get("user")) == str(user)] or items
    return {"orders": out}


@app.post("/admin/user/create")
def admin_user_create(user_id: str = Query(...), display_name: str = Query(""), _: bool = Depends(require_admin)):
    p = UserProfile(user_id=user_id, display_name=display_name)
    upsert_profile(p)
    return {"ok": True, "profile": p.to_public()}


@app.post("/admin/user/setkeys")
def admin_user_setkeys(
    user_id: str = Query(...),
    fx_key: str = Body(default=""),
    fx_secret: str = Body(default=""),
    ccxt_key: str = Body(default=""),
    ccxt_secret: str = Body(default=""),
):
    set_keys(user_id, fx_key or None, fx_secret or None, ccxt_key or None, ccxt_secret or None)
    return {"ok": True}


@app.get("/admin/user/get")
def admin_user_get(user_id: str = Query(...), _: bool = Depends(require_admin)):
    p = get_profile(user_id)
    if not p:
        return {"ok": False, "error": "not found"}
    ks = get_keys(user_id)
    # redact secrets in response (only lengths shown)
    red = {k: (len(v) if v else 0) for k, v in ks.items()}
    return {"ok": True, "profile": p.to_public(), "keys_present": red}


BROKER_MODE = os.getenv("BROKER_MODE", "emu").lower()


def _exec_market(symbol: str, side: str, qty: float, price: float):
    if BROKER_MODE == "emu":
        from ..execution.broker_emulator import BrokerEmulator

        emu = BrokerEmulator()
        return emu.market(symbol, side, qty, price)
    elif BROKER_MODE == "ccxt":
        return {"status": "todo_ccxt"}
    elif BROKER_MODE == "fx":
        return {"status": "todo_fx"}
    else:
        return {"status": "unknown_mode"}


@app.post("/admin/premium/add")
def admin_premium_add(chat_id: str = Query(...), _: bool = Depends(require_admin)):
    path = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"premium_chat_ids": []}
    if os.path.exists(path):
        import json as _json

        data = _json.loads(open(path, "r", encoding="utf-8").read())
    if str(chat_id) not in map(str, data.get("premium_chat_ids", [])):
        data.setdefault("premium_chat_ids", []).append(str(chat_id))
    open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2))
    return {"ok": True, "premium_chat_ids": data["premium_chat_ids"]}


@app.post("/admin/premium/remove")
def admin_premium_remove(chat_id: str = Query(...), _: bool = Depends(require_admin)):
    path = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")
    if not os.path.exists(path):
        return {"ok": True, "premium_chat_ids": []}
    import json as _json

    data = _json.loads(open(path, "r", encoding="utf-8").read())
    data["premium_chat_ids"] = [str(x) for x in data.get("premium_chat_ids", []) if str(x) != str(chat_id)]
    open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2))
    return {"ok": True, "premium_chat_ids": data["premium_chat_ids"]}


@app.get("/admin/premium/list")
def admin_premium_list(_: bool = Depends(require_admin)):
    path = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")
    if not os.path.exists(path):
        return {"premium_chat_ids": []}
    import json as _json

    data = _json.loads(open(path, "r", encoding="utf-8").read())
    return {"premium_chat_ids": data.get("premium_chat_ids", [])}


app.include_router(admin_router)


# ------- Telegram publish helper with counters + optional Redis fanout -------
_PUBLISHED_COUNT = 0
_LAST_PUBLISH_TS = 0

# Prometheus client metrics (optional)
_PROM_REG = None
_C_PUBLISHED = None
_G_LAST_TS = None
_G_ORDERS = None
_G_TRADES = None
_G_WINRATE = None
_G_AVG_R = None


def _maybe_init_prom():
    global _PROM_REG, _C_PUBLISHED, _G_LAST_TS, _G_ORDERS, _G_TRADES, _G_WINRATE, _G_AVG_R
    if not PROM_AVAILABLE or _PROM_REG is not None:
        return
    try:
        from prometheus_client import CollectorRegistry, Counter, Gauge  # type: ignore

        _PROM_REG = CollectorRegistry()
        _C_PUBLISHED = Counter("lt_signals_published_total", "Signals published", registry=_PROM_REG)
        _G_LAST_TS = Gauge("lt_last_publish_timestamp_seconds", "Last publish timestamp", registry=_PROM_REG)
        _G_ORDERS = Gauge("lt_orders_total", "Orders logged", registry=_PROM_REG)
        _G_TRADES = Gauge("lt_trades_total", "Trades logged", registry=_PROM_REG)
        _G_WINRATE = Gauge("lt_learn_winrate", "Winrate", registry=_PROM_REG)
        _G_AVG_R = Gauge("lt_learn_avg_r", "Average R", registry=_PROM_REG)
    except Exception:
        _PROM_REG = None


def _publish_signal(
    *,
    symbol: str,
    side: str,
    confidence: float,
    rationale: list,
    chart_path: str,
    signal_id: str,
    chat_id_override: str | None = None,
) -> bool:
    global _PUBLISHED_COUNT, _LAST_PUBLISH_TS
    ok = False
    try:
        ok = bool(
            tg_publish(
                symbol=symbol,
                side=side,
                confidence=float(confidence),
                rationale=list(rationale or []),
                chart_path=str(chart_path or ""),
                signal_id=str(signal_id),
                chat_id=chat_id_override or None,
            )
        )
    except Exception:
        ok = False
    if ok:
        _PUBLISHED_COUNT += 1
        try:
            _LAST_PUBLISH_TS = int(__import__("time").time())
            _maybe_init_prom()
            if _C_PUBLISHED:
                _C_PUBLISHED.inc()
            if _G_LAST_TS:
                _G_LAST_TS.set(float(_LAST_PUBLISH_TS))
        except Exception:
            pass
        # optional Redis fanout
        try:
            url = os.getenv("REDIS_URL")
            if url:
                import redis  # type: ignore

                r = redis.StrictRedis.from_url(url)
                payload = {
                    "symbol": symbol,
                    "side": side,
                    "confidence": float(confidence),
                    "id": signal_id,
                }
                r.publish(os.getenv("SIGNAL_REDIS_CHANNEL", "lt:signal"), json.dumps(payload))
        except Exception:
            pass
    return ok


@app.post("/run/scan")
def run_scan(
    pairs: str = Query(os.getenv("SCAN_PAIRS", "XAUUSD")), post: bool = Query(False), preview: bool = Query(False)
):
    out = {}
    for pair in [p.strip() for p in pairs.split(",") if p.strip()]:
        frames = _load_frames(pair)
        if not frames:
            out[pair] = {"error": "no_data"}
            continue
        sigs = generate_signals(frames, pair, post=False)
        last = sigs.tail(1).to_dict(orient="records")[0] if len(sigs) else {}
        if post and last:
            try:
                import hashlib
                import time as _t

                sid_src = f"{pair}|{int(_t.time())}|{last.get('entry', 0.0)}|{last.get('side', '')}"
                signal_id = hashlib.sha256(sid_src.encode("utf-8")).hexdigest()[:16]
                _publish_signal(
                    symbol=pair,
                    side=str(last.get("side") or "hold"),
                    confidence=float(last.get("confidence", 0.0)),
                    rationale=list(last.get("rationale") or []),
                    chart_path=str(last.get("chart_path") or ""),
                    signal_id=signal_id,
                    chat_id_override=(os.getenv("TELEGRAM_PREVIEW_CHAT_ID") if preview else None),
                )
            except Exception:
                pass
        out[pair] = last
    return out


@app.post("/publish/signal")
def publish_signal_endpoint(payload: dict, preview: bool = Query(False)):
    try:
        _publish_signal(
            symbol=str(payload.get("symbol")),
            side=str(payload.get("side")),
            confidence=float(payload.get("confidence", 0.0)),
            rationale=list(payload.get("rationale") or []),
            chart_path=str(payload.get("chart_path") or ""),
            signal_id=str(payload.get("signal_id") or "manual"),
            chat_id_override=(
                str(payload.get("chat_id"))
                if payload.get("chat_id")
                else (os.getenv("TELEGRAM_PREVIEW_CHAT_ID") if preview else None)
            ),
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# background scheduler (opt-in)

_SCHED_STOP = False


def _scheduler_seen_path() -> Path:
    p = Path(os.getenv("RUNTIME_DIR", "runtime")) / "scheduler_seen.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_scheduler_seen() -> dict:
    try:
        return _json.loads(_scheduler_seen_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_scheduler_seen(d: dict) -> None:
    try:
        _scheduler_seen_path().write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _scheduler_loop():
    interval = int(os.getenv("SCHEDULER_INTERVAL_SEC", "60"))
    pairs = [p.strip() for p in (os.getenv("SCAN_PAIRS", "XAUUSD").split(",")) if p.strip()]
    seen = _load_scheduler_seen()
    while not _SCHED_STOP:
        try:
            for pair in pairs:
                frames = _load_frames(pair)
                if not frames:
                    continue
                sigs = generate_signals(frames, pair, post=False)
                if len(sigs) == 0:
                    continue
                last = sigs.tail(1).to_dict(orient="records")[0]
                minute = int(pd.Timestamp(sigs.tail(1).index[0]).timestamp()) // 60
                fp = f"{pair}|{last.get('side')}|{minute}"
                if seen.get(pair) == fp:
                    continue
                seen[pair] = fp
                _save_scheduler_seen(seen)
                try:
                    import hashlib

                    src = f"{pair}|{minute}|{last.get('entry', 0.0)}|{last.get('side', '')}"
                    signal_id = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
                    _publish_signal(
                        symbol=pair,
                        side=str(last.get("side") or "hold"),
                        confidence=float(last.get("confidence", 0.0)),
                        rationale=list(last.get("rationale") or []),
                        chart_path=str(last.get("chart_path") or ""),
                        signal_id=signal_id,
                        chat_id_override=None,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        _time.sleep(max(5, interval))


@app.on_event("startup")
def _maybe_start_scheduler():
    enabled = os.getenv("SCHEDULER_ENABLED", "false").lower() in ("1", "true", "yes")
    if not enabled and not os.getenv("REDIS_URL"):
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


@app.on_event("shutdown")
def _stop_scheduler():
    global _SCHED_STOP
    _SCHED_STOP = True


# ---------------------- Prometheus metrics endpoint ----------------------
@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    # Prometheus client preferred when available
    try:
        if PROM_AVAILABLE:
            _maybe_init_prom()
            # refresh gauges from current logs
            try:
                items = json.loads(_orders_path().read_text(encoding="utf-8"))
                if _G_ORDERS:
                    _G_ORDERS.set(float(len(items)))
            except Exception:
                if _G_ORDERS:
                    _G_ORDERS.set(0.0)
            try:
                import csv

                p = Path("logs/learn/trades.csv")
                n = wins = 0
                total_r = 0.0
                if p.exists():
                    with open(p, "r", encoding="utf-8") as f:
                        rdr = csv.DictReader(f)
                        for row in rdr:
                            n += 1
                            r = float(row.get("r_mult") or 0.0)
                            total_r += r
                            if r > 0:
                                wins += 1
                winrate = (wins / n) if n else 0.0
                avg_r = (total_r / n) if n else 0.0
                if _G_TRADES:
                    _G_TRADES.set(float(n))
                if _G_WINRATE:
                    _G_WINRATE.set(float(winrate))
                if _G_AVG_R:
                    _G_AVG_R.set(float(avg_r))
            except Exception:
                pass
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # type: ignore

            data = generate_latest()  # default registry + our custom may be enough
            return PlainTextResponse(data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
    except Exception:
        pass
    # Basic text format exposition
    lines = []
    # signals published counters
    lines.append(f"lt_signals_published_total {_PUBLISHED_COUNT}")
    if _LAST_PUBLISH_TS:
        lines.append(f"lt_last_publish_timestamp_seconds {_LAST_PUBLISH_TS}")
    # orders count
    try:
        items = json.loads(_orders_path().read_text(encoding="utf-8"))
        lines.append(f"lt_orders_total {len(items)}")
    except Exception:
        lines.append("lt_orders_total 0")
    # trades summary
    try:
        import csv

        p = Path("logs/learn/trades.csv")
        n = 0
        wins = 0
        total_r = 0.0
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                for row in rdr:
                    n += 1
                    r = float(row.get("r_mult") or 0.0)
                    total_r += r
                    if r > 0:
                        wins += 1
        winrate = (wins / n) if n else 0.0
        avg_r = (total_r / n) if n else 0.0
        lines.append(f"lt_trades_total {n}")
        lines.append(f"lt_learn_winrate {winrate}")
        lines.append(f"lt_learn_avg_r {avg_r}")
        lines.append(f"lt_learn_expectancy {avg_r}")
    except Exception:
        lines.append("lt_trades_total 0")
        lines.append("lt_learn_winrate 0")
        lines.append("lt_learn_avg_r 0")
        lines.append("lt_learn_expectancy 0")
    return "\n".join(lines) + "\n"


# Ensure route registration in environments with aggressive import timing
try:
    app.add_api_route("/metrics", metrics, methods=["GET"], response_class=PlainTextResponse)
except Exception:
    pass


# ---------------------- Redis Pub/Sub trigger (optional) ----------------------
def _redis_subscriber_loop():
    url = os.getenv("REDIS_URL")
    channel = os.getenv("SCHEDULER_REDIS_CHANNEL", "lt:scan")
    if not url:
        return
    try:
        import redis  # type: ignore

        r = redis.StrictRedis.from_url(url)
        ps = r.pubsub()
        ps.subscribe(channel)
        for msg in ps.listen():
            if msg is None or msg.get("type") != "message":
                continue
            data = msg.get("data")
            try:
                txt = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
                payload = json.loads(txt) if txt.strip().startswith("{") else {"cmd": "scan"}
                if payload.get("cmd") == "scan":
                    pairs = str(payload.get("pairs") or os.getenv("SCAN_PAIRS", "XAUUSD"))
                    post = bool(payload.get("post", False))
                    preview = bool(payload.get("preview", False))
                    run_scan(pairs=pairs, post=post, preview=preview)
            except Exception:
                continue
    except Exception:
        return


@app.on_event("startup")
def _maybe_start_redis_subscriber():
    if not os.getenv("REDIS_URL"):
        return
    t = threading.Thread(target=_redis_subscriber_loop, daemon=True)
    t.start()


# (deprecated duplicate /run/scan removed; consolidated above)
