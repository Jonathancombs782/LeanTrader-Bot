# utils_runtime.py
import json, time, pathlib, platform, datetime as dt

RUNTIME = pathlib.Path("runtime"); RUNTIME.mkdir(exist_ok=True)
KILL = RUNTIME / "kill.flag"
HEART = RUNTIME / "heartbeat.json"

def should_stop() -> bool:
    return KILL.exists()

def write_heartbeat(state: dict):
    state = {
        **state,
        "ts": int(time.time()),
        "iso": dt.datetime.utcnow().isoformat() + "Z",
        "host": platform.node(),
    }
    HEART.write_text(json.dumps(state, indent=2), encoding="utf-8")
