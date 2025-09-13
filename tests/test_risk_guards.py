from __future__ import annotations

from risk.guards import GuardState, RiskLimits, should_halt_trading


def test_no_breach():
    st = GuardState()
    st.update_equity(1000.0)
    st.record_fill("BTCUSDT", 5.0)
    lim = RiskLimits(max_loss_per_symbol=0.5, max_daily_loss=0.5, max_account_drawdown=0.9, pct=True)
    halt, reasons = should_halt_trading(st, lim)
    assert halt is False
    assert reasons == []


def test_per_symbol_breach():
    st = GuardState()
    st.update_equity(1000.0)
    st.record_fill("BTCUSDT", -25.0)  # -25 loss
    lim = RiskLimits(max_loss_per_symbol=0.02, max_daily_loss=0.5, max_account_drawdown=0.9, pct=True)  # 2% = $20
    halt, reasons = should_halt_trading(st, lim)
    assert halt is True
    assert any("per_symbol_loss" in r for r in reasons)


def test_daily_loss_breach():
    st = GuardState()
    st.update_equity(1000.0)
    st.record_fill("ETHUSDT", -10.0)
    st.record_fill("BTCUSDT", -15.0)
    lim = RiskLimits(max_loss_per_symbol=0.9, max_daily_loss=0.02, max_account_drawdown=0.9, pct=True)  # 2% = $20
    halt, reasons = should_halt_trading(st, lim)
    assert halt is True
    assert any("daily_loss" in r for r in reasons)


def test_drawdown_breach():
    st = GuardState()
    st.update_equity(1000.0)
    st.update_equity(850.0)  # 15% DD
    lim = RiskLimits(max_loss_per_symbol=0.9, max_daily_loss=0.9, max_account_drawdown=0.10, pct=True)  # 10%
    halt, reasons = should_halt_trading(st, lim)
    assert halt is True
    assert any("drawdown" in r for r in reasons)

