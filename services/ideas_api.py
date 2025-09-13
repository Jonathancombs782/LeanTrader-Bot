from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request


APP = FastAPI(title="Ideas Interactive Endpoint")
OUT = Path(os.getenv("IDEAS_APPROVALS_FILE", "runtime/ideas_approvals.json"))


def _append(obj: Dict[str, Any]) -> None:
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if OUT.exists():
            data = json.loads(OUT.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        data.append(obj)
        OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@APP.post("/slack/ideas/interactive")
async def slack_interactive(req: Request):
    try:
        payload = await req.json()
    except Exception:
        # Slack may send application/x-www-form-urlencoded with 'payload' field
        form = await req.form()
        payload = json.loads(form.get("payload", "{}"))
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    _append(event)
    return {"ok": True}


# Uvicorn: uvicorn services.ideas_api:APP --port 8085

