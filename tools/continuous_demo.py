"""Run a short continuous demo that publishes signals across TFs periodically.

This is safe to run in paper mode. It reuses tools.demo_run logic but loops and
respects the signal publisher's rate limits.
"""

from __future__ import annotations

import time

from dotenv import load_dotenv


def main(loop_minutes: int | None = None):
    """Run continuous demo; if loop_minutes is None run forever (supervisor-friendly).

    The function imports `tools.demo_run` lazily and calls its main() in a loop.
    """
    load_dotenv()
    # Diagnostic: print environment helpful for debugging import issues under
    # supervisor (cwd and sys.path). Kept lightweight so it's safe in prod.
    try:
        import os
        import sys

        print(f"[diag] cwd={os.getcwd()} sys.path[0]={sys.path[0]}")
    except Exception:
        pass
    from tools import demo_run

    end = None if loop_minutes is None else time.time() + loop_minutes * 60
    while True if end is None else time.time() < end:
        try:
            print("continuous demo tick")
            demo_run.main()
        except Exception as e:
            print("demo tick error:", e)
        time.sleep(30)


if __name__ == "__main__":
    main()
