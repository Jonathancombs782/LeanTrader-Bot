"""Run quick project checks and dump JSON output for diagnostics.

This script calls `router.scan_full_project()` (a lightweight AST/file scanner)
and writes results to `checks_output.json` in the repo root.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from router import scan_full_project
except Exception as e:
    print(f"failed to import router.scan_full_project: {e}")
    raise

out = scan_full_project(
    str(ROOT), py_ext=".py", include_exts=[".py", ".yml", ".md"], top_n=30
)
with open(ROOT / "checks_output.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"wrote: {ROOT / 'checks_output.json'}")
