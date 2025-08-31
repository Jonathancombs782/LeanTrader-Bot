import os, json, time
from pathlib import Path

try:
    from tools.static_check import analyze_project
except Exception:
    import importlib.util, sys
    p = Path(__file__).resolve().parent / "static_check.py"
    spec = importlib.util.spec_from_file_location("tools.static_check", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    analyze_project = getattr(mod, "analyze_project")

def run_once(root: str = "."):
    ts = int(time.time())
    outdir = Path("runtime")
    outdir.mkdir(parents=True, exist_ok=True)
    report = analyze_project(root)
    outpath = outdir / f"static_report_{ts}.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    s = report.get("summary", {})
    print(f"Static check root: {report.get('root')}")
    print(f"Files scanned: {s.get('files',0)}  parse_errors: {s.get('parse_errors',0)}  total_missing_imports: {s.get('missing_imports_total',0)}")
    if s.get("parse_errors",0) > 0 or s.get("missing_imports_total",0) > 0:
        print(f"Detailed report written to: {outpath}")
    else:
        print("No parse errors or missing imports detected.")
    return outpath

if __name__ == "__main__":
    run_once(".")