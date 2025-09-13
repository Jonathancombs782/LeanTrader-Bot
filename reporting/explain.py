from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


try:
    from prometheus_client import Counter  # type: ignore

    EXPL_FILES_WRITTEN = Counter(
        "expl_files_written_total", "Trade explanation files written", []
    )
except Exception:  # pragma: no cover
    class _Noop:
        def inc(self, *_: Any, **__: Any) -> None:
            pass

    EXPL_FILES_WRITTEN = _Noop()  # type: ignore


def build_trade_explanation(order: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
    """Assemble a normalized explanation payload for a trade.

    Keys included (best-effort):
      - id, symbol, side, qty, price, ts
      - regime: calm|storm|unknown
      - selector: meta-selector choice, model or rule used
      - key_signals: list of dicts [{name, score, reason}]
      - sentiment: snapshot dict (news, onchain, hype_score)
      - risk_caps: dict of guards applied (liquidity, mempool, calendar, limits)
      - expected_slippage_bps: float
      - objective_value: float|None (e.g., QAOA objective)
      - alternatives_rejected: list of strings or dicts
      - route: public|private|futures|spot|dex
    """
    # Extract basics from order
    oid = str(order.get("id") or order.get("orderId") or order.get("tx_hash") or context.get("id") or "")
    sym = str(order.get("symbol") or context.get("symbol") or "").upper()
    side = str(order.get("side") or context.get("side") or "").lower()
    qty = order.get("qty") or order.get("size") or context.get("qty")
    price = order.get("price") or context.get("price")
    ts = int(order.get("ts") or context.get("ts") or 0)
    route = str(order.get("route") or context.get("route") or "").lower()

    # Heuristics / passthrough context
    regime = context.get("regime") or context.get("regime_now") or "unknown"
    selector = context.get("selector") or context.get("model") or context.get("strategy") or "unknown"
    key_signals = context.get("key_signals") or context.get("signals") or []
    if isinstance(key_signals, dict):
        key_signals = [
            {"name": k, "score": float(v) if v is not None else 0.0} for k, v in key_signals.items()
        ]
    # Sentiment snapshot from available sources
    sentiment = {
        "news_bias": context.get("news_bias"),
        "onchain_sent": context.get("onchain_sentiment"),
        "hype_score": context.get("hype_score"),
    }
    # Risk caps and guards
    risk_caps = {
        "liquidity": context.get("liquidity_guard"),
        "mempool": context.get("mempool_risk"),
        "calendar": context.get("calendar_guard"),
        "limits": context.get("risk_limits"),
    }
    exp_slip = context.get("expected_slippage_bps") or context.get("slippage_bps") or 0.0
    objective = context.get("objective_value") or context.get("qaoa_objective")
    alt = context.get("alternatives_rejected") or context.get("alts") or []

    return {
        "id": oid,
        "symbol": sym,
        "side": side,
        "qty": qty,
        "price": price,
        "ts": ts,
        "route": route,
        "regime": regime,
        "selector": selector,
        "key_signals": key_signals,
        "sentiment": sentiment,
        "risk_caps": risk_caps,
        "expected_slippage_bps": float(exp_slip or 0.0),
        "objective_value": objective,
        "alternatives_rejected": alt if isinstance(alt, list) else [alt],
    }


def render_markdown(expl: Mapping[str, Any]) -> str:
    items = [
        f"# Trade Explanation — {expl.get('symbol','')} {expl.get('side','')}\n",
        f"- ID: {expl.get('id','')}\n",
        f"- Route: {expl.get('route','')}\n",
        f"- Qty/Price: {expl.get('qty','?')} @ {expl.get('price','?')}\n",
        f"- Regime: {expl.get('regime','unknown')}\n",
        f"- Selector: {expl.get('selector','unknown')}\n",
        f"- Expected Slippage: {expl.get('expected_slippage_bps',0):.2f} bps\n",
    ]
    # Key signals
    ks = expl.get("key_signals") or []
    if ks:
        items.append("\n## Key Signals\n")
        for s in ks[:10]:
            name = str(s.get("name") or s.get("id") or "?")
            sc = s.get("score")
            reason = s.get("reason")
            items.append(f"- {name}: {sc} {('— '+reason) if reason else ''}\n")
    # Sentiment
    sent = expl.get("sentiment") or {}
    items.append("\n## Sentiment Snapshot\n")
    items.append(f"- News bias: {sent.get('news_bias')}\n")
    items.append(f"- On-chain: {sent.get('onchain_sent')}\n")
    items.append(f"- Hype score: {sent.get('hype_score')}\n")
    # Risk caps
    caps = expl.get("risk_caps") or {}
    items.append("\n## Risk Caps Applied\n")
    for k, v in caps.items():
        items.append(f"- {k}: {json.dumps(v, ensure_ascii=False)}\n")
    # Objective
    if expl.get("objective_value") is not None:
        items.append("\n## Objective (QAOA)\n")
        items.append(f"- value: {expl.get('objective_value')}\n")
    # Alternatives
    al = expl.get("alternatives_rejected") or []
    if al:
        items.append("\n## Alternatives Rejected\n")
        for e in al[:10]:
            items.append(f"- {e}\n")
    return "".join(items)


def render_html(expl: Mapping[str, Any]) -> str:
    # Prefer Jinja template if present
    try:
        from jinja2 import Environment, FileSystemLoader  # type: ignore

        tmpl_path = os.path.join("templates", "expl_trade.html.j2")
        if os.path.exists(tmpl_path):
            env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
            tmpl = env.get_template("expl_trade.html.j2")
            return tmpl.render(**expl)
    except Exception:
        pass
    # Fallback simple HTML from markdown
    md = render_markdown(expl)
    html = md.replace("\n# ", "\n<h1>").replace("\n## ", "\n<h2>")
    html = html.replace("\n", "<br/>")
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Trade Explanation</title></head><body>{html}</body></html>"


def write_explanation_markdown(
    order: Mapping[str, Any],
    context: Mapping[str, Any],
    base_dir: str = "out/explanations",
) -> Optional[str]:
    """Write per-trade markdown explanation to date folder. Returns path or None."""
    try:
        expl = build_trade_explanation(order, context)
        date = _dt.datetime.utcfromtimestamp(int(expl.get("ts") or 0) or int(_dt.datetime.utcnow().timestamp())).strftime(
            "%Y-%m-%d"
        )
        oid = expl.get("id") or f"{expl.get('symbol','')}-{int(_dt.datetime.utcnow().timestamp())}"
        folder = Path(base_dir) / date
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{oid}.md"
        path.write_text(render_markdown(expl), encoding="utf-8")
        # Also write HTML alongside
        try:
            (folder / f"{oid}.html").write_text(render_html(expl), encoding="utf-8")
        except Exception:
            pass
        # Sensitive snapshot (selector, signals, risk_caps) encrypted at rest
        try:
            from security.vault import secure_write  # type: ignore

            sensitive = {
                "id": expl.get("id"),
                "symbol": expl.get("symbol"),
                "selector": expl.get("selector"),
                "key_signals": expl.get("key_signals"),
                "risk_caps": expl.get("risk_caps"),
                "sentiment": expl.get("sentiment"),
            }
            secure_write(str(folder / f"{oid}.sensitive.enc"), sensitive)
        except Exception:
            pass
        try:
            EXPL_FILES_WRITTEN.inc()
        except Exception:
            pass
        return str(path)
    except Exception:
        return None


def scan_explanations_for_date(date: str, base_dir: str = "out/explanations") -> List[str]:
    d = Path(base_dir) / date
    if not d.exists():
        return []
    return [str(p) for p in sorted(d.glob("*.md"))]


__all__ = [
    "EXPL_FILES_WRITTEN",
    "build_trade_explanation",
    "render_markdown",
    "render_html",
    "write_explanation_markdown",
    "scan_explanations_for_date",
]
