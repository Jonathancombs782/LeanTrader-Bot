from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


@dataclass
class Candidate:
    asset: str
    hypothesis: str
    change: str
    rationale: List[str]
    score: float
    expected_risk: float
    backtest: Optional[Dict[str, Any]] = None


def scan_features(
    *,
    features: Optional[Any] = None,
    attribution: Mapping[str, float] | None = None,
    sentiment: Mapping[str, Any] | None = None,
    hype: Mapping[str, float] | None = None,
    top_k: int = 5,
) -> List[Candidate]:
    """Heuristic scan: combine attribution, sentiment, hype to propose actions.

    - High positive attribution + positive sentiment/hype -> increase allocation or widen TP.
    - Negative attribution + negative sentiment -> reduce exposure or tighten stops.
    - Divergence (positive attribution, negative sentiment) -> add protective hedge.
    """
    attribution = attribution or {}
    sentiment = sentiment or {}
    hype = hype or {}
    # normalize keys to uppercase symbols
    def up_keys(d):
        return {str(k).upper(): v for k, v in d.items()}

    A = up_keys(attribution)
    S = up_keys(sentiment)
    H = up_keys(hype)

    # rank by |attribution|
    ranked = sorted(A.items(), key=lambda kv: abs(kv[1]), reverse=True)
    cands: List[Candidate] = []
    for sym, contrib in ranked[: max(3, top_k * 2)]:
        s = float(S.get(sym, 0))  # -1..+1
        h = float(H.get(sym, 0.0))
        rationale: List[str] = []
        if contrib > 0 and s >= 0:
            hyp = f"Momentum persists in {sym} supported by positive sentiment"
            chg = "Increase allocation slightly; widen TP by +10%"
            rationale = [f"Attribution +{contrib:.4f}", f"Sentiment {s:+.0f}", f"Hype {h:.3f}"]
            score = abs(contrib) * (1.0 + 0.2 * s) * (1.0 + 0.1 * min(1.0, h))
            risk = 0.4 + 0.6 * min(1.0, max(0.0, h))
        elif contrib < 0 and s <= 0:
            hyp = f"Alpha underperforming in {sym} with bearish sentiment"
            chg = "Tighten stops -10%; reduce position size by 20%"
            rationale = [f"Attribution {contrib:.4f}", f"Sentiment {s:+.0f}", f"Hype {h:.3f}"]
            score = abs(contrib) * (1.0 + 0.2 * abs(s))
            risk = 0.6 + 0.5 * min(1.0, max(0.0, h))
        else:
            hyp = f"Divergence in {sym}: attribution {contrib:+.4f} vs sentiment {s:+.0f}"
            chg = "Add small protective hedge or reduce leverage"
            rationale = [f"Attribution {contrib:.4f}", f"Sentiment {s:+.0f}", f"Hype {h:.3f}"]
            score = 0.6 * abs(contrib) * (1.0 + 0.1 * abs(s))
            risk = 0.5
        cands.append(Candidate(asset=sym, hypothesis=hyp, change=chg, rationale=rationale, score=score, expected_risk=risk))

    # keep top_k by score
    cands.sort(key=lambda c: c.score, reverse=True)
    return cands[:top_k]


def quick_backtest(c: Candidate, series: Optional[Sequence[float]] = None, lookback: int = 120) -> Dict[str, Any]:
    """Compute a toy backtest stat; if price series provided, compute simple momentum PnL proxy.

    Returns {sharpe, hitrate, days}.
    """
    if not series or len(series) < 10:
        return {"sharpe": 0.0, "hitrate": 0.5, "days": lookback}
    xs = list(map(float, series[-lookback:]))
    rets = [(xs[i] - xs[i - 1]) / xs[i - 1] for i in range(1, len(xs))]
    # align action sign: if change contains "increase", we assume long; if "reduce" -> risk-off
    sign = +1.0 if ("increase" in c.change.lower()) else -1.0 if ("reduce" in c.change.lower()) else 0.5
    pnl = [sign * r for r in rets]
    import statistics

    mu = statistics.fmean(pnl) if pnl else 0.0
    sd = statistics.pstdev(pnl) if len(pnl) > 1 else 0.0
    sharpe = (mu / (sd + 1e-12)) * math.sqrt(252) if sd > 0 else 0.0
    hitrate = sum(1 for r in pnl if r > 0) / len(pnl)
    return {"sharpe": sharpe, "hitrate": hitrate, "days": len(pnl)}


def backtest_candidates(cands: List[Candidate], price_series: Mapping[str, Sequence[float]] | None = None) -> List[Candidate]:
    out: List[Candidate] = []
    for c in cands:
        series = (price_series or {}).get(c.asset)
        bt = quick_backtest(c, series)
        c.backtest = bt
        out.append(c)
    # sort by a composite score (score * sharpe adjustment)
    def comp(x: Candidate) -> float:
        sh = float((x.backtest or {}).get("sharpe", 0.0))
        return x.score * (1.0 + 0.2 * max(0.0, sh))

    out.sort(key=comp, reverse=True)
    return out


def render_markdown_cards(cands: List[Candidate]) -> List[str]:
    cards: List[str] = []
    for c in cands:
        bt = c.backtest or {}
        lines = [
            f"### {c.asset}: {c.hypothesis}",
            f"- Change: {c.change}",
            f"- Evidence: {'; '.join(c.rationale)}",
            f"- Score: {c.score:.3f}  Risk: {c.expected_risk:.2f}",
            f"- Backtest: Sharpe={bt.get('sharpe',0):.2f}  Hitrate={bt.get('hitrate',0):.2%}  Days={bt.get('days',0)}",
            f"- Required Changes: Update params or rules accordingly; run A/B in paper for a week.",
        ]
        cards.append("\n".join(lines))
    return cards


def slack_blocks_for_ideas(cards: List[str]) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []
    for md in cards:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": md}})
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "value": "approve", "action_id": "idea_approve"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "value": "reject", "action_id": "idea_reject"},
                ],
            }
        )
    return {"blocks": blocks}


def write_slack_stub(cards: List[str], out: str = "runtime/ideas_slack.json") -> str:
    payload = slack_blocks_for_ideas(cards)
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(p)


def generate_ideas(
    *,
    attribution_agg: Mapping[str, float] | None,
    sentiment: Mapping[str, Any] | None,
    hype_scores_path: str = "runtime/hype_scores.json",
    price_cache_path: str = "runtime/price_cache.json",
    top_k: int = 3,
) -> Dict[str, Any]:
    # Load hype and price cache if available
    hype: Dict[str, float] = {}
    price: Dict[str, List[float]] = {}
    try:
        if Path(hype_scores_path).exists():
            hype = (json.loads(Path(hype_scores_path).read_text(encoding="utf-8")) or {}).get("scores", {})
    except Exception:
        hype = {}
    try:
        if Path(price_cache_path).exists():
            price = json.loads(Path(price_cache_path).read_text(encoding="utf-8")) or {}
    except Exception:
        price = {}

    cands = scan_features(features=None, attribution=attribution_agg or {}, sentiment=sentiment or {}, hype=hype, top_k=top_k)
    cands = backtest_candidates(cands, price)
    cards = render_markdown_cards(cands)
    write_slack_stub(cards)
    return {"candidates": [c.__dict__ for c in cands], "cards": cards}


__all__ = [
    "Candidate",
    "scan_features",
    "quick_backtest",
    "backtest_candidates",
    "render_markdown_cards",
    "slack_blocks_for_ideas",
    "write_slack_stub",
    "generate_ideas",
]

