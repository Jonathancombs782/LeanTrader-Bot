"""Minimal metrics HTTP server.

Serves Prometheus metrics at /metrics. Run:
    python -m observability.http_metrics --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse

try:
    from fastapi import FastAPI, Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # type: ignore
    import uvicorn  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(f"Required deps missing for metrics server: {e}")

from observability.metrics import set_canary_up

app = FastAPI(title="LeanTrader Metrics")


@app.on_event("startup")
def _on_start():
    set_canary_up()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=int(args.port))


if __name__ == "__main__":
    main()

