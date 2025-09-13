from __future__ import annotations

from web3.guards import estimate_price_impact, is_safe_gas, token_safety_checks, is_safe_price_impact


def test_price_impact_calc():
    impact = estimate_price_impact(100.0, 1000.0, 1000.0)
    # should be a fraction in (0,1)
    assert 0.0 < impact < 1.0
    # sanity: small amount => higher remaining fraction => impact closer to 1 than large amount
    impact_small = estimate_price_impact(10.0, 1000.0, 1000.0)
    assert impact_small > impact  # per given formula
    assert is_safe_price_impact(impact, max_impact=0.95) is True


def test_gas_safety():
    assert is_safe_gas(50.0, 30.0) is True
    assert is_safe_gas(50.0, 60.0) is False


def test_token_safety_flags_block():
    meta = {
        "owner_can_mint": True,
        "trading_paused": False,
        "blacklistable": False,
        "taxed_transfer": False,
        "proxy_upgradable": False,
        "liquidity_usd": 1000.0,
        "min_liquidity_usd": 2000.0,
    }
    res = token_safety_checks(meta)
    assert res["ok"] is False
    assert any("flag:owner_can_mint" in r or "liquidity_usd_lt_min" in r for r in res["reasons"])  

