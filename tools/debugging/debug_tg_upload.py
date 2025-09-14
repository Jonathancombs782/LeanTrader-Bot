"""Opt-in debug upload helper.

Set TELEGRAM_DEBUG=1 to enable. This avoids accidental posting to the real bot.
"""

import os

if os.getenv("TELEGRAM_DEBUG", "").strip().lower() not in ("1", "true", "yes"):
    print("debug_tg_upload: TELEGRAM_DEBUG not set; exiting")
    raise SystemExit(0)

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
charts = list((ROOT / "runtime" / "charts").glob("*.png"))
if not charts:
    print("no charts found")
    raise SystemExit(1)
charts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
chart = charts[0]
print("testing upload of:", chart)

try:
    from tg_utils import debug_send_photo
except Exception as e:
    print("failed to import tg_utils:", e)
    raise

ok, details = debug_send_photo(f"Debug upload {chart.name}", str(chart))
print("ok:", ok)
print("details:", details)
