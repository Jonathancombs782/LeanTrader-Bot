from __future__ import annotations

from ops.ramp import RampState, RampPolicy, Mode


def test_promotion_from_paper():
    st = RampState(mode=Mode.PAPER, start_date="2025-01-01", stats={"days": 15, "drawdown": 0.01, "slippage_bps_p90": 10.0, "reject_rate": 0.01})
    pol = RampPolicy(min_paper_days=10)
    assert st.consider_promotion(pol) is True


def test_no_promotion_due_to_slippage():
    st = RampState(mode=Mode.PAPER, stats={"days": 15, "drawdown": 0.01, "slippage_bps_p90": 40.0, "reject_rate": 0.01})
    pol = RampPolicy()
    assert st.consider_promotion(pol) is False


def test_rollback_from_tiny():
    st = RampState(mode=Mode.TINY_PROD, stats={"days": 5, "drawdown": 0.05, "slippage_bps_p90": 10.0, "reject_rate": 0.01})
    pol = RampPolicy(max_drawdown_tiny=0.03)
    rb, reason = st.consider_rollback(pol)
    assert rb is True
    assert "drawdown" in reason

