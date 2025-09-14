"""Compile all .py files under the workspace, excluding backup folders that
may contain malformed snippets (_incoming, runtime/backups). This mirrors
`python -m compileall` but with filter control for faster diagnostics.
"""

import compileall
import pathlib
import sys

EXCLUDE = {"_incoming", "runtime/backups"}


def should_skip(p: pathlib.Path) -> bool:
    # Skip if path contains any excluded segment or subfolder
    s = str(p)
    if "_incoming" in s:
        return True
    # handle mixed separators for Windows/Unix
    if "runtime/backups" in s or "runtime\\backups" in s:
        return True
    return False


def main(root: str = ".") -> int:
    root_p = pathlib.Path(root).resolve()
    bad = []
    for p in root_p.rglob("*.py"):
        if should_skip(p):
            continue
        try:
            # compile single file in quiet mode
            ok = compileall.compile_file(str(p), quiet=1)
            if not ok:
                bad.append(str(p))
        except Exception as e:  # pragma: no cover - diagnostic script
            bad.append(f"{p}: {e}")

    if bad:
        print("Compile failures:")
        for b in bad:
            print(" -", b)
        return 2
    print("All scanned python files compiled successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main("."))
