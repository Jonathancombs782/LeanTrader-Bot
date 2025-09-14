import argparse
import ast
import importlib.util
import json
import os
from typing import Any, Dict, List, Tuple


def find_py_files(root: str, exclude_dirs=None) -> List[str]:
    if exclude_dirs is None:
        exclude_dirs = {
            ".git",
            "__pycache__",
            "venv",
            "env",
            ".venv",
            "node_modules",
            "reports",
        }
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        parts = set(p for p in dirpath.split(os.sep) if p)
        if parts & exclude_dirs:
            continue
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def parse_file(path: str) -> Tuple[bool, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=path)
        return True, tree
    except Exception as e:
        return False, str(e)


def extract_imports(tree: ast.AST) -> List[str]:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name:
                    mods.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return sorted(mods)


def check_module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def analyze_project(root: str) -> Dict[str, Any]:
    files = find_py_files(root)
    report: Dict[str, Any] = {
        "root": os.path.abspath(root),
        "files": {},
        "summary": {"files": len(files), "parse_errors": 0, "missing_imports_total": 0},
    }
    for p in files:
        rel = os.path.relpath(p, root)
        ok, res = parse_file(p)
        entry: Dict[str, Any] = {"path": p, "rel": rel}
        if not ok:
            entry["parse_error"] = res
            report["summary"]["parse_errors"] += 1
            report["files"][rel] = entry
            continue
        tree = res
        imports = extract_imports(tree)
        missing = []
        for m in imports:
            if not check_module_available(m):
                missing.append(m)
        entry["imports"] = imports
        entry["missing_imports"] = sorted(missing)
        report["summary"]["missing_imports_total"] += len(missing)
        report["files"][rel] = entry
    return report


def pretty_report(rep: Dict[str, Any]) -> None:
    root = rep.get("root")
    s = rep.get("summary", {})
    print(f"Static check root: {root}")
    print(
        f"Files scanned: {s.get('files', 0)}  parse_errors: {s.get('parse_errors', 0)}  total_missing_imports: {s.get('missing_imports_total', 0)}"
    )
    print("-" * 80)
    for rel, info in rep.get("files", {}).items():
        pe = info.get("parse_error")
        if pe:
            print(f"[PARSE ERROR] {rel}: {pe}")
            continue
        missing = info.get("missing_imports", []) or []
        if missing:
            print(f"[MISSING IMPORTS] {rel}: {len(missing)} -> {', '.join(missing)}")
    print("-" * 80)


def main():
    ap = argparse.ArgumentParser(
        description="Light static checker: parse + import availability (no execution)."
    )
    ap.add_argument("--root", default=".", help="project root to scan")
    ap.add_argument("--json", help="write JSON report to file")
    args = ap.parse_args()
    rep = analyze_project(args.root)
    pretty_report(rep)
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=2)
            print(f"Wrote JSON report to {args.json}")
        except Exception as e:
            print("Failed writing JSON:", e)


if __name__ == "__main__":
    main()
