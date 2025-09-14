import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Following imports rely on the repo root being on sys.path
from fastapi.testclient import TestClient  # noqa: E402

import runtime.webhook_server as ws  # noqa: E402


def run_once():
    test_uid = os.environ.get("TEST_UID", "5329503447")
    # ensure PREMIUM_USERS env is set
    os.environ["PREMIUM_USERS"] = test_uid

    client = TestClient(ws.app)

    sig = f"dbg-run-{int(time.time())}"
    payload = {"callback_query": {"id": "cb-dbg", "from": {"id": int(test_uid)}, "data": f"confirm:{sig}"}}
    r = client.post("/telegram_webhook", json=payload)
    print("webhook status", r.status_code, r.json())

    # inspect in-memory store
    print("_CONFIRM_STORE after webhook:", ws._CONFIRM_STORE.get(str(test_uid)))

    # read last lines of confirm_store.ndjson
    logp = ROOT / "runtime" / "logs" / "confirm_store.ndjson"
    if logp.exists():
        with open(logp, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        print("last 10 lines of confirm_store.ndjson:\n", "".join(lines[-10:]))
    else:
        print("confirm_store.ndjson not found")

    # call execute endpoint with a bogus pin (we're only testing presence)
    r2 = client.post("/execute", json={"user_id": test_uid, "text": "/execute 0000"})
    print("/execute status", r2.status_code, r2.json())


if __name__ == "__main__":
    run_once()
