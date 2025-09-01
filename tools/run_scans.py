# run_scans.py
import argparse
import json
import os
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description="Run repo scans and emit JSON report")
    p.add_argument("--root", "-r", default=".", help="Project root")
    p.add_argument(
        "--out",
        "-o",
        default=os.path.join("reports", "scan_report.json"),
        help="Output JSON path",
    )
    args = p.parse_args(argv)

    sys.path.insert(0, os.path.abspath(args.root))
    report = {"meta": {"root": os.path.abspath(args.root)}}
    # run router scan
    try:
        from router import scan_full_project

        report["full_project"] = scan_full_project(args.root)
    except Exception as e:
        report["full_project_error"] = str(e)
    # run strategy + model scan
    try:
        from strategy import scan_project_with_model

        report["strategy_scan"] = scan_project_with_model(args.root)
    except Exception as e:
        report["strategy_scan_error"] = str(e)

    # Detect requirements-like files in project root (catch misspellings like 'require,ents.fx.txt')
    try:
        reqs = {}
        for entry in os.listdir(args.root):
            low = entry.lower()
            if "require" in low:
                full = os.path.join(args.root, entry)
                if os.path.isfile(full):
                    try:
                        with open(full, "r", encoding="utf-8") as rf:
                            lines = [ln.strip() for ln in rf.readlines()]
                        # filter out comments and blank lines
                        pkgs = [ln for ln in lines if ln and not ln.startswith("#")]
                        reqs[entry] = pkgs
                    except Exception as e:
                        reqs[entry] = {"error": str(e)}
        if reqs:
            report["requirements_files"] = reqs
        else:
            report["requirements_files"] = {}
    except Exception as e:
        report["requirements_files_error"] = str(e)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote scan report to {args.out}")


if __name__ == "__main__":
    main()
