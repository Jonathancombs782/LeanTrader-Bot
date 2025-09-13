"""Run the crawler diagnostic and capture stdout/stderr to a file.

This avoids shell-level redirection issues in the test harness.
"""

from __future__ import annotations

import io
import os
import sys
import traceback

proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from tools import diagnose_crawler  # noqa: E402


def main():
    out_path = os.path.join("runtime", "logs", "diagnose_capture.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    buf = io.StringIO()
    try:
        diagnose_crawler.main()
    except Exception:
        traceback.print_exc(file=buf)
    # also capture sys.stdout if needed
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
    except Exception:
        pass


if __name__ == "__main__":
    main()
