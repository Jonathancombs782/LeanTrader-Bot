# tg_utils.py
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Optional  # noqa: F401  # intentionally kept

import requests

# Ensure local .env is loaded for CLI runs that don't import trader_core
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# --- ENV ---
ENABLED = os.getenv("TELEGRAM_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TIMEOUT_S = int(os.getenv("TELEGRAM_TIMEOUT", "10"))
RETRY = int(os.getenv("TELEGRAM_RETRY", "1"))  # quick retry count (0/1/2)

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _enabled() -> bool:
    # Allow sending messages to arbitrary chat_id (e.g. callback_query.from.id)
    # as long as the bot token is present and TELEGRAM_ENABLED is truthy.
    # CHAT_ID is still used as a convenience default for broadcast messages,
    # but it should not block direct replies to users.
    return ENABLED and bool(BOT_TOKEN)


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
            if r.status_code == 200 and (
                r.json().get("ok", False) if r.headers.get("content-type", "").startswith("application/json") else True
            ):
                return True
        except Exception:
            pass
        time.sleep(0.4)  # tiny backoff
    return False


# -------- Public helpers --------
def send_signal(title: str, lines: List[str]) -> bool:
    """Legacy-compatible signal sender; prefers premium style if enabled.

    Use PRETTY_SIGNALS env var to enable the upgraded look (`true`|`1`).
    """
    if not _enabled():
        return False
    pretty = os.getenv("PRETTY_SIGNALS", "true").strip().lower() in ("1", "true", "yes")
    if pretty:
        return send_premium_signal(title, lines)
    # fallback basic formatting
    text = f"*{_md(title)}*\n" + "\n".join(_md(line) for line in lines)
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    return _post_json("sendMessage", payload)


def send_premium_signal(title: str, lines: List[str]) -> bool:
    """Send an upgraded, clean-looking MarkdownV2 message with sections and code helpers.

    This deliberately uses a strict set of MarkdownV2 escapes. Telegram requires
    escaping of several characters; we keep the message compact and legible.
    """
    if not _enabled():
        return False
    # Compose sections: header, boxed price line, bullets, quick commands, footer
    header = f"*{_md(title)}*\n"
    # find the header price line and separate it
    body_lines = list(lines)
    boxed = body_lines[0] if body_lines else ""
    rest = body_lines[1:]

    # Boxed price line using code block
    boxed_block = f"`{_md(boxed)}`\n"

    # construct bullets and rest, escaping markdown
    bullets = "\n".join(_md(s) for s in rest)

    text = header + boxed_block
    if bullets:
        text += "\n" + bullets

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
    # If photo_url is a local file path, upload as multipart/form-data
    try:
        if os.path.exists(photo_url):
            url = f"{API_BASE}/sendPhoto"
            files = {"photo": open(photo_url, "rb")}
            data = {"chat_id": CHAT_ID, "caption": _md(caption), "parse_mode": "Markdown"}
            tries = max(1, RETRY + 1)
            last_resp = None
            for _ in range(tries):
                try:
                    r = requests.post(url, data=data, files=files, timeout=TIMEOUT_S)
                    last_resp = r
                    if r.status_code == 200:
                        return True
                except Exception as e:
                    last_resp = e
                    time.sleep(0.3)  # tiny backoff
            # log last response for debugging
            try:
                # ensure runtime logs dir
                logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                logdir.mkdir(parents=True, exist_ok=True)
                debug_file = logdir / "tg_send_debug.log"
                entry = {
                    "ts": int(time.time()),
                    "event": "send_photo_upload_failed",
                    "status_code": getattr(last_resp, "status_code", None),
                    "text": getattr(last_resp, "text", str(last_resp)),
                    "photo": str(photo_url),
                }
                with open(debug_file, "a", encoding="utf-8") as df:
                    df.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                # fallback to printing
                print("[tg_utils] send_photo upload failed: unknown error")
            # fallback to public URL if configured
            public_base = os.getenv("CHART_PUBLIC_URL", "").strip()
            if public_base:
                # assume public_base ends with / and append relative path
                import urllib.parse as _up

                rel = _up.quote(os.path.basename(photo_url))
                photo_remote = public_base.rstrip("/") + "/" + rel
                payload = {"chat_id": CHAT_ID, "photo": photo_remote, "caption": _md(caption), "parse_mode": "Markdown"}
                return _post_json("sendPhoto", payload)
            return False
    except Exception:
        # fallback to URL-based send
        payload = {
            "chat_id": CHAT_ID,
            "photo": photo_url,
            "caption": _md(caption),
            "parse_mode": "Markdown",
        }
        return _post_json("sendPhoto", payload)


def debug_send_photo(caption: str, photo_url: str):
    """Debug helper: attempt to upload and return (ok: bool, details: str).

    Returns a tuple (ok, details) where details is the response text or exception.
    """
    if not _enabled():
        return False, "telegram disabled or missing token/chat"
    try:
        # Prefer multipart upload when the path exists locally.
        if os.path.exists(photo_url):
            url = f"{API_BASE}/sendPhoto"
            files = {"photo": open(photo_url, "rb")}
            data = {"chat_id": CHAT_ID, "caption": _md(caption), "parse_mode": "Markdown"}
            try:
                r = requests.post(url, data=data, files=files, timeout=TIMEOUT_S)
                ok = r.status_code == 200
                details = getattr(r, "text", "")
                # write debug log
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "debug_send_photo",
                        "ok": ok,
                        "status_code": r.status_code,
                        "text": details,
                        "photo": str(photo_url),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return ok, details
            except Exception as e:
                # log exception
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "debug_send_photo_exception",
                        "error": str(e),
                        "photo": str(photo_url),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return False, str(e)
        else:
            # If the provided photo_url looks like a local Windows path (contains backslashes or a drive letter),
            # avoid sending it as an HTTP URL to Telegram (Telegram will reject malformed local paths).
            p = str(photo_url)
            looks_like_windows_path = ("\\" in p) or (":" in p and p[1:3] == ":\\")
            if looks_like_windows_path:
                # log a helpful debug entry
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "debug_send_photo_local_path_missing",
                        "photo": str(photo_url),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return False, "local file not found"

            # treat as a remote URL and send via JSON payload
            payload = {"chat_id": CHAT_ID, "photo": photo_url, "caption": _md(caption), "parse_mode": "Markdown"}
            try:
                r = requests.post(f"{API_BASE}/sendPhoto", json=payload, timeout=TIMEOUT_S)
                ok = r.status_code == 200
                details = getattr(r, "text", "")
                # write debug log for URL sends too
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "debug_send_photo_url",
                        "ok": ok,
                        "status_code": r.status_code,
                        "text": details,
                        "photo": str(photo_url),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return ok, details
            except Exception as _e:
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "debug_send_photo_url_exception",
                        "error": str(_e),
                        "photo": str(photo_url),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return False, str(_e)
    except Exception as _e:
        return False, str(_e)


def send_photo_rich(caption: str, photo_path: str, buttons: list) -> bool:
    """Higher-level photo send that wraps send_photo_with_buttons with extra
    retries, explicit debug logging, and URL fallback. Returns True on success.
    """
    # attempt primary send via send_photo_with_buttons
    try:
        ok = send_photo_with_buttons(caption, photo_path, buttons)
        if ok:
            return True
    except Exception:
        ok = False

    # fallback: call debug_send_photo to capture low-level response and log it
    try:
        dbg_ok, dbg_details = debug_send_photo(caption, photo_path)
        try:
            logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            debug_file = logdir / "tg_send_debug.log"
            entry = {
                "ts": int(time.time()),
                "event": "send_photo_rich_debug",
                "ok": dbg_ok,
                "details": str(dbg_details),
                "photo": str(photo_path),
            }
            with open(debug_file, "a", encoding="utf-8") as df:
                df.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return bool(dbg_ok)
    except Exception:
        return False


def heartbeat(title: str, lines: List[str]) -> bool:
    """Small wrapper for periodic status messages."""
    return send_signal(title, lines)


def send_photo_with_buttons(caption: str, photo_path: str, buttons: list) -> bool:
    """Send a photo with inline keyboard buttons.

    buttons: list of rows, each row a list of {"text":..., "url":...}
    """
    if not _enabled():
        return False
    url = f"{API_BASE}/sendPhoto"
    # if photo_path is a local file, upload multipart and include reply_markup
    try:
        if os.path.exists(photo_path):
            files = {"photo": open(photo_path, "rb")}
            # buttons may contain either 'url' or 'callback_data' keys per button
            reply = {"inline_keyboard": buttons}
            data = {
                "chat_id": CHAT_ID,
                "caption": _md(caption),
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(reply),
            }
            try:
                r = requests.post(url, data=data, files=files, timeout=TIMEOUT_S)
            except Exception as e:
                # write debug log
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "send_photo_exception",
                        "error": str(e),
                        "photo": str(photo_path),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                # try fallback to public URL if configured
                public_base = os.getenv("CHART_PUBLIC_URL", "").strip()
                if public_base:
                    import urllib.parse as _up

                    rel = _up.quote(os.path.basename(photo_path))
                    photo_remote = public_base.rstrip("/") + "/" + rel
                    payload = {
                        "chat_id": CHAT_ID,
                        "photo": photo_remote,
                        "caption": _md(caption),
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(reply),
                    }
                    return _post_json("sendPhoto", payload)
                return False

            # if response not OK, try resizing image and retry once to avoid upload size issues
            if getattr(r, "status_code", None) != 200:
                try:
                    from PIL import Image

                    img = Image.open(photo_path)
                    img.thumbnail((1200, 1200))
                    tmp = Path(photo_path).with_suffix(".small.png")
                    img.save(tmp, format="PNG")
                    files = {"photo": open(str(tmp), "rb")}
                    r2 = requests.post(url, data=data, files=files, timeout=TIMEOUT_S)
                    if getattr(r2, "status_code", None) == 200:
                        try:
                            tmp.unlink()
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass

            # if response not OK, log details and try fallback
            if getattr(r, "status_code", None) != 200:
                try:
                    logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
                    logdir.mkdir(parents=True, exist_ok=True)
                    debug_file = logdir / "tg_send_debug.log"
                    entry = {
                        "ts": int(time.time()),
                        "event": "send_photo_failed",
                        "status_code": r.status_code,
                        "text": getattr(r, "text", None),
                        "photo": str(photo_path),
                    }
                    with open(debug_file, "a", encoding="utf-8") as df:
                        df.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                # fallback to public URL if configured
                public_base = os.getenv("CHART_PUBLIC_URL", "").strip()
                if public_base:
                    import urllib.parse as _up

                    rel = _up.quote(os.path.basename(photo_path))
                    photo_remote = public_base.rstrip("/") + "/" + rel
                    payload = {
                        "chat_id": CHAT_ID,
                        "photo": photo_remote,
                        "caption": _md(caption),
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(reply),
                    }
                    return _post_json("sendPhoto", payload)
                return False
            return True
        else:
            # send by URL
            # when sending by URL we post JSON via the API helper
            reply = {"inline_keyboard": buttons}
            payload = {
                "chat_id": CHAT_ID,
                "photo": photo_path,
                "caption": _md(caption),
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(reply),
            }
            return _post_json("sendPhoto", payload)
    except Exception:
        return False


def build_confirm_buttons(signal_id: str, include_simulate: bool = True, include_subscribe: bool = False) -> list:
    """Return a standard confirm/cancel inline keyboard for a signal id.

    Options:
    - include_simulate: adds a Simulate button on its own row
    - include_subscribe: adds a Subscribe/Login button to help users link their broker

    callback_data values are simple strings the webhook server will parse: e.g. "confirm:<id>" or "subscribe:<id>".
    """
    # Primary action row: Execute + Cancel for clear alignment
    row1 = [
        {"text": "✅ Execute", "callback_data": f"confirm:{signal_id}"},
        {"text": "❌ Cancel", "callback_data": f"cancel:{signal_id}"},
    ]
    rows = [row1]

    # Secondary actions: Simulate and Subscribe (if requested) on a second row for neat alignment
    secondary = []
    if include_simulate:
        secondary.append({"text": "🧪 Simulate", "callback_data": f"simulate:{signal_id}"})
    if include_subscribe:
        # subscribe callback will trigger login/link flow
        secondary.append({"text": "🔗 Subscribe / Link Broker", "callback_data": f"subscribe:{signal_id}"})
    if secondary:
        rows.append(secondary)
    return rows


def send_message_with_buttons(text: str, buttons: list) -> bool:
    """Send a text message with inline keyboard buttons (callback_data or url allowed)."""
    if not _enabled():
        return False
    payload = {
        "chat_id": CHAT_ID,
        "text": _md(text),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps({"inline_keyboard": buttons}),
    }
    ok = _post_json("sendMessage", payload)
    if not ok:
        try:
            logdir = Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            debug_file = logdir / "tg_send_debug.log"
            entry = {"ts": int(time.time()), "event": "send_message_failed", "text": text, "buttons": buttons}
            with open(debug_file, "a", encoding="utf-8") as df:
                df.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return ok


# Clean, ASCII-safe confirm buttons builder for integrations
def build_confirm_buttons_clean(signal_id: str, include_simulate: bool = True, include_subscribe: bool = False) -> list:
    """Return InlineKeyboard button rows for confirm/cancel (+optional simulate/subscribe).

    Uses readable labels with optional emoji unless TELEGRAM_ASCII=true.
    """
    ascii_only = os.getenv("TELEGRAM_ASCII", "false").strip().lower() in ("1", "true", "yes")
    ok_lbl = "Execute" if ascii_only else "\u2713 Execute"
    cancel_lbl = "Cancel" if ascii_only else "\u2715 Cancel"
    sim_lbl = "Simulate" if ascii_only else "\U0001f9ea Simulate"
    sub_lbl = "Subscribe / Link" if ascii_only else "\U0001f517 Subscribe / Link"

    rows = [
        [
            {"text": ok_lbl, "callback_data": f"confirm:{signal_id}"},
            {"text": cancel_lbl, "callback_data": f"cancel:{signal_id}"},
        ]
    ]
    secondary = []
    if include_simulate:
        secondary.append({"text": sim_lbl, "callback_data": f"simulate:{signal_id}"})
    if include_subscribe:
        secondary.append({"text": sub_lbl, "callback_data": f"subscribe:{signal_id}"})
    if secondary:
        rows.append(secondary)
    return rows
