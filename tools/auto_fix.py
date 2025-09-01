import argparse
import ast
import json
import os
import re
from typing import Dict, List

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    "env",
    "node_modules",
    "reports",
    "tools",
}

# Safe textual fixes (order matters)
FIX_PATTERNS = [
    # Convert bare except: -> except Exception:
    (
        re.compile(r"(^[ \t]*)except\s*:(\s*(#.*)?)$", re.MULTILINE),
        r"\1except Exception:\2",
    ),
    # Fix accidental extra paren before colon: `.items()):` -> `.items():`
    (re.compile(r"\.items\(\)\):"), r".items():"),
    # Remove duplicated consecutive identical lines (handled separately)
]


def remove_consecutive_duplicates(text: str) -> str:
    out_lines: List[str] = []
    prev = None
    for line in text.splitlines():
        if line == prev:
            # skip duplicate
            prev = line
            continue
        out_lines.append(line)
        prev = line
    # preserve trailing newline if present originally
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


def apply_fixes(text: str) -> (str, List[str]):
    applied = []
    new = text
    # apply regex patterns
    for patt, repl in FIX_PATTERNS:
        new2, n = patt.subn(repl, new)
        if n:
            applied.append(f"pattern {patt.pattern!r} -> {n} replacement(s)")
            new = new2
    # remove consecutive duplicate lines
    new2 = remove_consecutive_duplicates(new)
    if new2 != new:
        applied.append("removed consecutive duplicate lines")
        new = new2
    return new, applied


def is_python_file(path: str) -> bool:
    return path.endswith(".py")


def safe_parse(src: str) -> (bool, str):
    try:
        ast.parse(src)
        return True, ""
    except Exception as e:
        return False, str(e)


def scan_and_fix(root: str, apply: bool = False) -> Dict[str, Dict]:
    report: Dict[str, Dict] = {}
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # skip excluded dirs
        parts = set(p for p in dirpath.split(os.sep) if p)
        if parts & EXCLUDE_DIRS:
            continue
        for fn in filenames:
            if not is_python_file(fn):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
            except Exception as e:
                report[rel] = {"ok": False, "error": f"read error: {e}"}
                continue
            # initial parse check
            ok_before, err_before = safe_parse(src)
            entry = {
                "ok_before": ok_before,
                "parse_error_before": err_before if not ok_before else "",
                "applied": [],
                "ok_after": None,
                "parse_error_after": None,
            }
            # attempt fixes only if parse failed OR file contains patterns we can fix
            should_try = (
                (not ok_before)
                or any(p.search(src) for p, _ in FIX_PATTERNS)
                or ".items())" in src
                or "\n" + src.splitlines()[-1] + "\n" in src
            )
            if not should_try:
                entry["reason"] = "no fixes needed"
                report[rel] = entry
                continue
            new_src, applied = apply_fixes(src)
            entry["applied"] = applied
            ok_after, err_after = safe_parse(new_src)
            entry["ok_after"] = ok_after
            entry["parse_error_after"] = err_after if not ok_after else ""
            # write back only when parse succeeds and apply flag set
            if ok_after and apply and new_src != src:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_src)
                    entry["written"] = True
                except Exception as e:
                    entry["written"] = False
                    entry["write_error"] = str(e)
            report[rel] = entry
    return report


def main(argv: List[str] = None):
    p = argparse.ArgumentParser(
        description="Conservative auto-fixer for common Python repo issues"
    )
    p.add_argument("--root", "-r", default=".", help="Project root")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write fixes to files (only when parse succeeds)",
    )
    p.add_argument(
        "--out", "-o", default="tools/auto_fix_report.json", help="Report JSON path"
    )
    args = p.parse_args(argv)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    report = scan_and_fix(args.root, apply=args.apply)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Auto-fix report written to {args.out}")
    # print summary
    total = len(report)
    fixes = sum(1 for v in report.values() if v.get("applied"))
    written = sum(1 for v in report.values() if v.get("written"))
    parsed_fail_before = sum(1 for v in report.values() if not v.get("ok_before"))
    parsed_fail_after = sum(1 for v in report.values() if not v.get("ok_after"))
    print(
        f"Files scanned: {total}, files with attempted fixes: {fixes}, files written: {written}"
    )
    print(f"Parse failures before: {parsed_fail_before}, after: {parsed_fail_after}")


if __name__ == "__main__":
    main()
