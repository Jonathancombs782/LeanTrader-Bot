from __future__ import annotations

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from traders_core.mt5_adapter import init as mt5_init
from traders_core.mt5_adapter import shutdown as mt5_shutdown
from traders_core.orchestration.jobs import load_cfg, research_once, signals_once
try:
    from observability.metrics import set_canary_up
except Exception:
    def set_canary_up():
        return None

app = FastAPI(title="LeanTraderBot Core API")


class CfgPath(BaseModel):
    path: str = "traders_core/configs/default.yaml"


@app.on_event("startup")
def _start():
    mt5_init()
    try:
        set_canary_up()
    except Exception:
        pass


@app.on_event("shutdown")
def _stop():
    mt5_shutdown()


@app.post("/research/run")
def research(payload: CfgPath):
    cfg = load_cfg(payload.path)
    return research_once(cfg)


@app.post("/signals/run")
def signals(payload: CfgPath):
    cfg = load_cfg(payload.path)
    return signals_once(cfg)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
