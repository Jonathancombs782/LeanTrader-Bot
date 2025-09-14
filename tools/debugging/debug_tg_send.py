#!/usr/bin/env python
"""Opt-in debug helper: find the most recent chart and call tg_utils.debug_send_photo.

Only runs when TELEGRAM_DEBUG env var is set to a truthy value.
"""
import os

if os.getenv("TELEGRAM_DEBUG", "").strip().lower() not in ("1", "true", "yes"):
    print("debug_tg_send: TELEGRAM_DEBUG not set; exiting")
    raise SystemExit(0)

import glob
import json
import sys
from pathlib import Path

print("[debug_tg_send] TELEGRAM_BOT_TOKEN present:", "TELEGRAM_BOT_TOKEN" in os.environ)
print("[debug_tg_send] TELEGRAM_CHAT_ID present:", "TELEGRAM_CHAT_ID" in os.environ)

charts = sorted(
    glob.glob(str(Path(__file__).resolve().parent.parent / "runtime" / "charts" / "*.png")),
    key=os.path.getmtime,
    reverse=True,
)
if not charts:
    print("[debug_tg_send] NO_CHARTS found under runtime/charts")
    sys.exit(2)

chart = charts[0]
print("[debug_tg_send] Using chart:", chart)

try:
    from tg_utils import debug_send_photo
except Exception as e:
    print("[debug_tg_send] failed to import tg_utils:", e)
    sys.exit(3)

try:
    ok, details = debug_send_photo("Debug upload from repo", chart)
    print("[debug_tg_send] OK:", ok)
    try:
        print("[debug_tg_send] DETAILS:", json.dumps(details, default=str))
    except Exception:
        print("[debug_tg_send] DETAILS (repr):", repr(details))
except Exception as e:
    print("[debug_tg_send] Exception while calling debug_send_photo:", repr(e))
    sys.exit(4)
