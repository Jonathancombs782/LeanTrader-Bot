from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional


class _KV:
    """Small Redis-like wrapper. Falls back to in-memory when redis is unavailable.

    Methods: set(name, value, ex=None, nx=False, xx=False), get(name), ttl(name), delete(name)
    """

    def __init__(self, url: Optional[str] = None):
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._use_mem = True
        self._r = None
        if url:
            try:
                import redis  # type: ignore

                self._r = redis.from_url(url, decode_responses=True)
                self._use_mem = False
            except Exception:
                self._use_mem = True

    def _gc(self) -> None:
        now = time.time()
        for k in list(self._mem.keys()):
            exp = self._mem[k].get("exp")
            if exp and now >= exp:
                del self._mem[k]

    def set(self, name: str, value: str, ex: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        if not self._use_mem:
            try:
                res = self._r.set(name, value, ex=ex, nx=nx, xx=xx)  # type: ignore
                return bool(res)
            except Exception:
                pass
        # mem
        self._gc()
        if nx and name in self._mem:
            return False
        if xx and name not in self._mem:
            return False
        exp = time.time() + ex if ex else None
        self._mem[name] = {"val": value, "exp": exp}
        return True

    def get(self, name: str) -> Optional[str]:
        if not self._use_mem:
            try:
                return self._r.get(name)  # type: ignore
            except Exception:
                pass
        self._gc()
        rec = self._mem.get(name)
        return None if rec is None else str(rec.get("val"))

    def ttl(self, name: str) -> int:
        if not self._use_mem:
            try:
                t = self._r.ttl(name)  # type: ignore
                return int(t) if t is not None else -2
            except Exception:
                pass
        self._gc()
        rec = self._mem.get(name)
        if rec is None:
            return -2
        exp = rec.get("exp")
        if not exp:
            return -1
        return max(0, int(exp - time.time()))

    def delete(self, name: str) -> None:
        if not self._use_mem:
            try:
                self._r.delete(name)  # type: ignore
                return
            except Exception:
                pass
        self._mem.pop(name, None)


try:
    from prometheus_client import Gauge, CollectorRegistry, generate_latest  # type: ignore

    SUP_LEADER = Gauge("supervisor_leader", "1 if this node is leader", ["node", "namespace"])  # noqa: N816
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_: Any, **__: Any) -> "_Noop":
            return self

        def set(self, *_: Any, **__: Any) -> None:
            pass

    def generate_latest(*_args: Any, **_kwargs: Any) -> bytes:  # type: ignore
        return b""

    SUP_LEADER = _Noop()  # type: ignore


class Supervisor:
    def __init__(self, *, node_id: str, namespace: str = "lt", ttl_sec: int = 15, redis_url: Optional[str] = None):
        self.node_id = node_id
        self.ns = namespace
        self.ttl = max(5, int(ttl_sec))
        self.kv = _KV(redis_url)
        self.leader_key = f"{self.ns}:leader"
        self.state_key = f"{self.ns}:state"
        self.is_leader = False
        self.last_state: Dict[str, Any] = {}
        self._stop = threading.Event()
        self._http_thread: Optional[threading.Thread] = None
        self._http_ready = False

    # ---------- HTTP health server ----------
    def _start_http(self, host: str = "0.0.0.0", port: int = 8081) -> None:
        sup = self

        class Handler(BaseHTTPRequestHandler):  # type: ignore
            def log_message(self, fmt: str, *args: Any) -> None:
                return  # quiet

            def _resp(self, code: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/healthz"):
                    self._resp(200, {"ok": True, "leader": sup.is_leader})
                elif self.path.startswith("/readyz"):
                    ready = sup._http_ready
                    self._resp(200 if ready else 503, {"ready": ready, "leader": sup.is_leader})
                elif self.path.startswith("/metrics"):
                    # Expose Prometheus metrics
                    payload = generate_latest()  # type: ignore[arg-type]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self._resp(404, {"error": "not found"})

        def _serve():
            try:
                httpd = HTTPServer((host, port), Handler)
                sup._http_ready = True
                httpd.serve_forever()
            except Exception:
                sup._http_ready = False

        self._http_thread = threading.Thread(target=_serve, daemon=True)
        self._http_thread.start()

    # ---------- leadership ----------
    def _try_acquire(self) -> bool:
        return bool(self.kv.set(self.leader_key, self.node_id, ex=self.ttl, nx=True))

    def _heartbeat(self) -> bool:
        return bool(self.kv.set(self.leader_key, self.node_id, ex=self.ttl, xx=True))

    def _leader_loop(self, jobs: Optional[list[list[str]]] = None) -> None:
        # Start jobs (best-effort)
        procs: list[Any] = []
        import subprocess

        if jobs:
            for cmd in jobs:
                try:
                    procs.append(subprocess.Popen(cmd))  # noqa: S603
                except Exception:
                    continue
        try:
            while not self._stop.is_set():
                if not self._heartbeat():
                    # lost leadership
                    break
                # optionally persist state snapshot
                st = {"node": self.node_id, "ts": int(time.time()), "jobs": len(procs)}
                try:
                    self.kv.set(self.state_key, json.dumps(st), ex=self.ttl * 3)
                except Exception:
                    pass
                try:
                    SUP_LEADER.labels(node=self.node_id, namespace=self.ns).set(1)
                except Exception:
                    pass
                time.sleep(self.ttl / 3.0)
        finally:
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass

    def _standby_loop(self) -> None:
        # passive loop waiting for opportunity to promote
        while not self._stop.is_set():
            val = self.kv.get(self.leader_key)
            if val is None:
                if self._try_acquire():
                    self.is_leader = True
                    return
            try:
                SUP_LEADER.labels(node=self.node_id, namespace=self.ns).set(0)
            except Exception:
                pass
            time.sleep(max(1.0, self.ttl / 4.0))

    def run(self, role: str = "standby", jobs: Optional[list[list[str]]] = None, http_port: int = 8081) -> None:
        self._start_http(port=http_port)
        if role == "leader":
            if not self._try_acquire():
                role = "standby"
        try:
            while not self._stop.is_set():
                if role == "standby":
                    self.is_leader = False
                    self._standby_loop()
                    role = "leader"
                    continue
                # leader role
                self.is_leader = True
                # attempt to load last state for warm resume
                try:
                    st = self.kv.get(self.state_key)
                    self.last_state = json.loads(st) if st else {}
                except Exception:
                    self.last_state = {}
                self._leader_loop(jobs)
                role = "standby"
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()


def _default_jobs() -> list[list[str]]:
    jobs: list[list[str]] = []
    # Always run scheduler in leader
    jobs.append([os.environ.get("PYTHON", os.sys.executable), "tools/scheduler.py"])
    # Start mempool daemon by default; allow disabling via env
    if os.getenv("MEMPOOL_DISABLED", "false").lower() not in ("1", "true", "yes", "on"):
        jobs.append([os.environ.get("PYTHON", os.sys.executable), "tools/mempool_daemon.py"])
    # Optional: metrics exporter
    if os.getenv("METRICS_EXPORTER_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
        jobs.append([os.environ.get("PYTHON", os.sys.executable), "tools/metrics_http.py"])
    return jobs


def main() -> int:
    p = argparse.ArgumentParser(description="LeanTrader process supervisor with leader election")
    p.add_argument("--role", choices=["leader", "standby"], default=os.getenv("ROLE", "standby"))
    p.add_argument("--namespace", default=os.getenv("SUP_NS", "lt"))
    p.add_argument("--node-id", default=os.getenv("NODE_ID", ""))
    p.add_argument("--ttl", type=int, default=int(os.getenv("SUP_TTL", "15")))
    p.add_argument("--redis", default=os.getenv("REDIS_URL", ""))
    p.add_argument("--http-port", type=int, default=int(os.getenv("SUP_HTTP_PORT", "8081")))
    args = p.parse_args()

    node_id = args.node_id or (os.getenv("HOSTNAME") or f"node-{int(time.time())}")
    sup = Supervisor(node_id=node_id, namespace=args.namespace, ttl_sec=args.ttl, redis_url=(args.redis or None))
    sup.run(role=args.role, jobs=_default_jobs(), http_port=args.http_port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
