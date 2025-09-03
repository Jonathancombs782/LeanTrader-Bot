"""Run a short continuous demo that publishes signals across TFs periodically.

This is safe to run in paper mode. It reuses tools.demo_run logic but loops and
respects the signal publisher's rate limits.
"""
from __future__ import annotations

import time
from pathlib import Path
from dotenv import load_dotenv


def main(loop_minutes: int = 5):
    load_dotenv()
    from tools import demo_run

    end = time.time() + loop_minutes * 60
    while time.time() < end:
        try:
            print('continuous demo tick')
            demo_run.main()
        except Exception as e:
            print('demo tick error:', e)
        time.sleep(30)


if __name__ == '__main__':
    main()
