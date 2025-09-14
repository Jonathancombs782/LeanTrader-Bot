from __future__ import annotations

from signals.onchain_flows import (
    whale_transfer_detector,
    pool_imbalance_detector,
    dex_volume_spike,
    sentiment_fusion,
)


def test_whale_transfer_and_fusion():
    evts = whale_transfer_detector(
        [
            {"token": "ETH", "usd_value": 800_000, "direction": "out", "ts": 1},
            {"token": "ETH", "usd_value": 10_000, "direction": "out", "ts": 2},  # filtered
        ],
        min_usd=500_000,
    )
    assert len(evts) == 1
    feats = sentiment_fusion(evts)
    assert "ETH" in feats and feats["ETH"]["buzz"] > 0


def test_pool_imbalance_detector():
    evts = pool_imbalance_detector(
        [
            {
                "pool": "ETH/USDC",
                "reserve0": 5000,
                "reserve1": 8_000_000,
                "prev_reserve0": 8000,
                "prev_reserve1": 12_000_000,
                "token0": "ETH",
                "token1": "USDC",
            }
        ],
        threshold_pct=10.0,
    )
    assert len(evts) == 1
    assert evts[0]["type"] == "pool_imbalance"


def test_dex_volume_spike_zscore():
    vols = [100, 110, 95, 105, 98, 102, 99, 101, 97, 103] * 6
    vols.append(200)  # current spike
    evts = dex_volume_spike("ETH", vols, zscore_threshold=3.0, window=48)
    assert len(evts) == 1
    feats = sentiment_fusion(evts)
    assert feats.get("ETH", {}).get("buzz", 0) > 0

