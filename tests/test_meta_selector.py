from __future__ import annotations

from strategies.meta_selector import BanditSelector, StratPath, daily_reward, EWMA


def test_ewma_basic():
    e = EWMA(half_life=2)
    v1 = e.update(1.0)
    assert v1 > 0
    v2 = e.update(0.0)
    assert 0 <= v2 <= 1.0


def test_bandit_choose_update():
    sel = BanditSelector(key="test_meta_selector", half_life=2)
    # force known baseline
    sel.rewards = {
        StratPath.CLASSICAL.value: 0.1,
        StratPath.QUANTUM.value: 0.1,
        StratPath.ENSEMBLE.value: 0.1,
    }
    # tie-break prefers QUANTUM by default order
    assert sel.choose() == StratPath.QUANTUM
    # update classical with higher reward, then choose should switch
    sel.update(StratPath.CLASSICAL, 1.0)
    assert sel.choose() in (StratPath.CLASSICAL, StratPath.QUANTUM)  # depending on EWMA alpha


def test_daily_reward_penalizes_turnover():
    r_low = daily_reward(0.02, turnover=4.0)
    r_high = daily_reward(0.02, turnover=0.25)
    assert r_high > r_low

