# Emulate test order: import ws first, then set env, then proceed
import sys
from pathlib import Path
import os
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The import below relies on the repo root being on sys.path. Kept after sys.path insert.
from fastapi.testclient import TestClient  # noqa: E402

import runtime.webhook_server as ws  # noqa: E402
from tools import user_pins  # noqa: E402

TEST_UID = "5329503447"
# set env after import
os.environ.setdefault("PREMIUM_USERS", TEST_UID)
os.environ.setdefault("ALLOW_DIRECT_EXEC", "0")

signal_id = f"pytest-sig-{int(time.time())}"
# write a test signal
pdir = ws.ROOT / "runtime"
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
    fh.write(__import__("json").dumps(sig, ensure_ascii=False) + "\n")

pin = user_pins.generate_pin(TEST_UID)
client = TestClient(ws.app)

payload = {"callback_query": {"id": "cb-py", "from": {"id": int(TEST_UID)}, "data": f"confirm:{signal_id}"}}
r = client.post("/telegram_webhook", json=payload)
print("webhook status", r.status_code, r.text)
print("CONFIRM_STORE after webhook:", ws._CONFIRM_STORE)

r2 = client.post("/execute", json={"user_id": TEST_UID, "text": f"/execute {pin}"})
print("execute status", r2.status_code, r2.text)
