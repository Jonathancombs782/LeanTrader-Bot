from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def write_digest(notes_dir: str, symbol: str, body: str):
    Path(notes_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(notes_dir) / f"{ts}__{symbol}.md"
    with open(path, "a", encoding="utf-8") as f:
        f.write(body.strip() + "\n\n")
