from __future__ import annotations

import base64
import io
import json
import os
from typing import Any, Dict, List
from pathlib import Path


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _render_chart_base64(pnl_q: List[float] | None, pnl_c: List[float] | None, solve_hist: List[float] | None) -> str:
    """Render a simple chart (PNG) as base64 using plotly if available, else matplotlib.

    Returns a data URI string (image/png;base64, ...). If plotting not available, return empty string.
    """
    pnl_q = pnl_q or []
    pnl_c = pnl_c or []
    solve_hist = solve_hist or []

    # Prefer plotly
    try:
        import plotly.graph_objects as go  # type: ignore

        fig = go.Figure()
        if pnl_q:
            fig.add_trace(go.Scatter(y=pnl_q, name="PnL Quantum", mode="lines"))
        if pnl_c:
            fig.add_trace(go.Scatter(y=pnl_c, name="PnL Classical", mode="lines"))
        if solve_hist:
            # show solve ms as a bar inset
            fig.add_trace(go.Bar(y=solve_hist, name="Solve ms", opacity=0.4, yaxis="y2"))
            fig.update_layout(
                yaxis2=dict(overlaying="y", side="right", title="ms", showgrid=False)
            )
        fig.update_layout(height=360, margin=dict(l=30, r=30, t=30, b=30), legend=dict(orientation="h"))
        buf = fig.to_image(format="png")  # requires kaleido
        b64 = base64.b64encode(buf).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        pass

    # Fallback matplotlib
    try:
        import matplotlib.pyplot as plt  # type: ignore

        plt.figure(figsize=(8, 3))
        if pnl_q:
            plt.plot(pnl_q, label="PnL Quantum")
        if pnl_c:
            plt.plot(pnl_c, label="PnL Classical")
        plt.legend()
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def build_report_payload(
    date: str,
    allocs: List[Any],
    pnl_q: List[float] | float,
    pnl_c: List[float] | float,
    var: float,
    cvar: float,
    solve_histogram: List[float] | None,
    fallbacks: int | None,
    notes: str | None,
) -> Dict[str, Any]:
    """Assemble a normalized payload for rendering.

    pnl_q/pnl_c can be list (series) or single float for latest; we normalize to series in 'series' and include totals.
    """
    def _to_series(x) -> List[float]:
        if x is None:
            return []
        if isinstance(x, (int, float)):
            return [float(x)]
        try:
            return [float(v) for v in x]
        except Exception:
            return []

    ser_q = _to_series(pnl_q)
    ser_c = _to_series(pnl_c)
    total_q = float(sum(ser_q)) if ser_q else float(pnl_q) if isinstance(pnl_q, (int, float)) else 0.0
    total_c = float(sum(ser_c)) if ser_c else float(pnl_c) if isinstance(pnl_c, (int, float)) else 0.0
    chart_uri = _render_chart_base64(ser_q, ser_c, solve_histogram or [])
    # Scan explanations for the date (best-effort)
    expl_dir = os.getenv("EXPL_DIR", os.path.join("out", "explanations"))
    expl_list: List[str] = []
    try:
        d = Path(expl_dir) / date
        if d.exists():
            expl_list = [p.name for p in sorted(d.glob("*.md"))]
    except Exception:
        expl_list = []

    # Try to load attribution summary for this date
    attribution: Dict[str, Any] | None = None
    try:
        from analytics.attribution import load_daily_attribution  # type: ignore

        attribution = load_daily_attribution(date)
    except Exception:
        attribution = None

    # Scenario stress (optional): load inputs from reports/scenario_input.json
    scenario_stress = None
    try:
        import json as _json
        from research.macro.simulator import run_scenarios  # type: ignore

        scen_path = os.path.join("reports", "scenario_input.json")
        if os.path.exists(scen_path):
            js = _json.loads(open(scen_path, "r", encoding="utf-8").read())
            w = js.get("weights") or []
            Sigma = js.get("cov") or []
            scens = js.get("scenarios") or [
                {"rates_up": 0.5, "oil_shock": 0.2, "recession_prob": 0.3},
                {"rates_up": -0.2, "oil_shock": -0.1, "recession_prob": 0.1},
            ]
            if w and Sigma:
                scenario_stress = run_scenarios(w, Sigma, scens)
    except Exception:
        scenario_stress = None

    return {
        "date": date,
        "allocs": allocs or [],
        "pnl": {
            "series_q": ser_q,
            "series_c": ser_c,
            "total_q": total_q,
            "total_c": total_c,
        },
        "risk": {"var": float(var or 0.0), "cvar": float(cvar or 0.0)},
        "solve": {"hist_ms": list(solve_histogram or []), "fallbacks": int(fallbacks or 0)},
        "notes": notes or "",
        "chart_uri": chart_uri,
        "explanations": expl_list,
        "attribution": attribution,
        "scenario_stress": scenario_stress,
    }


def render_html(payload: Dict[str, Any]) -> str:
    """Render payload to HTML using templates/report.html.j2 (fallback inline if missing)."""
    tmpl_path = os.path.join("templates", "report.html.j2")
    try:
        from jinja2 import Environment, FileSystemLoader  # type: ignore

        if os.path.exists(tmpl_path):
            env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
            tmpl = env.get_template("report.html.j2")
            return tmpl.render(**payload)
    except Exception:
        pass

    # Fallback minimal HTML
    return f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Daily Report</title>
<style>body{{font-family:Arial,sans-serif;margin:16px}} .kpi{{display:flex;gap:20px}} .card{{border:1px solid #ddd;padding:12px;border-radius:8px}}</style>
</head>
<body>
  <h1>Daily Report — {payload.get('date','')}</h1>
  <div class="kpi">
    <div class="card"><b>Total PnL (Q)</b><br/>{payload.get('pnl',{}).get('total_q',0):.6f}</div>
    <div class="card"><b>Total PnL (C)</b><br/>{payload.get('pnl',{}).get('total_c',0):.6f}</div>
    <div class="card"><b>VaR</b><br/>{payload.get('risk',{}).get('var',0):.6f}</div>
    <div class="card"><b>CVaR</b><br/>{payload.get('risk',{}).get('cvar',0):.6f}</div>
  </div>
  <h3>Allocations</h3>
  <pre>{json.dumps(payload.get('allocs',[]), indent=2)}</pre>
  <h3>Chart</h3>
  {('<img src="'+payload.get('chart_uri','')+'" style="max-width:100%"/>') if payload.get('chart_uri') else '<i>No chart</i>'}
  <h3>Quantum Solve / Fallbacks</h3>
  <div class="card">Fallbacks: {payload.get('solve',{}).get('fallbacks',0)}</div>
  <h3>Notes</h3>
  <pre>{payload.get('notes','')}</pre>
  <h3>Trade Explanations</h3>
  {('<ul>' + ''.join([f'<li><a href="out/explanations/{payload.get('date','')}/{fn}">{fn}</a></li>' for fn in payload.get('explanations', [])]) + '</ul>') if payload.get('explanations') else '<i>No trade explanations found</i>'}
  <h3>Attribution</h3>
  {('<b>Total PnL:</b> ' + str(payload.get('attribution',{}).get('total_pnl','')) + '<br/>'
    + '<b>Top Contributors:</b><ul>' + ''.join([f"<li>{k}: {v:.6f}</li>" for k,v in (payload.get('attribution',{}).get('top_contributors',[]) or [])]) + '</ul>'
    + '<b>Negative Drags:</b><ul>' + ''.join([f"<li>{k}: {v:.6f}</li>" for k,v in (payload.get('attribution',{}).get('negative_drags',[]) or [])]) + '</ul>'
   ) if payload.get('attribution') else '<i>No attribution available</i>'}
  <h3>Scenario Stress</h3>
  {(
    '<b>Baseline VaR:</b> ' + ('%.6f' % payload.get('scenario_stress',{}).get('baseline',{}).get('VaR',0)) + '<br/>' +
    '<b>Top Scenarios:</b><ul>' + ''.join([
      f"<li>ΔVaR={s.get('delta_VaR',0):.6f} | ΔCVaR={s.get('delta_CVaR',0):.6f} | {s.get('input')}</li>" for s in (payload.get('scenario_stress',{}).get('scenarios',[])[:3])
    ]) + '</ul>'
  ) if payload.get('scenario_stress') else '<i>No scenario stress available</i>'}
  <h3>Sentiment Snapshot</h3>
  {('<pre>'+json.dumps(payload.get('sentiment',{}), indent=2)+'</pre>') if payload.get('sentiment') else '<i>No sentiment snapshot</i>'}
  <h3>Arbitrage Summary</h3>
  {('<b>Count:</b> ' + str(payload.get('arbitrage',{}).get('count',0)) + '<br/>' + '<pre>'+json.dumps(payload.get('arbitrage',{}).get('top',[]), indent=2)+'</pre>') if payload.get('arbitrage') else '<i>No arbitrage summary</i>'}
  <h3>Liquidity Guard Blocks</h3>
  {('<pre>'+json.dumps(payload.get('liquidity_blocks',{}), indent=2)+'</pre>') if payload.get('liquidity_blocks') else '<i>No data</i>'}
  <h3>Flash-crash Events</h3>
  {('<pre>'+json.dumps(payload.get('flash_crash',{}), indent=2)+'</pre>') if payload.get('flash_crash') else '<i>No data</i>'}
  <h3>Ensemble λ cap</h3>
  {str(payload.get('lambda_cap')) if payload.get('lambda_cap') is not None else '<i>None</i>'}
</body></html>
"""


def save_pdf(html: str, out_path: str) -> bool:
    """Render HTML to PDF with weasyprint. Returns True on success."""
    try:
        from weasyprint import HTML  # type: ignore

        _ensure_dir(out_path)
        HTML(string=html).write_pdf(out_path)
        return True
    except Exception:
        return False
