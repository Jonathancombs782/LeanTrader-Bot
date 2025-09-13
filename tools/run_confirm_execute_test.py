"""Run an in-process confirm -> execute integration test against runtime.webhook_server.

Creates a test signal in runtime, generates a per-user PIN, posts a confirm callback, then
posts /execute with the PIN. Prints responses and shows tail of persistent logs.

This uses FastAPI TestClient so no external server is required.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

TEST_UID = "5329503447"


def write_test_signal(signal_id: str) -> None:
    pdir = ROOT / "runtime"
    pdir.mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y%m%d")
    f = pdir / f"signals-{day}.ndjson"
    sig = {
        "id": signal_id,
        "symbol": "TEST/FAKE",
        "side": "buy",
        "entry": 1.23,
        "qty": 0.01,
        "ts": int(time.time()),
        "confidence": 0.9,
    }
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sig, ensure_ascii=False) + "\n")


def tail(path: Path, n: int = 20) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return lines[-n:]
    except Exception:
        return []


def main():
    # ensure test user is treated as premium for the confirm flow
    os.environ.setdefault("PREMIUM_USERS", TEST_UID)
    # import webhook server after env var so PREMIUM_USERS is read correctly at import-time
    import runtime.webhook_server as ws
    from tools import user_pins

    signal_id = f"test-sig-{int(time.time())}"
    print("Writing test signal id=", signal_id)
    write_test_signal(signal_id)

    print("Generating PIN for user", TEST_UID)
    pin = user_pins.generate_pin(TEST_UID)
    print("PIN (one-time):", pin)

    client = TestClient(ws.app)

    # send confirm callback
    payload = {
        "callback_query": {
            "id": "cb-test-1",
            "from": {"id": int(TEST_UID)},
            "data": f"confirm:{signal_id}",
        }
    }
    print("Posting /telegram_webhook confirm payload...")
    r = client.post("/telegram_webhook", json=payload)
    print("webhook confirm response status", r.status_code, r.text)
    # debug: print in-memory confirm store
    try:
        print("_CONFIRM_STORE now:", ws._CONFIRM_STORE)
    except Exception as _e:
        print("failed to read _CONFIRM_STORE:", _e)

    # now call the test-only direct execute endpoint (bypass webhook pairing race)
    os.environ.setdefault("ALLOW_DIRECT_EXEC", "1")
    exec_body = {"user_id": TEST_UID, "pin": pin, "signal_id": signal_id}
    print("Posting /execute_direct with PIN and signal_id...")
    r2 = client.post("/execute_direct", json=exec_body)
    print("/execute_direct response:", r2.status_code, r2.json())

    # Also attempt the normal /execute flow which uses the in-memory _CONFIRM_STORE
    exec_body2 = {"user_id": TEST_UID, "text": f"/execute {pin}"}
    print("Posting /execute with PIN (normal flow)...")
    r3 = client.post("/execute", json=exec_body2)
    print("/execute response:", r3.status_code, r3.json())

    # show confirm_store and webhook events tail
    logdir = ROOT / "runtime" / "logs"
    print("confirm_store.ndjson tail:")
    for L in tail(logdir / "confirm_store.ndjson", 50):
        print(L)

    print("webhook_events.ndjson tail:")
    for L in tail(logdir / "webhook_events.ndjson", 200):
        print(L)

    print("Done.")


if __name__ == "__main__":
    main()
