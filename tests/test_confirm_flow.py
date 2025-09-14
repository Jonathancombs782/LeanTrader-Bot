import json
import os
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

import runtime.webhook_server as ws
from tools import user_pins

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def test_confirm_execute_roundtrip(tmp_path):
    os.environ.setdefault("PREMIUM_USERS", TEST_UID)
    # ensure ALLOW_DIRECT_EXEC disabled for normal flow test
    os.environ.setdefault("ALLOW_DIRECT_EXEC", "0")

    signal_id = f"pytest-sig-{int(time.time())}"
    write_test_signal(signal_id)

    pin = user_pins.generate_pin(TEST_UID)

    client = TestClient(ws.app)

    # post confirm callback
    payload = {"callback_query": {"id": "cb-py", "from": {"id": int(TEST_UID)}, "data": f"confirm:{signal_id}"}}
    r = client.post("/telegram_webhook", json=payload)
    assert r.status_code == 200

    # now attempt execute via normal /execute flow
    r2 = client.post("/execute", json={"user_id": TEST_UID, "text": f"/execute {pin}"})
    # either succeed or return execution disabled error depending on ENABLE_LIVE; at least should not error on missing pending signal
    assert r2.status_code == 200
    j = r2.json()
    # either success or pin/disabled, but not 'no pending signal to execute'
    assert j.get("error") != "no pending signal to execute"
