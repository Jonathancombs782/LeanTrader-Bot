# tg_utils.py
from __future__ import annotations
import os, time, requests
from typing import List, Optional

# --- ENV ---
ENABLED   = os.getenv("TELEGRAM_ENABLED", "true").strip().lower() in ("1","true","yes","on")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TIMEOUT_S = int(os.getenv("TELEGRAM_TIMEOUT", "10"))
RETRY     = int(os.getenv("TELEGRAM_RETRY", "1"))  # quick retry count (0/1/2)

API_BASE  = f"https://api.telegram.org/bot{BOT_TOKEN}"

def _enabled() -> bool:
    return ENABLED and bool(BOT_TOKEN) and bool(CHAT_ID)

# Minimal Markdown escaping (Telegram MarkdownV2 is stricter; we keep classic Markdown)
_MD_REPLACE = {
    "_": r"\_",
    "*": r"\*",
    "`": r"\`",
    "[": r"\[",
}

def _md(text: str) -> str:
    out = []
    for ch in text:
        out.append(_MD_REPLACE.get(ch, ch))
    return "".join(out)

def _post_json(method: str, payload: dict) -> bool:
    if not _enabled():
        return False
    url = f"{API_BASE}/{method}"
    tries = max(1, RETRY + 1)
    for _ in range(tries):
        try:
            r = requests.post(url, json=payload, timeout=TIMEOUT_S)
            if r.status_code == 200 and (r.json().get("ok", False) if r.headers.get("content-type","").startswith("application/json") else True):
                return True
        except Exception:
            pass
        time.sleep(0.4)  # tiny backoff
    return False

# -------- Public helpers --------
def send_signal(title: str, lines: List[str]) -> bool:
    """
    Send a formatted trading signal.
    Called as tg_send(title, lines) from signals_publisher.py.
    """
    if not _enabled():
        return False
    text = f"*{_md(title)}*\n" + "\n".join(_md(l) for l in lines)
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    return _post_json("sendMessage", payload)

def send_text(msg: str) -> bool:
    """Plain text convenience notifier."""
    if not _enabled():
        return False
    payload = {
        "chat_id": CHAT_ID,
        "text": _md(msg),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    return _post_json("sendMessage", payload)

def send_photo(caption: str, photo_url: str) -> bool:
    """Optional: send a photo (e.g., chart image URL) with caption."""
    if not _enabled():
        return False
    payload = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": _md(caption),
        "parse_mode": "Markdown",
    }
    return _post_json("sendPhoto", payload)

def heartbeat(title: str, lines: List[str]) -> bool:
    """Small wrapper for periodic status messages."""
    return send_signal(title, lines)
