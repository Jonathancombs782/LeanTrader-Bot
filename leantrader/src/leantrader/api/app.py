import json
import os

import pandas as pd
from fastapi import Body, FastAPI, Query, Request

from ..api.admin_ui import router as admin_router
from ..api.trade_ui import router as trade_router
from ..live.signal_service import generate_signals
from ..users.store import UserProfile, get_keys, get_profile, set_keys, upsert_profile

app = FastAPI(title="LeanTrader API", version="0.3")
app.include_router(trade_router)
app.include_router(admin_router)


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
def signal(pair: str = Query("EURUSD")):
    frames = _load_frames(pair)
    if not frames:
        return {"error": "No data found. Place CSVs in data/ohlc/<PAIR>_<TF>.csv with time,open,high,low,close."}
    sigs = generate_signals(frames, pair)
    last = sigs.tail(1).to_dict(orient="records")[0] if len(sigs) else {}
    return {"pair": pair, "signal": last}


@app.post("/telegram/callback")
async def telegram_callback(req: Request):
    body = await req.json()
    # Expect callback query payload
    data = body.get("data") or body.get("callback_query", {}).get("data")
    if not data:
        return {"ok": True}
    try:
        payload = json.loads(data)
        action = payload.get("action")
        if action == "trade":
            res = _exec_market(
                payload.get("pair"),
                payload.get("side"),
                float(payload.get("qty", 1.0)),
                float(payload.get("price", 0.0)),
            )
            return {"ok": True, "routed": True, "payload": payload, "exec": res}
        elif action == "mute":
            # Store mute preference
            try:
                user_id = payload.get("user", "demo")
                pair = payload.get("pair")
                if pair:
                    mute_path = Path(os.getenv("MUTE_PREFS_PATH", "data/telegram/mute_prefs.json"))
                    mute_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    mute_data = {}
                    if mute_path.exists():
                        try:
                            mute_data = json.loads(mute_path.read_text(encoding="utf-8"))
                        except Exception:
                            mute_data = {}
                    
                    # Add to user's muted pairs
                    if user_id not in mute_data:
                        mute_data[user_id] = []
                    if pair not in mute_data[user_id]:
                        mute_data[user_id].append(pair)
                    
                    mute_path.write_text(json.dumps(mute_data, indent=2), encoding="utf-8")
            except Exception:
                pass  # Silent fail
            return {"ok": True, "muted": payload.get("pair")}
    except Exception:
        pass
    return {"ok": True}


@app.post("/admin/user/create")
def admin_user_create(user_id: str = Query(...), display_name: str = Query("")):
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
def admin_user_get(user_id: str = Query(...)):
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
def admin_premium_add(chat_id: str = Query(...)):
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
def admin_premium_remove(chat_id: str = Query(...)):
    path = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")
    if not os.path.exists(path):
        return {"ok": True, "premium_chat_ids": []}
    import json as _json

    data = _json.loads(open(path, "r", encoding="utf-8").read())
    data["premium_chat_ids"] = [str(x) for x in data.get("premium_chat_ids", []) if str(x) != str(chat_id)]
    open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2))
    return {"ok": True, "premium_chat_ids": data["premium_chat_ids"]}


@app.get("/admin/premium/list")
def admin_premium_list():
    path = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")
    if not os.path.exists(path):
        return {"premium_chat_ids": []}
    import json as _json

    data = _json.loads(open(path, "r", encoding="utf-8").read())
    return {"premium_chat_ids": data.get("premium_chat_ids", [])}
