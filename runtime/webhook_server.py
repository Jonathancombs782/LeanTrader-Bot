"""Telegram webhook server (minimal restoration, Nov 11, 2026).

This module was referenced by `tests/test_confirm_flow.py` (and old
Telegram tooling) but never committed, so its test skipped. This is a
minimal restoration of exactly the surface the test exercises — not a
rebuild of the old bot:

- POST /telegram_webhook — handles `confirm:<signal_id>` callback
  queries: looks the signal up in `runtime/signals-*.ndjson` and records
  it as pending for that user.
- POST /execute — `{"user_id", "text": "/execute <pin>"}`: verifies the
  PIN via `tools.user_pins`, requires a pending confirmed signal, and
  then REFUSES: live execution is disabled by design (paper-first).
  It returns `{"ok": false, "error": "execution disabled"}` — never a
  live order, never a fund movement.

Pending confirmations live in memory only (one process). A restart
loses them; re-confirm from Telegram. No keys, no accounts, no real
money: the paper brain (`paper/`) is the only trading path.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from tools import user_pins

RUNTIME_DIR = Path(__file__).resolve().parent

app = FastAPI(title="leantrader-webhook", version="0.1.0")

# user_id (str) -> confirmed signal dict. In-memory only; see docstring.
_pending: dict[str, dict] = {}


def _find_signal(signal_id: str) -> dict | None:
    """Look a signal up in runtime/signals-*.ndjson, newest file first."""
    for path in sorted(glob.glob(str(RUNTIME_DIR / "signals-*.ndjson")),
                       reverse=True):
        try:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                sig = json.loads(line)
                if str(sig.get("id")) == str(signal_id):
                    return sig
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _is_premium(user_id: str) -> bool:
    """PREMIUM_USERS (comma-separated) gates /execute when it is set."""
    allowed = os.environ.get("PREMIUM_USERS", "")
    if not allowed.strip():
        return True
    return str(user_id) in {u.strip() for u in allowed.split(",") if u.strip()}


def _live_execution_enabled() -> bool:
    """Live execution stays off unless both gates say otherwise."""
    return (os.environ.get("ENABLE_LIVE", "").lower() == "true"
            and os.environ.get("ALLOW_DIRECT_EXEC", "0") == "1")


@app.get("/")
def health() -> dict:
    return {"ok": True, "service": "webhook_server", "mode": "paper",
            "live_execution": False}


@app.post("/telegram_webhook")
def telegram_webhook(payload: dict) -> JSONResponse:
    cb = payload.get("callback_query") or {}
    data = str(cb.get("data") or "")
    user_id = str((cb.get("from") or {}).get("id", ""))
    if data.startswith("confirm:"):
        signal_id = data.split("confirm:", 1)[1]
        sig = _find_signal(signal_id)
        if sig is None:
            return JSONResponse({"ok": False, "error": "unknown signal",
                                 "signal_id": signal_id})
        _pending[user_id] = sig
        return JSONResponse({"ok": True, "confirmed": signal_id,
                             "user_id": user_id})
    if data.startswith("cancel:"):
        _pending.pop(user_id, None)
        return JSONResponse({"ok": True, "cancelled": True})
    return JSONResponse({"ok": True, "ignored": True})


@app.post("/execute")
def execute(payload: dict) -> JSONResponse:
    user_id = str(payload.get("user_id", ""))
    text = str(payload.get("text", "")).strip()
    parts = text.split()
    if len(parts) != 2 or parts[0] != "/execute":
        return JSONResponse({"ok": False,
                             "error": "usage: /execute <pin>"})
    if not _is_premium(user_id):
        return JSONResponse({"ok": False, "error": "user not premium"})
    if not user_pins.verify_pin(user_id, parts[1]):
        return JSONResponse({"ok": False, "error": "invalid pin"})
    sig = _pending.get(user_id)
    if sig is None:
        return JSONResponse({"ok": False,
                             "error": "no pending signal to execute"})
    if not _live_execution_enabled():
        # Paper-first: a confirmed signal is never executed live from
        # this webhook. The pending confirmation stands for inspection.
        return JSONResponse({"ok": False,
                             "error": "execution disabled",
                             "signal_id": str(sig.get("id"))})
    return JSONResponse({"ok": False,
                         "error": "execution disabled",
                         "signal_id": str(sig.get("id"))})
