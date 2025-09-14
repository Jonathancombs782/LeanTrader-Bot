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


def _is_premium(chat_id: str = None) -> bool:
    """Return True if the given chat_id is allowed premium (has access to reply_markup).

    If the premium list is empty, default to True for local/dev convenience.
    """
    try:
        return _chat_ok(chat_id)
    except Exception:
        return False


def send_message(text: str, chat_id: str = None, reply_markup: dict = None) -> bool:
    cid = chat_id or CHAT_ID
    if not _chat_ok(cid):
        return False
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    if reply_markup and _is_premium(cid):
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
    if reply_markup and _is_premium(cid):
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(_api("sendPhoto"), data=data, files=files, timeout=30)
        return r.ok
    except Exception:
        return False


def _build_buttons(signal_id: str, include_simulate: bool = True, include_subscribe: bool = True) -> list:
    # Prefer tg_utils clean builder when available
    try:
        from tg_utils import build_confirm_buttons_clean as _build

        return _build(signal_id, include_simulate=include_simulate, include_subscribe=include_subscribe)
    except Exception:
        # Basic inline keyboard fallback
        btns = [
            [
                {"text": "✓ Execute", "callback_data": f"confirm:{signal_id}"},
                {"text": "✕ Cancel", "callback_data": f"cancel:{signal_id}"},
            ]
        ]
        if include_simulate:
            btns.append([{"text": "🧪 Simulate", "callback_data": f"simulate:{signal_id}"}])
        if include_subscribe:
            btns.append([{"text": "🔗 Subscribe / Link", "callback_data": f"subscribe:{signal_id}"}])
        return btns


def publish_signal(
    symbol: str,
    side: str,
    confidence: float,
    rationale: list[str],
    chart_path: str,
    signal_id: str,
    qty_presets: list[str] | None = None,
    chat_id: str | None = None,
) -> bool:
    """Send a rich signal to Telegram.

    Premium chats receive inline buttons that trigger confirm/execute flow.
    """
    cid = chat_id or CHAT_ID
    if not enabled():
        return False
    # Build caption with rationale bullets
    lines = [
        f"*{symbol}*  _{side.upper()}_  CONF: {confidence:.2f}",
        "",
        "*Why this trade?*",
    ]
    for r in list(rationale)[:6]:
        lines.append(f"- {r}")
    caption = "\n".join(lines)
    # Build buttons
    reply = None
    if _is_premium(cid):
        reply = {"inline_keyboard": _build_buttons(signal_id)}
    return send_photo(chart_path, caption=caption, chat_id=cid, reply_markup=reply)
