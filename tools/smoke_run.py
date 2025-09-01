import json
import os

os.environ["EXCHANGE_ID"] = os.environ.get("EXCHANGE_ID", "paper")
from smoke_ultra import quick_smoke  # noqa: E402
os.environ["LIVE_AUTOTRADE"] = "false"
os.environ["THINK_FILL_MISSING_PRICE"] = "true"

from brain_loop import think_once

print("SMOKE: calling think_once()")
try:
    res = think_once()
except Exception as e:
    print("SMOKE: think_once raised", type(e).__name__, e)
    raise
out_path = os.path.join("runtime", "smoke_result.json")
os.makedirs("runtime", exist_ok=True)
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=2, default=str)

print(f"SMOKE_FINISHED wrote {len(res)} signals to {out_path}")
