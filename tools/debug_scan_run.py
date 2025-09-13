import json
import os  # noqa: F401  # intentionally kept
from types import SimpleNamespace

os.environ["EXCHANGE_ID"] = os.environ.get("EXCHANGE_ID", "paper")
os.environ["ENABLE_LIVE"] = "false"
os.environ["LIVE_AUTOTRADE"] = "false"
os.environ["THINK_FILL_MISSING_PRICE"] = os.environ.get("THINK_FILL_MISSING_PRICE", "true")

# signals_scanner imported after sys.path insert; keep noqa to acknowledge intentional placement
import signals_scanner  # noqa: E402

args = SimpleNamespace(
    tf=os.getenv("SCAN_TF", "5m"),
    top=int(os.getenv("TOP_N", "7")),
    limit=int(os.getenv("SCAN_LIMIT", "200")),
    repeat=0,
    publish=False,
)
res = signals_scanner.run_once(args)
print("RAW_SIGNALS_COUNT=", len(res))
print(json.dumps(res, indent=2, default=str))
os.makedirs("runtime", exist_ok=True)
with open(os.path.join("runtime", "raw_signals.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=2, default=str)
print("WROTE runtime/raw_signals.json")
