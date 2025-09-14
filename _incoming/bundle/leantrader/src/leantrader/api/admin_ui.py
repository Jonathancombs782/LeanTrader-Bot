import json
import os

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from ..users.store import get_keys, get_profile, set_keys, upsert_profile

PREMIUM_PATH = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")

router = APIRouter()

HTML_PAGE = """
<!doctype html>
<html><head><meta charset="utf-8"/><title>LeanTrader Admin</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;}
.card{max-width:720px;margin:auto;border:1px solid #ddd;border-radius:12px;padding:16px;box-shadow:0 4px 18px rgba(0,0,0,.05)}
h1{font-size:20px;margin:0 0 12px}
label{display:block;margin-top:10px;font-weight:600}
input{width:100%;padding:10px;border:1px solid #ccc;border-radius:10px}
button{margin-top:12px;padding:10px 16px;border:none;border-radius:10px;background:#111827;color:#fff;cursor:pointer}
pre{background:#f3f4f6;padding:12px;border-radius:10px;overflow:auto}
</style></head><body>
<div class="card">
<h1>Premium Manager</h1>
<form method="post" action="/admin/premium/add">
<label>Chat ID</label><input name="chat_id"/>
<button>Add Premium</button>
</form>
<form method="post" action="/admin/premium/remove">
<label>Chat ID</label><input name="chat_id"/>
<button>Remove Premium</button>
</form>
<p>Current List:</p>
<pre id="prem">{prem}</pre>
</div>

<div class="card">
<h1>User Keys</h1>
<form method="post" action="/admin/user/setkeys">
<label>User ID</label><input name="user_id" value="demo"/>
<label>FX Key</label><input name="fx_key"/>
<label>FX Secret</label><input name="fx_secret"/>
<label>CCXT Key</label><input name="ccxt_key"/>
<label>CCXT Secret</label><input name="ccxt_secret"/>
<button>Save Keys</button>
</form>
</div>
</body></html>
"""


def _read_premium():
    try:
        with open(PREMIUM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"premium_chat_ids": []}


def _write_premium(obj):
    os.makedirs(os.path.dirname(PREMIUM_PATH), exist_ok=True)
    with open(PREMIUM_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(HTML_PAGE.format(prem=json.dumps(_read_premium(), indent=2)))


@router.post("/admin/premium/add")
def admin_premium_add(chat_id: str = Form(...)):
    obj = _read_premium()
    ids = set(str(x) for x in obj.get("premium_chat_ids", []))
    ids.add(str(chat_id))
    obj["premium_chat_ids"] = sorted(list(ids))
    _write_premium(obj)
    return JSONResponse({"ok": True, "premium_chat_ids": obj["premium_chat_ids"]})


@router.post("/admin/premium/remove")
def admin_premium_remove(chat_id: str = Form(...)):
    obj = _read_premium()
    ids = [str(x) for x in obj.get("premium_chat_ids", []) if str(x) != str(chat_id)]
    obj["premium_chat_ids"] = ids
    _write_premium(obj)
    return JSONResponse({"ok": True, "premium_chat_ids": obj["premium_chat_ids"]})


@router.post("/admin/user/setkeys")
def admin_user_keys(
    user_id: str = Form(...),
    fx_key: str = Form(""),
    fx_secret: str = Form(""),
    ccxt_key: str = Form(""),
    ccxt_secret: str = Form(""),
):
    set_keys(user_id, fx_key or None, fx_secret or None, ccxt_key or None, ccxt_secret or None)
    return {"ok": True}
