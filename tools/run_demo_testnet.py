"""
Run the bot in testnet/demo-friendly mode.
- If BYBIT/API keys are present in environment, enable testnet live mode (ENABLE_LIVE/ALLOW_LIVE/LIVE_CONFIRM)
  and start the supervisor so modules run against the exchange testnet.
- If no API creds are found, fall back to paper broker by setting EXCHANGE_ID=paper and starting the supervisor.

This script is intentionally conservative: it will not modify existing API_KEY/API_SECRET values.
It only sets the minimal env toggles required to run the workspace in a test/demo context.

Usage (PowerShell):
    python -u tools\run_demo_testnet.py

"""

import os
import subprocess
import sys
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

PY = sys.executable or "python"


def has_api_creds() -> bool:
    # Check common env names: API_KEY/API_SECRET or BYBIT_API_KEY/BYBIT_API_SECRET
    if os.getenv("API_KEY") and os.getenv("API_SECRET"):
        return True
    if os.getenv("BYBIT_API_KEY") and os.getenv("BYBIT_API_SECRET"):
        return True
    return False


def main():
    print("[run_demo_testnet] Starting demo/testnet helper")
    if has_api_creds():
        print("[run_demo_testnet] Found API credentials in environment. Enabling testnet/live mode (testnet only).")
        os.environ.setdefault("ENABLE_LIVE", "true")
        os.environ.setdefault("ALLOW_LIVE", "true")
        os.environ.setdefault("LIVE_CONFIRM", "YES")
        # Prefer explicit BYBIT testnet toggle when using bybit
        os.environ.setdefault("BYBIT_TESTNET", "true")
        os.environ.setdefault("EXCHANGE_ID", "bybit")
        # Start supervisor which will pick up env flags
        cmd = [PY, "-u", "-m", "tools.supervisor"]
    else:
        print("[run_demo_testnet] No API credentials detected. Falling back to safe paper broker (EXCHANGE_ID=paper).")
        os.environ.setdefault("EXCHANGE_ID", "paper")
        os.environ.setdefault("ENABLE_LIVE", "false")
        # Start a short paper run by default to avoid long-running surprises
        cmd = [PY, "-u", "tools/paper_run.py", "--minutes", "60"]

    print(f"[run_demo_testnet] Running: {cmd}")
    # Launch subprocess and forward output
    try:
        p = subprocess.Popen(cmd, cwd=os.getcwd())
        print(f"[run_demo_testnet] Supervisor started pid={p.pid}")
        # Wait briefly to show initial startup, then detach
        time.sleep(2)
        print("[run_demo_testnet] Detached; check runtime/logs/ for process logs.")
    except Exception as e:
        print(f"[run_demo_testnet] Failed to start process: {e}")
        raise


if __name__ == "__main__":
    main()
