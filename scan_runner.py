import argparse
import json
import os
import sys
from datetime import datetime


def _ensure_cwd_in_path(root: str):
    # ensure imports resolve when running from other dirs
    p = os.path.abspath(root)
    if p not in sys.path:
        sys.path.insert(0, p)


def run_scans(root: str, out_dir: str, pretty: bool = True):
    _ensure_cwd_in_path(root)
    try:
        from router import scan_full_project
    except Exception as e:
        scan_full_project = None
        print(f"[scan_runner] failed to import router.scan_full_project: {e}")
    try:
        from strategy import scan_project_with_model
    except Exception as e:
        scan_project_with_model = None
        print(f"[scan_runner] failed to import strategy.scan_project_with_model: {e}")

    results = {
        "meta": {
            "root": os.path.abspath(root),
            "ts": datetime.utcnow().isoformat() + "Z",
        }
    }

    if scan_full_project:
        try:
            results["router_full"] = scan_full_project(root)
            # persist router combined results
            fp = os.path.join(out_dir, "scan_full.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(results["router_full"], f, indent=2 if pretty else None)
            print(f"[scan_runner] saved router scan to {fp}")
        except Exception as e:
            results["router_error"] = str(e)
            print(f"[scan_runner] router scan error: {e}")

    if scan_project_with_model:
        try:
            results["strategy"] = scan_project_with_model(root)
            fp = os.path.join(out_dir, "strategy_scan.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(results["strategy"], f, indent=2 if pretty else None)
            print(f"[scan_runner] saved strategy scan to {fp}")
        except Exception as e:
            results["strategy_error"] = str(e)
            print(f"[scan_runner] strategy scan error: {e}")

    # quick summary if router scan present
    summary = {}
    rf = results.get("router_full") or {}
    other = rf.get("other_files", {})
    codebase = rf.get("codebase", {})
    if other:
        summary["total_other_files"] = sum(other.get("counts_by_ext", {}).values())
        summary["top_files_sample"] = other.get("top_files", [])[:5]
    if codebase and "totals" in codebase:
        summary["py_files"] = codebase["totals"].get("files")
        summary["py_parse_errors"] = codebase["totals"].get("parse_errors")
    # write merged summary
    fp = os.path.join(out_dir, "scan_summary.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(
            {"meta": results["meta"], "summary": summary},
            f,
            indent=2 if pretty else None,
        )
    print(f"[scan_runner] wrote summary to {fp}")
    return results


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Run project scans (router + strategy) and save JSON outputs"
    )
    p.add_argument("--root", "-r", default=".", help="Project root to scan")
    p.add_argument("--out", "-o", default=".", help="Output directory for JSON results")
    p.add_argument(
        "--no-pretty", dest="pretty", action="store_false", help="Disable pretty JSON"
    )
    args = p.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    run_scans(args.root, args.out, pretty=args.pretty)


if __name__ == "__main__":
    main()
