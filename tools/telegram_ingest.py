"""Telegram ingest via Bot API getUpdates polling.

Environment:
  ENABLE_TELEGRAM_INGEST=true
  TELEGRAM_BOT_TOKEN=...
  SOURCE_CHAT_IDS=<comma separated IDs>   # optional filter
  TELEGRAM_INGEST_LIMIT=100

Writes messages to runtime/strategies/telegram_<chat_id>.txt and runtime/strategies/telegram_<chat_id>.ndjson (with metadata),
and stores offset in runtime/logs/telegram_ingest_state.json
Requires the bot to be a member of the target chats/channels with permission to read messages.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List

import requests


STATE = Path("runtime") / "logs" / "telegram_ingest_state.json"


def _csv(x: str) -> List[str]:
    return [s.strip() for s in (x or "").split(",") if s.strip()]


def _load_state() -> Dict:
    try:
        if STATE.exists():
            return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"offset": 0}


def _save_state(st: Dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass


def ingest_once(timeout: int = 5) -> int:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        return 0
    base = f"https://api.telegram.org/bot{tok}"
    st = _load_state()
    offset = int(st.get("offset", 0))
    lim = int(os.getenv("TELEGRAM_INGEST_LIMIT", "100"))
    url = f"{base}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset + 1, "timeout": timeout, "limit": lim}, timeout=timeout + 2)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        return 0
    res = j.get("result", [])
    if not res:
        return 0
    allow_ids = set()
    src_env = os.getenv("SOURCE_CHAT_IDS", "").strip()
    if src_env:
        try:
            allow_ids = set(int(x) for x in _csv(src_env))
        except Exception:
            allow_ids = set()
    outdir = Path("runtime") / "strategies"
    outdir.mkdir(parents=True, exist_ok=True)
    saved = 0
    last_id = offset
    for upd in res:
        try:
            last_id = max(last_id, int(upd.get("update_id", last_id)))
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat", {})
            chat_id = int(chat.get("id")) if chat.get("id") is not None else None
            if chat_id is None:
                continue
            if allow_ids and chat_id not in allow_ids:
                continue
            txt = msg.get("text") or msg.get("caption")
            if not txt:
                continue
            # Plain text file
            fname = outdir / (f"telegram_{chat_id}.txt")
            with fname.open("a", encoding="utf-8") as f:
                f.write(f"{int(time.time())}\t{txt}\n")
            # NDJSON with metadata
            meta = {
                "ts": int(time.time()),
                "update_id": last_id,
                "chat_id": chat_id,
                "chat_title": chat.get("title") or chat.get("username"),
                "message_id": msg.get("message_id"),
                "from_id": (msg.get("from") or {}).get("id"),
                "text": txt,
                "entities": msg.get("entities"),
                "reply_to_message_id": (msg.get("reply_to_message") or {}).get("message_id"),
                "forward_from": (msg.get("forward_from") or {}).get("id"),
            }
            json_path = outdir / (f"telegram_{chat_id}.ndjson")
            with json_path.open("a", encoding="utf-8") as jf:
                jf.write(json.dumps(meta, ensure_ascii=False) + "\n")
            saved += 1
        except Exception:
            continue
    st["offset"] = last_id
    _save_state(st)
    return saved


if __name__ == "__main__":
    n = ingest_once()
    print("telegram items stored:", n)
