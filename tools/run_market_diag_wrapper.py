"""Wrapper runner to reliably run the market diagnostic and persist logs.

This script imports and runs `tools.market_diag.main()` and captures any
exceptions, writing a persistent `runtime/logs/market_diag.txt` file so the
results are visible even if shell redirection fails.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path


def _write(lines: list[str]) -> None:
    p = Path("runtime") / "logs" / "market_diag.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> int:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [f"market_diag wrapper start {ts}"]
    try:
        # Import here so package imports resolve when run as module
        from tools.market_diag import main as diag_main

        # run the diagnostic and capture output via prints
        try:
            ret = diag_main()
            lines.append(f"diagnostic returned: {ret}")
        except SystemExit as se:
            lines.append(f"diagnostic exited: {se}")
        except Exception as e:
            lines.append(f"diagnostic raised: {e}")
            lines.append(traceback.format_exc())
    except Exception as e:
        lines.append(f"failed to import diagnostic: {e}")
        lines.append(traceback.format_exc())

    ts2 = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"market_diag wrapper done {ts2}")
    _write(lines)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
