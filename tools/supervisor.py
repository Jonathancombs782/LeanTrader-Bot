"""Simple supervisor to run demo and news workers and keep them alive.

Runs in the repository virtualenv (sys.executable). It spawns two subprocesses:
 - tools.continuous_demo (long-run)
 - tools.web_crawler

Behavior:
 - restarts a child if it exits
 - logs stdout/stderr to runtime/logs/<name>.log
 - writes a PID file runtime/supervisor.pid
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
LOGDIR = RUNTIME / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOGDIR / "supervisor.log"), logging.StreamHandler()],
)

CHILDREN = [
    {
        "name": "continuous_demo",
        # run a long loop (minutes)
        # use -m to run as a module so top-level imports resolve correctly from project root
        "cmd": [sys.executable, "-u", "-m", "tools.continuous_demo", "1440"],
    },
    {
        "name": "web_crawler",
        "cmd": [sys.executable, "-u", "-m", "tools.web_crawler"],
    },
]

PROCS = {}
STOP = False


def _start(child):
    name = child["name"]
    logfile = LOGDIR / f"{name}.log"
    errfile = LOGDIR / f"{name}.err"
    logging.info(f"starting {name}, log={logfile}")
    f_out = open(logfile, "a", buffering=1, encoding="utf-8")
    f_err = open(errfile, "a", buffering=1, encoding="utf-8")
    try:
        p = subprocess.Popen(child["cmd"], cwd=str(ROOT), stdout=f_out, stderr=f_err, stdin=subprocess.DEVNULL)
        PROCS[name] = (p, f_out, f_err)
        logging.info(f"started {name} pid={p.pid}")
    except Exception as e:
        logging.exception(f"failed to start {name}: {e}")


def _stop_all():
    logging.info("stopping children")
    for name, (p, out, err) in list(PROCS.items()):
        try:
            logging.info(f"terminating {name} pid={p.pid}")
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
            out.close()
            err.close()
        except Exception:
            logging.exception("error stopping process")
    PROCS.clear()


def _write_pid():
    try:
        pidfile = RUNTIME / "supervisor.pid"
        pidfile.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        logging.exception("failed to write pid file")


def _signal_handler(signum, frame):
    global STOP
    logging.info(f"received signal {signum}, stopping supervisor")
    STOP = True


def main():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    _write_pid()

    # start all children
    for c in CHILDREN:
        _start(c)

    # loop and restart as needed
    try:
        while not STOP:
            for name, (p, out, err) in list(PROCS.items()):
                ret = p.poll()
                if ret is not None:
                    logging.warning(f"child {name} exited with {ret}, restarting")
                    try:
                        out.close(); err.close()
                    except Exception:
                        pass
                    PROCS.pop(name, None)
                    # find child config
                    cfg = next((x for x in CHILDREN if x["name"] == name), None)
                    if cfg:
                        time.sleep(2)
                        _start(cfg)
            time.sleep(5)
    finally:
        _stop_all()
        logging.info("supervisor exiting")


if __name__ == "__main__":
    main()
