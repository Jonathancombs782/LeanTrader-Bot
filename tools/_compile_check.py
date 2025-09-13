import traceback
from pathlib import Path

FILES = [
    "auto_pilot.py",
    "news_adapter.py",
    "run_live.py",
    "run_live_fx.py",
    "mobile_app.py",
    "tg_heartbeat.py",
    "run_live_meme.py",
]

ROOT = Path(__file__).resolve().parents[1]
for f in FILES:
    try:
        p = ROOT / f
        if not p.exists():
            continue
        print("---", p)
        src = p.read_text(encoding="utf-8")
        compile(src, str(p), "exec")
        print("OK")
    except Exception:
        traceback.print_exc()
