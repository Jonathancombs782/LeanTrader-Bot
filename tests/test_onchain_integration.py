from __future__ import annotations

import json
import os
from pathlib import Path

from news_adapter import _merge_onchain_fusion, ONCHAIN_EVENTS_ENV


def test_merge_onchain_fusion_from_file(tmp_path: Path, monkeypatch):
    evts = [
        {"type": "whale_transfer", "token": "ETH", "size_usd": 900_000, "direction": "out"},
        {"type": "dex_volume_spike", "asset": "BTC", "zscore": 4.2},
    ]
    p = tmp_path / "onchain.json"
    p.write_text(json.dumps(evts), encoding="utf-8")
    monkeypatch.setenv(ONCHAIN_EVENTS_ENV, str(p))
    base = {"ETH/USDT": 0}
    merged = _merge_onchain_fusion(base)
    assert "ETH/USDT" in merged
    assert merged["ETH/USDT"] in (-1, 0, 1)

