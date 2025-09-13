from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from reporting.daily_report import build_report_payload, render_html, save_pdf


def _load_summary(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _infer_fields(summary: Dict[str, Any]) -> Dict[str, Any]:
    # Try serverless_rebalance schema first
    allocs = summary.get("indices") or summary.get("selected") or []
    pnl_q = summary.get("pnl_q") or summary.get("quantum", {}).get("pnl_series") or []
    pnl_c = summary.get("pnl_c") or summary.get("classical", {}).get("pnl_series") or []
    risk = summary.get("risk") or {}
    var = risk.get("var") or risk.get("quantum", {}).get("var") or 0.0
    cvar = risk.get("cvar") or risk.get("quantum", {}).get("cvar") or 0.0
    # Optional metrics (would come from exporter snapshot if available)
    solve_hist = summary.get("solve_ms") or []
    fallbacks = summary.get("fallbacks") or 0
    notes = summary.get("notes") or ""
    return dict(allocs=allocs, pnl_q=pnl_q, pnl_c=pnl_c, var=var, cvar=cvar, solve_hist=solve_hist, fallbacks=fallbacks, notes=notes)


def main():
    import argparse

    p = argparse.ArgumentParser(description="Generate daily HTML/PDF report")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--out", required=True, help="output path prefix (e.g., out/report)")
    p.add_argument("--json", required=True, help="path to summary json")
    args = p.parse_args()

    try:
        js = _load_summary(args.json)
        fields = _infer_fields(js)
        payload = build_report_payload(
            date=args.date,
            allocs=fields["allocs"],
            pnl_q=fields["pnl_q"],
            pnl_c=fields["pnl_c"],
            var=float(fields["var"]),
            cvar=float(fields["cvar"]),
            solve_histogram=fields["solve_hist"],
            fallbacks=int(fields["fallbacks"]),
            notes=fields["notes"],
        )
        # Optional: compute attribution if summary provides series
        try:
            pnl_series = summary.get("pnl_series")
            components = summary.get("components")
            if pnl_series and components and isinstance(components, dict):
                from analytics.attribution import write_daily_attribution  # type: ignore

                write_daily_attribution(args.date, pnl_series, components)
        except Exception:
            pass
        html = render_html(payload)
        out_html = f"{args.out}.html"
        out_pdf = f"{args.out}.pdf"
        os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html)
        ok = save_pdf(html, out_pdf)
        print(json.dumps({"html": out_html, "pdf": out_pdf if ok else None}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
