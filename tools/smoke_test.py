"""Smoke test for basic end-to-end sanity checks.

Imports core modules and runs a single demo + reconcile + ctf pass in paper mode.
"""

from __future__ import annotations

import importlib

from dotenv import load_dotenv


def main():
    load_dotenv()
    ok = True
    try:
        Router = importlib.import_module("traders_core.router")
        r = Router.ExchangeRouter()
        print("router.info():", r.info())
        print("router.account():", r.account())
    except Exception as e:
        print("router import/inspect failed:", e)
        ok = False

    try:
        demo = importlib.import_module("tools.demo_run")
        print("running demo_run.main() (paper mode)")
        demo.main()
    except Exception as e:
        print("demo_run failed:", e)
        ok = False

    try:
        recon = importlib.import_module("tools.reconcile_positions")
        recon.reconcile()
    except Exception as e:
        print("reconcile failed:", e)
        ok = False

    try:
        ctf = importlib.import_module("tools.ctf_manager")
        ctf.main()
    except Exception as e:
        print("ctf_manager failed:", e)
        ok = False

    if ok:
        print("smoke_test: OK")
    else:
        print("smoke_test: FAILED")


if __name__ == "__main__":
    main()
