"""
Conservative auto-fixer: reads reports/f401_report.txt and appends "# noqa: F401"
to the reported import lines. This is intentionally conservative and preserves behavior.
Use this when you want to keep imports for side-effects or developer reasons but quiet
flake8 until a human review.

Run: python -m tools.auto_mark_f401
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "f401_report.txt"

if not REPORT.exists():
    print("No report found at", REPORT)
    raise SystemExit(1)

pat = re.compile(r"^\.\\(?P<path>.+?):(?P<line>\d+):\d+: F401")

edits = 0
for raw in REPORT.read_text(encoding="utf-8").splitlines():
    m = pat.match(raw)
    if not m:
        continue
    rel = m.group("path").replace("\\", "/")
    line_no = int(m.group("line"))
    f = ROOT / rel
    if not f.exists():
        print("Missing file:", f)
        continue
    lines = f.read_text(encoding="utf-8").splitlines()
    idx = line_no - 1
    if idx < 0 or idx >= len(lines):
        print("Invalid line index for", f, line_no)
        continue
    orig = lines[idx]
    if "# noqa" in orig:
        continue
    # Only modify if this line looks like an import statement
    if orig.strip().startswith("import") or orig.strip().startswith("from"):
        lines[idx] = orig + "  # noqa: F401  # intentionally kept"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        edits += 1
        print("Patched", f, "line", line_no)

print("Done. Edited", edits, "files.")
