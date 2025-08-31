import ast
import py_compile
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def find_py_files(root: Path):
    out = []
    for p in root.rglob("*.py"):
        # skip virtualenv, runtime, .git, __pycache__
        if any(part in ("venv", ".venv", ".git", "runtime", "__pycache__", "tools") for part in p.parts):
            continue
        out.append(p)
    return sorted(out)

def which_tools():
    tools = {}
    for t in ("ruff","isort","black","autoflake"):
        tools[t] = shutil.which(t)
    return tools

def run_cmd(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        return p.returncode, p.stdout.strip()
    except Exception as e:
        return 1, str(e)

def find_smike_script(root: Path):
    """Search for smike.py or smoke.py under root and return path or None."""
    for name in ("smike.py", "smoke.py"):
        for p in root.rglob(name):
            if any(part in ("venv", ".venv", ".git", "runtime", "__pycache__") for part in p.parts):
                continue
            return p
    return None

def run_smike_script(root: Path):
    script = find_smike_script(root)
    if not script:
        return 1, f"No smike.py or smoke.py found under {root}"
    cmd = f"{sys.executable} \"{script}\""
    return run_cmd(cmd, cwd=script.parent)

def scan_patterns(files):
    issues = []
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="ignore")
        # look for direct router assignment (potential mismatch) and absence of RouterAdapter
        if re.search(r"\bself\.router\s*=\s*router\b", txt) and "RouterAdapter" not in txt:
            issues.append({"file": str(f), "issue": "direct self.router=router without RouterAdapter"})
        # look for safe_* vs create_order usage
        if re.search(r"\bcreate_order\s*\(", txt) and "safe_place_order" not in txt:
            issues.append({"file": str(f), "issue": "uses create_order; consider safe_place_order wrapper"})
        # suspicious identical SL==entry (quick heuristic)
        if re.search(r"sl\s*=\s*float\(entry\s*([\+\-])\s*0\)", txt):
            issues.append({"file": str(f), "issue": "possible degenerate SL==entry pattern"})
    return issues

def auto_wrap_router(files):
    """Automatically wrap direct `self.router = router` assignments with RouterAdapter.
    Creates per-file .bak backups before writing changes.
    Returns list of changed file paths.
    """
    changed = []
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "self.router = router" not in txt:
            continue
        new_txt = txt
        # add import if missing
        if "from ultra_core import RouterAdapter" not in new_txt:
            # insert import after shebang or initial encoding line if present, else at top
            lines = new_txt.splitlines()
            insert_at = 0
            if lines and lines[0].startswith("#!"):
                insert_at = 1
            if len(lines) > insert_at and re.match(r"#\s*filepath:", lines[insert_at]) :
                insert_at += 1
            lines.insert(insert_at, "from ultra_core import RouterAdapter")
            new_txt = "\n".join(lines)
        # perform replacement (conservative)
        new_txt = new_txt.replace("self.router = router", "self.router = RouterAdapter(router, logger=getattr(self, 'logger', None))")
        if new_txt != txt:
            # backup original
            bak = f.with_suffix(f".py.bak")
            try:
                bak.write_text(txt, encoding="utf-8")
            except Exception:
                pass
            try:
                f.write_text(new_txt, encoding="utf-8")
                changed.append(str(f))
            except Exception:
                # restore backup on failure
                try:
                    if bak.exists():
                        f.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass
    return changed

def apply_formatters(files, tools):
    paths = " ".join(str(p) for p in files)
    results = {}
    if tools.get("ruff"):
        rc, out = run_cmd(f"ruff check --fix {paths}")
        results["ruff"] = (rc, out)
    if tools.get("isort"):
        rc, out = run_cmd(f"isort {paths}")
        results["isort"] = (rc, out)
    if tools.get("black"):
        rc, out = run_cmd(f"black {paths}")
        results["black"] = (rc, out)
    if tools.get("autoflake"):
        rc, out = run_cmd(f"autoflake --in-place --remove-all-unused-imports -r {paths}")
        results["autoflake"] = (rc, out)
    return results

def inspect_router_interface(root: Path):
    """Look for router.py and check for common method names using AST."""
    router_paths = list(root.rglob("router.py"))
    if not router_paths:
        return {"found": False, "path": None, "methods": {}}
    p = router_paths[0]
    info = {"found": True, "path": str(p), "methods": {}}
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        funcs = {fn.name for fn in tree.body if isinstance(fn, ast.FunctionDef)}
        # check for likely router-class method names or free functions
        expected = ["safe_place_order","safe_fetch_ticker","safe_fetch_ohlcv","safe_close_position","create_order","fetch_ticker","fetch_ohlcv"]
        for name in expected:
            info["methods"][name] = name in funcs or (name in src)
    except Exception as e:
        info["error"] = str(e)
    return info

def full_scan(files, tools, root: Path):
    """Run a fuller scan: syntax checks + optional linters + router interface inspection."""
    report = {"syntax": [], "ruff": None, "flake8": None, "router": None}
    # syntax check via py_compile
    for f in files:
        try:
            # use py_compile to get deterministic errors
            py_compile.compile(str(f), doraise=True)
        except Exception as e:
            report["syntax"].append({"file": str(f), "error": str(e)})
    # run ruff if available
    if tools.get("ruff"):
        rc, out = run_cmd(f"ruff check {' '.join(str(p) for p in files)}")
        report["ruff"] = {"rc": rc, "out": out}
    # run flake8 if available
    if shutil.which("flake8"):
        rc, out = run_cmd(f"flake8 {' '.join(str(p) for p in files)}")
        report["flake8"] = {"rc": rc, "out": out}
    # inspect router.py interface
    report["router"] = inspect_router_interface(root)
    return report

def main():
    ap = argparse.ArgumentParser(description="Autofix / scan helper for LeanTrader_ForexPack")
    ap.add_argument("--apply", action="store_true", help="Run fixers (black/isort/ruff/autoflake) if available")
    ap.add_argument("--auto-wrap-router", action="store_true", help="Auto-replace `self.router = router` with RouterAdapter wrapping (creates .bak files)")
    ap.add_argument("--run-smike", action="store_true", help="Locate and run smike.py (or smoke.py) automatically and capture output")
    ap.add_argument("--full-scan", action="store_true", help="Run full static scan (syntax, optional linters, router interface checks)")
    ap.add_argument("--report-json", type=str, default="", help="Write json report to file")
    args = ap.parse_args()

    files = find_py_files(ROOT)
    print(f"Found {len(files)} python files under {ROOT}")
    tools = which_tools()
    print("Detected tools:", {k: bool(v) for k,v in tools.items()})

    issues = scan_patterns(files)
    print(f"Pattern scan found {len(issues)} potential issues.")
    for it in issues[:50]:
        print(f"- {it['file']}: {it['issue']}")

    if args.auto_wrap_router:
        print("Running auto-wrap-router transformation (creating .bak backups)...")
        changed = auto_wrap_router(files)
        print(f"Auto-wrap changed {len(changed)} files:")
        for c in changed:
            print(" -", c)
        # re-scan patterns after change
        issues = scan_patterns(files)
        print(f"Pattern scan after auto-wrap found {len(issues)} potential issues.")
        for it in issues[:50]:
            print(f"- {it['file']}: {it['issue']}")

    smike_result = None
    if args.run_smike:
        print("Attempting to locate and run smike.py / smoke.py...")
        rc, out = run_smike_script(ROOT)
        smike_result = {"rc": rc, "out": out}
        print(f"smike run rc={rc}")
        if out:
            print(out[:2000])

    full_scan_res = None
    if args.full_scan:
        print("Running full static scan (syntax + linters + router checks)...")
        full_scan_res = full_scan(files, tools, ROOT)
        # print concise results
        if full_scan_res.get("syntax"):
            print(f"Syntax errors: {len(full_scan_res['syntax'])}")
            for s in full_scan_res["syntax"][:10]:
                print(f"- {s['file']}: {s['error'][:200]}")
        else:
            print("No syntax errors detected.")
        if full_scan_res.get("ruff"):
            print("Ruff check rc:", full_scan_res["ruff"]["rc"])
        if full_scan_res.get("flake8"):
            print("Flake8 check rc:", full_scan_res["flake8"]["rc"])
        if full_scan_res.get("router"):
            rinfo = full_scan_res["router"]
            print("Router.py found:", rinfo.get("found"), "path:", rinfo.get("path"))
            if rinfo.get("methods"):
                print("Router methods presence sample:", {k:v for k,v in list(rinfo['methods'].items())[:6]})

    report = {"files_scanned": len(files), "tools": {k: bool(v) for k,v in tools.items()}, "pattern_issues": issues}
    if smike_result is not None:
        report["smike_run"] = smike_result
    if full_scan_res is not None:
        report["full_scan"] = full_scan_res

    if args.apply:
        print("Applying available formatters (this will modify files).")
        res = apply_formatters(files, tools)
        for k, (rc, out) in res.items():
            print(f"=== {k} rc={rc} ===")
            if out:
                print(out[:2000])
        report["format_results"] = {k: {"rc": rc, "out": out} for k, (rc, out) in res.items()}

    if args.report_json:
        try:
            Path(args.report_json).write_text(json.dumps(report, indent=2), encoding="utf-8")
            print("Wrote JSON report to", args.report_json)
        except Exception as e:
            print("Failed to write JSON report:", e, file=sys.stderr)

    print("Done. Review the pattern_issues and formatter outputs. For safety, review changes before enabling live trading.")

if __name__ == "__main__":
    main()
