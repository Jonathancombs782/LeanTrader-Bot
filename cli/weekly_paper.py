from __future__ import annotations

import argparse
import datetime as dt

from reporting.weekly_paper import write_weekly_report


def _current_iso_week() -> str:
    today = dt.date.today()
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


def main() -> int:
    p = argparse.ArgumentParser(description="Build weekly research paper (PDF if possible)")
    p.add_argument("--week", default=_current_iso_week(), help="ISO week like YYYY-Www (default: current week)")
    p.add_argument("--out", default="out/reports/weekly", help="Output prefix (without extension)")
    args = p.parse_args()

    res = write_weekly_report(args.week, out_prefix=args.out)
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

