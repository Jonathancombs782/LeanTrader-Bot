import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# import depends on repo root path insertion
from fastapi.testclient import TestClient  # noqa: E402

import runtime.webhook_server as ws  # noqa: E402

TEST_UID = "5329503447"
client = TestClient(ws.app)
signal_id = "dbg-sig-12345"
payload = {"callback_query": {"id": "cb-dbg", "from": {"id": int(TEST_UID)}, "data": f"confirm:{signal_id}"}}
print("posting webhook")
resp = client.post("/telegram_webhook", json=payload)
print("webhook status", resp.status_code, resp.text)
print("CONFIRM_STORE after webhook:", ws._CONFIRM_STORE)

# now post execute
pin = "0000"
exec_resp = client.post("/execute", json={"user_id": TEST_UID, "text": f"/execute {pin}"})
print("execute status", exec_resp.status_code, exec_resp.text)
