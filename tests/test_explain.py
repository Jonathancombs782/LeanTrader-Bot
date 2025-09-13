from __future__ import annotations

import os
from pathlib import Path

from reporting.explain import write_explanation_markdown


def test_write_explanation_markdown(tmp_path: Path):
    order = {
        "id": "test-123",
        "symbol": "ETH/USDT",
        "side": "buy",
        "price": 2500.0,
        "qty": 0.1,
        "ts": 1_700_000_000,
        "route": "spot",
    }
    context = {
        "regime": "calm",
        "selector": "unit-test",
        "key_signals": [{"name": "prob", "score": 0.7}],
        "hype_score": 0.2,
        "expected_slippage_bps": 3.0,
    }
    base = tmp_path / "expl"
    path = write_explanation_markdown(order, context, base_dir=str(base))
    assert path is not None
    p = Path(path)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Trade Explanation" in text and "ETH/USDT" in text

