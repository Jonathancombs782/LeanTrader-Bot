from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _iso_week_range(iso_week: str) -> Tuple[dt.date, dt.date]:
    # iso_week like '2025-W07'
    year_str, week_str = iso_week.split('-W')
    year, week = int(year_str), int(week_str)
    # Monday
    d0 = dt.date.fromisocalendar(year, week, 1)
    d6 = d0 + dt.timedelta(days=6)
    return d0, d6


def _daterange(d0: dt.date, d1: dt.date) -> List[str]:
    out = []
    cur = d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur = cur + dt.timedelta(days=1)
    return out


def _load_json_safe(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _sharpe(pnls: Sequence[float]) -> float:
    if not pnls:
        return 0.0
    import statistics

    mean = statistics.fmean(pnls)
    st = statistics.pstdev(pnls) or 0.0
    if st <= 0:
        return 0.0
    # Assume daily series; annualize to 252 trading days
    return float((mean / st) * (252 ** 0.5))


def _max_drawdown(series: Sequence[float]) -> float:
    if not series:
        return 0.0
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for x in series:
        cum += float(x)
        peak = max(peak, cum)
        dd = cum - peak
        mdd = min(mdd, dd)
    return float(mdd)


def gather_weekly_stats(iso_week: str) -> Dict[str, Any]:
    d0, d6 = _iso_week_range(iso_week)
    dates = _daterange(d0, d6)

    # Attribution per day
    attrib_dir = Path('reports') / 'attribution'
    daily = []
    for d in dates:
        p = attrib_dir / f'{d}.json'
        if p.exists():
            js = _load_json_safe(p) or {}
            daily.append(js)

    daily_pnl = [float(x.get('total_pnl', 0.0)) for x in daily]
    sharpe = _sharpe(daily_pnl) if daily_pnl else 0.0
    mdd = _max_drawdown(daily_pnl)

    # Aggregate attribution contributions by component
    agg_contrib: Dict[str, float] = {}
    for js in daily:
        for k, v in (js.get('contributions') or {}).items():
            agg_contrib[k] = agg_contrib.get(k, 0.0) + float(v)

    # Regime distribution from trade explanations (best-effort)
    expl_dir = Path('out') / 'explanations'
    regimes: Dict[str, int] = {}
    for d in dates:
        day_dir = expl_dir / d
        if not day_dir.exists():
            continue
        for md in day_dir.glob('*.md'):
            try:
                txt = md.read_text(encoding='utf-8')
                # crude parse: '- Regime: X' line
                for line in txt.splitlines():
                    if line.lower().startswith('- regime:'):
                        r = line.split(':', 1)[1].strip().lower()
                        regimes[r] = regimes.get(r, 0) + 1
                        break
            except Exception:
                continue

    # Solve stats and fallbacks from daily report summary if present (best-effort)
    # Expected at reports/summary/YYYY-MM-DD.json (customizable later)
    solve_ms: List[float] = []
    fallbacks = 0
    for d in dates:
        p = Path('reports') / 'summary' / f'{d}.json'
        js = _load_json_safe(p)
        if not js:
            continue
        solve_ms += [float(x) for x in (js.get('solve_ms') or []) if isinstance(x, (int, float))]
        fallbacks += int(js.get('fallbacks') or 0)

    # Notable sentiment and on-chain events
    sentiment = {}
    try:
        from news_adapter import _load_json, CRYPTO_PATH  # type: ignore

        sent_js = _load_json(Path(CRYPTO_PATH)) or {}
        sentiment = sent_js.get('bias', {})
    except Exception:
        pass

    onchain_events = []
    try:
        path = os.getenv('ONCHAIN_EVENTS_PATH', 'runtime/onchain_events.json')
        if Path(path).exists():
            onchain_events = _load_json_safe(Path(path)) or []
            # keep only last 1000 for report size
            onchain_events = onchain_events[-1000:]
    except Exception:
        pass

    return {
        'week': iso_week,
        'dates': dates,
        'pnl': {
            'daily': daily_pnl,
            'total': float(sum(daily_pnl)),
            'sharpe': sharpe,
            'max_drawdown': mdd,
        },
        'attribution_agg': agg_contrib,
        'regimes': regimes,
        'solve_ms': solve_ms,
        'fallbacks': fallbacks,
        'sentiment': sentiment,
        'onchain_events': onchain_events,
    }


def _render_jinja(template: str, ctx: Dict[str, Any]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader  # type: ignore

        env = Environment(loader=FileSystemLoader('templates'), autoescape=False)
        tmpl = env.get_template(template)
        return tmpl.render(**ctx)
    except Exception:
        # minimal fallback HTML
        return f"<html><body><pre>{json.dumps(ctx, indent=2)}</pre></body></html>"


def render_weekly_html(payload: Dict[str, Any]) -> str:
    if Path('templates/weekly_paper.html.j2').exists():
        return _render_jinja('weekly_paper.html.j2', payload)
    return _render_jinja('', payload)  # fallback


def render_weekly_tex(payload: Dict[str, Any]) -> str:
    if Path('templates/weekly_paper.tex.j2').exists():
        return _render_jinja('weekly_paper.tex.j2', payload)
    # fallback minimal TeX
    return (r"\documentclass{article}\begin{document}"
            + json.dumps(payload)
            + r"\end{document}")


def write_weekly_report(iso_week: str, out_prefix: str = 'out/reports/weekly') -> Dict[str, Optional[str]]:
    payload = gather_weekly_stats(iso_week)
    # Generate top ideas (best-effort)
    try:
        from research.idea_generator import generate_ideas  # type: ignore

        ideas = generate_ideas(
            attribution_agg=payload.get('attribution_agg') or {},
            sentiment=payload.get('sentiment') or {},
        )
        payload['ideas'] = ideas
    except Exception:
        payload['ideas'] = None
    # Always write HTML
    html = render_weekly_html(payload)
    out_dir = Path(out_prefix).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = f"{out_prefix}_{iso_week}.html"
    Path(out_html).write_text(html, encoding='utf-8')

    # Try weasyprint HTML->PDF
    out_pdf = f"{out_prefix}_{iso_week}.pdf"
    pdf_ok = False
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html).write_pdf(out_pdf)
        pdf_ok = True
    except Exception:
        # Try tectonic LaTeX
        try:
            tex = render_weekly_tex(payload)
            tex_path = Path(out_prefix + f'_{iso_week}.tex')
            tex_path.write_text(tex, encoding='utf-8')
            import subprocess

            subprocess.run(['tectonic', str(tex_path)], check=True)
            # tectonic outputs PDF next to tex with same stem
            gen_pdf = tex_path.with_suffix('.pdf')
            if gen_pdf.exists():
                gen_pdf.replace(out_pdf)
                pdf_ok = True
        except Exception:
            pdf_ok = False

    return {'html': out_html, 'pdf': out_pdf if pdf_ok else None}


__all__ = ['gather_weekly_stats', 'render_weekly_html', 'render_weekly_tex', 'write_weekly_report']
