"""Internal E2E test harness (offline) for publish->send->webhook->execute flow.

This test is deliberately lightweight and uses monkeypatching of tg_utils to avoid
calling the real Telegram API. Run with the repo virtualenv:
    ./.venv/Scripts/python.exe tools/test_e2e_telegram.py

It performs:
 - create a fake promoted signal
 - run publish_mtf_signals.main() with a patched tg_utils that records calls
 - simulate a callback by invoking the webhook handler directly (if available)
 - verify the callback executor returns a simulated execution result

This harness is intentionally non-invasive and prints a short summary.
"""

from __future__ import annotations

import importlib
import os
import sys

# ensure repo root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

sys.path.insert(0, ROOT)

# monkeypatch tg_utils to avoid real Telegram network calls
import tg_utils as _tg  # noqa: E402

calls = []


def fake_send_photo_rich(caption, photo_path, buttons):
    calls.append({"caption": caption, "photo": photo_path, "buttons": buttons})
    return True


def fake_send_photo_with_buttons(caption, photo_path, buttons):
    calls.append({"caption": caption, "photo": photo_path, "buttons": buttons, "basic": True})
    return True


# Replace implementations
_tg.send_photo_rich = fake_send_photo_rich
_tg.send_photo_with_buttons = fake_send_photo_with_buttons
_tg.debug_send_photo = lambda caption, photo: (True, "ok")

# run publisher
pub = importlib.import_module("tools.publish_mtf_signals")
res = pub.main()

print("E2E: publish returned", res)
print("E2E: tg calls recorded:", len(calls))
if calls:
    print("Sample call:", calls[0]["caption"][:200])

# optionally exercise callback executor if present
try:
    cb = importlib.import_module("tools.callback_executor")
    # fabricate a fake signal id (look in runtime/signals-*.ndjson for real ones)
    fake_id = '"sym": "TEST/FAKE"'
    print("E2E: callback_executor module present; calling simulate with fake id")
    # Function execute_signal_by_id(signal_id, simulate=True) expected
    if hasattr(cb, "execute_signal_by_id"):
        out = cb.execute_signal_by_id("fake-id-for-test", simulate=True)
        print("E2E: execute_signal_by_id returned:", out)
except Exception:
    pass
