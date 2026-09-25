"""Hard risk limits. These are gates, not guidelines.

Every check that fails raises RiskBreach — the engine logs it and the trade
never happens. No overrides, no "just this once".
"""
from __future__ import annotations

from dataclasses import dataclass


class RiskBreach(Exception):
    """Raised when a trade or state violates a risk limit."""

    def __init__(self, limit: str, detail: str):
        self.limit = limit
        super().__init__(f"[{limit}] {detail}")


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: float = 2.0   # % of equity risked on one trade
    max_portfolio_heat_pct: float = 6.0   # % of equity in total open risk
    max_position_pct: float = 25.0        # max notional per symbol, % of equity
    daily_loss_limit_pct: float = 4.0     # halt new trades after -4% day
    kill_switch_drawdown_pct: float = 15.0  # halt everything after -15% from peak


def check_new_trade(
    limits: RiskLimits,
    *,
    equity: float,
    trade_risk_amount: float,
    trade_notional: float,
    open_risk_amount: float,
    symbol_open_notional: float,
    daily_pnl_pct: float,
    drawdown_pct: float,
) -> None:
    """Gate a prospective trade. Raises RiskBreach on any violation."""
    if equity <= 0:
        raise RiskBreach("equity", "equity is not positive — refusing to trade")
    if drawdown_pct >= limits.kill_switch_drawdown_pct:
        raise RiskBreach(
            "kill_switch",
            f"drawdown {drawdown_pct:.2f}% >= kill switch "
            f"{limits.kill_switch_drawdown_pct:.2f}% — all trading halted",
        )
    if daily_pnl_pct <= -limits.daily_loss_limit_pct:
        raise RiskBreach(
            "daily_loss_halt",
            f"daily PnL {daily_pnl_pct:.2f}% <= -{limits.daily_loss_limit_pct:.2f}% "
            "— no new trades today",
        )
    max_trade_risk = equity * limits.max_risk_per_trade_pct / 100
    if trade_risk_amount > max_trade_risk:
        raise RiskBreach(
            "per_trade_risk",
            f"trade risk ${trade_risk_amount:,.2f} > ${max_trade_risk:,.2f} "
            f"({limits.max_risk_per_trade_pct}% of equity)",
        )
    max_heat = equity * limits.max_portfolio_heat_pct / 100
    if open_risk_amount + trade_risk_amount > max_heat:
        raise RiskBreach(
            "portfolio_heat",
            f"heat would be ${open_risk_amount + trade_risk_amount:,.2f} > "
            f"${max_heat:,.2f} ({limits.max_portfolio_heat_pct}% of equity)",
        )
    max_notional = equity * limits.max_position_pct / 100
    if symbol_open_notional + trade_notional > max_notional:
        raise RiskBreach(
            "position_size",
            f"{symbol_open_notional + trade_notional:,.2f} notional > "
            f"${max_notional:,.2f} ({limits.max_position_pct}% of equity)",
        )


def size_position(
    equity: float, limits: RiskLimits, risk_per_unit: float, price: float
) -> float:
    """Position quantity from risk: risk `max_risk_per_trade_pct` of equity,
    capped so notional never exceeds `max_position_pct` of equity."""
    if risk_per_unit <= 0:
        raise RiskBreach("per_trade_risk", "risk_per_unit must be positive")
    if price <= 0:
        raise RiskBreach("per_trade_risk", "price must be positive")
    risk_amount = equity * limits.max_risk_per_trade_pct / 100
    qty = risk_amount / risk_per_unit
    max_qty = (equity * limits.max_position_pct / 100) / price
    return min(qty, max_qty)
