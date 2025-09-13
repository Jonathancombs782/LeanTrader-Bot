import json
import os

import requests

BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PREMIUM_PATH = os.getenv("PREMIUM_LIST_PATH", "data/telegram/premium.json")


def _chat_ok(chat_id: str) -> bool:
    try:
        with open(PREMIUM_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        allowed = set(str(x) for x in cfg.get("premium_chat_ids", []))
        return str(chat_id or CHAT_ID) in allowed or not allowed  # if empty, allow all by default
    except Exception:
        return True


def enabled() -> bool:
    return bool(BOT and CHAT_ID)


def _api(method: str):
    return f"https://api.telegram.org/bot{BOT}/{method}"


def send_message(text: str, chat_id: str = None, reply_markup: dict = None) -> bool:
    cid = chat_id or CHAT_ID
    if not _chat_ok(cid):
        return False
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    if reply_markup and is_premium(cid):
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(_api("sendMessage"), json=payload, timeout=15)
        return r.ok
    except Exception:
        return False


def send_photo(image_path: str, caption: str = "", chat_id: str = None, reply_markup: dict = None) -> bool:
    cid = chat_id or CHAT_ID
    if not _chat_ok(cid):
        return False
    files = {"photo": open(image_path, "rb")}
    data = {"chat_id": cid, "caption": caption, "parse_mode": "Markdown"}
    if reply_markup and is_premium(cid):
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(_api("sendPhoto"), data=data, files=files, timeout=30)
        return r.ok
    except Exception:
        return False
