"""
Report unused-import (F401) occurrences by running flake8 and saving output.
Run: python -m tools.report_unused_imports
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)
REPORT = OUT / "f401_report.txt"


def run():
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "flake8",
        "--select=F401",
        ".",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, check=False
        )
        out = proc.stdout.strip() + (
            "\n" + proc.stderr.strip() if proc.stderr.strip() else ""
        )
    except Exception as e:
        out = f"Error running flake8: {e}"

    REPORT.write_text(out, encoding="utf-8")
    print(f"Wrote unused-import report to: {REPORT}")


if __name__ == "__main__":
    run()
