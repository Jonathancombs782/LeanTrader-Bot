from __future__ import annotations

import os
import time
from typing import Optional

import requests


def _enabled() -> bool:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    flag = os.getenv("TELEGRAM_ALERTS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    return flag and bool(tok and chat)


def notify(text: str, chat_id: Optional[str] = None) -> bool:
    """Send a simple text message to Telegram. No-op if not configured.

    - 3 retries
    - 5s timeout
    """
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not _enabled():
        # minimal warning; avoid raising in prod paths
        try:
            print("[tele] telegram not configured or disabled; message suppressed")
        except Exception:
            pass
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    payload = {"chat_id": chat, "text": str(text)}
    last = None
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                return True
            last = r.text
        except Exception as e:
            last = str(e)
        time.sleep(0.4)
    try:
        print("[tele] notify failed:", last)
    except Exception:
        pass
    return False

