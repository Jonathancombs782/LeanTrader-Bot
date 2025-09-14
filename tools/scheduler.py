"""Simple scheduler for LeanTrader: auto-runs focused crypto and forex pipelines.

Features:
- Blocking scheduler with configurable intervals for `crypto` and `forex` jobs.
- Safe single-instance per-job locking using PID lockfiles in `runtime/locks/`.
- One-shot mode (--once) to run both jobs sequentially and exit (useful for CI/Task Scheduler).
- CLI flags to run individual jobs immediately.
- Writes logs to `runtime/logs/scheduler.log` and last-run metadata to `runtime/last_run.json`.

Usage:
  python tools/scheduler.py --once
  python tools/scheduler.py             # run as a long-lived scheduler
  python tools/scheduler.py --run-crypto-now

This file uses subprocess to call existing repository scripts (conservative approach
to avoid importing fragile adapters at top-level). Adjust commands in the job wrappers
if you'd rather call library functions directly.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except Exception:
    BlockingScheduler = None  # handled below

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
LOG_DIR = RUNTIME / "logs"
LOCK_DIR = RUNTIME / "locks"
LAST_RUN_FILE = RUNTIME / "last_run.json"

for d in (RUNTIME, LOG_DIR, LOCK_DIR):
    d.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "scheduler.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)


def _lock_path(job_name: str) -> Path:
    return LOCK_DIR / f"{job_name}.lock"


def _acquire_lock(job_name: str) -> bool:
    p = _lock_path(job_name)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            pid = int(data.get("pid", 0))
        except Exception:
            pid = 0
        # check if pid is still alive
        if pid and _process_is_running(pid):
            logging.info("Lock for job %s present and PID %s is running — skipping run", job_name, pid)
            return False
        else:
            logging.info("Stale lock for %s detected, overwriting", job_name)
    p.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}))
    return True


def _release_lock(job_name: str) -> None:
    p = _lock_path(job_name)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        logging.exception("Failed to release lock for %s", job_name)


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            # On Windows, os.kill with signal 0 doesn't exist reliably; use tasklist
            import subprocess as _sp

            r = _sp.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _write_last_run(job_name: str, success: bool, details: dict | None = None) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    try:
        data = {}
        if LAST_RUN_FILE.exists():
            data = json.loads(LAST_RUN_FILE.read_text())
    except Exception:
        data = {}
    data[job_name] = {"ts": now, "success": bool(success), "details": details or {}}
    try:
        LAST_RUN_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        logging.exception("Failed to write last run metadata")


def _run_script(script_rel: str, args: list[str] | None = None, timeout: int = 600) -> tuple[bool, str]:
    args = args or []
    script = ROOT / script_rel
    if not script.exists():
        msg = f"Script not found: {script_rel}"
        logging.error(msg)
        return False, msg
    cmd = [sys.executable, str(script)] + args
    logging.info("Running command: %s", " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip() + "\n" + r.stderr.strip()
        success = r.returncode == 0
        logging.info("Script %s exit=%s", script_rel, r.returncode)
        return success, out
    except subprocess.TimeoutExpired as e:
        logging.exception("Script %s timed out", script_rel)
        return False, str(e)
    except Exception as e:
        logging.exception("Script %s failed", script_rel)
        return False, str(e)


def crypto_job() -> None:
    name = "crypto"
    if not _acquire_lock(name):
        return
    try:
        # 1) Run crawler (best-effort)
        ok_c, out_c = _run_script("tools/run_crawler.py")
        # 2) Train / update learner
        ok_l, out_l = _run_script("tools/learner.py")
        # 3) Optional: run crypto-specific scans or demo publisher
        ok_p, out_p = _run_script("runtime/publish_demo.py")
        success = ok_c and ok_l and ok_p
        _write_last_run(name, success, {"crawler_ok": ok_c, "learner_ok": ok_l, "publisher_ok": ok_p})
        if not success:
            logging.warning("One or more crypto sub-tasks failed: %s %s %s", ok_c, ok_l, ok_p)
    finally:
        _release_lock(name)


def forex_job() -> None:
    name = "forex"
    if not _acquire_lock(name):
        return
    try:
        # For forex we prefer a slightly longer cadence and may run different scripts
        ok_c, out_c = _run_script("tools/run_crawler.py")
        ok_l, out_l = _run_script("tools/learner.py")
        ok_scan, out_scan = _run_script("scan_runner.py")
        success = ok_c and ok_l and ok_scan
        _write_last_run(name, success, {"crawler_ok": ok_c, "learner_ok": ok_l, "scan_ok": ok_scan})
        if not success:
            logging.warning("One or more forex sub-tasks failed: %s %s %s", ok_c, ok_l, ok_scan)
    finally:
        _release_lock(name)


def hype_job() -> None:
    """Optional hype radar job: runs when HYPE_SCHED_ENABLED=true."""
    if os.getenv("HYPE_SCHED_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return
    name = "hype"
    if not _acquire_lock(name):
        return
    try:
        assets = os.getenv("HYPE_ASSETS", "BTC,ETH,SOL,XRP,DOGE")
        ok, out = _run_script("scanners/hype_radar.py", ["--assets", assets])
        _write_last_run(name, ok, {"assets": assets})
        if not ok:
            logging.warning("hype_radar failed: %s", out[-200:])
    finally:
        _release_lock(name)


def collectors_job() -> None:
    """Optional collectors for social/dev volumes, gated by env flags."""
    if os.getenv("COLLECTORS_SCHED_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return
    name = "collectors"
    if not _acquire_lock(name):
        return
    try:
        assets = os.getenv("HYPE_ASSETS", os.getenv("COLLECT_ASSETS", "BTC,ETH,SOL,XRP,DOGE"))
        # Twitter
        if os.getenv("TWITTER_SCHED_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            _run_script("tools/collect_twitter_rates.py", ["--assets", assets])
        # GitHub
        repos = os.getenv("GITHUB_REPOS", "ethereum/go-ethereum,solana-labs/solana")
        if os.getenv("GITHUB_SCHED_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            _run_script("tools/collect_github_commits.py", ["--repos", repos])
        # Discord
        chans = os.getenv("DISCORD_CHANNELS", "")
        if os.getenv("DISCORD_SCHED_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            _run_script("tools/collect_discord_volume.py", ["--assets", assets, "--channels", chans])
        # Telegram
        tg_chans = os.getenv("TELEGRAM_CHANNELS", "")
        if os.getenv("TELEGRAM_SCHED_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            _run_script("tools/collect_telegram_volume.py", ["--assets", assets, "--channels", tg_chans])
    finally:
        _release_lock(name)


def hedge_job() -> None:
    if os.getenv("HEDGE_SCHED_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return
    name = "hedger"
    if not _acquire_lock(name):
        return
    try:
        args = []
        if os.getenv("HEDGE_LIVE", "false").strip().lower() in ("1", "true", "yes", "on"):
            args.append("--execute")
        _run_script("tools/hedge_daemon.py", args + ["--interval", os.getenv("HEDGE_INTERVAL_SEC", "3600")])
    finally:
        _release_lock(name)


def moon_job() -> None:
    if os.getenv("MOON_SCHED_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return
    name = "moon"
    if not _acquire_lock(name):
        return
    try:
        _run_script("scanners/moon_radar.py", ["--once"])
    finally:
        _release_lock(name)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="LeanTrader simple scheduler (crypto + forex)")
    p.add_argument("--once", action="store_true", help="Run both jobs once (sequential) and exit")
    p.add_argument("--run-crypto-now", action="store_true", help="Run crypto job now and exit")
    p.add_argument("--run-forex-now", action="store_true", help="Run forex job now and exit")
    p.add_argument("--crypto-interval-mins", type=int, default=2, help="Crypto cadence in minutes")
    p.add_argument("--forex-interval-mins", type=int, default=5, help="Forex cadence in minutes")
    args = p.parse_args(argv)

    if args.run_crypto_now:
        crypto_job()
        return 0
    if args.run_forex_now:
        forex_job()
        return 0
    if args.once:
        crypto_job()
        forex_job()
        return 0

    if BlockingScheduler is None:
        logging.error("apscheduler is not installed. Please install requirements (pip install apscheduler)")
        return 2

    sched = BlockingScheduler()
    sched.add_job(
        crypto_job,
        trigger=IntervalTrigger(minutes=max(1, args.crypto_interval_mins)),
        id="crypto-job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    sched.add_job(
        forex_job,
        trigger=IntervalTrigger(minutes=max(1, args.forex_interval_mins)),
        id="forex-job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # Optional hype radar at custom cadence
    try:
        hype_min = int(os.getenv("HYPE_INTERVAL_MINS", "10"))
        sched.add_job(
            hype_job,
            trigger=IntervalTrigger(minutes=max(1, hype_min)),
            id="hype-job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    except Exception:
        pass
    # Collectors job
    try:
        coll_min = int(os.getenv("COLLECT_INTERVAL_MINS", "15"))
        sched.add_job(
            collectors_job,
            trigger=IntervalTrigger(minutes=max(1, coll_min)),
            id="collectors-job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    except Exception:
        pass
    # Hedging job (hourly default)
    try:
        hedge_min = int(int(os.getenv("HEDGE_INTERVAL_SEC", "3600")) / 60)
        sched.add_job(
            hedge_job,
            trigger=IntervalTrigger(minutes=max(1, hedge_min)),
            id="hedge-job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    except Exception:
        pass
    # Moon radar job
    try:
        moon_min = int(os.getenv("MOON_INTERVAL_MINS", "15"))
        sched.add_job(
            moon_job,
            trigger=IntervalTrigger(minutes=max(1, moon_min)),
            id="moon-job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    except Exception:
        pass

    logging.info(
        "Scheduler starting: crypto every %s mins, forex every %s mins",
        args.crypto_interval_mins,
        args.forex_interval_mins,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped by user")
        return 0
    except Exception:
        logging.exception("Scheduler failed")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
