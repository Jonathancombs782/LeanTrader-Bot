"""PaperEngine: the brain's beating heart.

submit_signal() -> risk gate -> size -> simulate fill -> portfolio -> ledger.
Every step is recorded; a breached limit stops the trade and logs why.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import universe as universe_mod
from .fills import simulate_fill
from .ledger import Ledger
from .portfolio import PaperPortfolio, Position
from .receipts import utcnow_iso
from .risk import RiskBreach, RiskLimits, check_new_trade, size_position
from .signals import Signal


@dataclass
class EngineResult:
    accepted: bool
    reason: str = ""
    position: Position | None = None
    fill_price: float = 0.0


class PaperEngine:
    def __init__(
        self,
        starting_equity: float = 100_000.0,
        limits: RiskLimits | None = None,
        ledger: Ledger | None = None,
        universe: list | None = None,
    ):
        self.limits = limits or RiskLimits()
        self.portfolio = PaperPortfolio.funded(starting_equity)
        self.ledger = ledger or Ledger()
        self.universe = universe or universe_mod.BLUE_CHIPS
        self.prices: dict[str, float] = {}  # last known mids, set via update_prices

    # -- market data -----------------------------------------------------
    def update_prices(self, prices: dict[str, float]) -> None:
        self.prices.update({k: v for k, v in prices.items() if v > 0})

    # -- trading ---------------------------------------------------------
    def submit_signal(self, signal: Signal) -> EngineResult:
        """Validate a signal against risk gates and simulate the fill."""
        if signal.symbol not in self.prices:
            return EngineResult(False, f"no price for {signal.symbol}")
        price = self.prices[signal.symbol]
        equity = self.portfolio.equity(self.prices)

        quantity = size_position(equity, self.limits, signal.risk_per_unit, price)
        trade_risk = quantity * signal.risk_per_unit
        trade_notional = quantity * price

        try:
            check_new_trade(
                self.limits,
                equity=equity,
                trade_risk_amount=trade_risk,
                trade_notional=trade_notional,
                open_risk_amount=self.portfolio.open_risk(),
                symbol_open_notional=self.portfolio.open_notional(signal.symbol, self.prices),
                daily_pnl_pct=self.portfolio.daily_pnl_pct(self.prices),
                drawdown_pct=self.portfolio.drawdown_pct(self.prices),
            )
        except RiskBreach as e:
            self.ledger.append("risk_events", {
                "event": "breach", "limit": e.limit, "detail": str(e),
                "signal_id": signal.signal_id, "symbol": signal.symbol,
            })
            self.ledger.append("signals", {**signal.to_dict(), "disposition": "rejected"})
            return EngineResult(False, str(e))

        try:
            asset = universe_mod.by_symbol(signal.symbol, self.universe)
            tier = asset.tier
        except KeyError:
            tier = "mid"
        fill = simulate_fill(signal.symbol, signal.side, quantity, price, tier)

        position = Position(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            avg_price=fill.fill_price,
            stop=signal.stop,
            target=signal.target,
            risk_amount=trade_risk,
            fees_paid=fill.fee,
        )
        if signal.side.value == "long":
            self.portfolio.open_position(position, fill.notional + fill.fee)
        else:
            self.portfolio.open_position(position, fill.fee)  # fee only; proceeds credited inside

        self.ledger.append("signals", {**signal.to_dict(), "disposition": "accepted"})
        self.ledger.append("fills", {
            "signal_id": signal.signal_id, **fill.to_dict(),
            "at": utcnow_iso(),
        })
        return EngineResult(True, "filled", position, fill.fill_price)

    def close(self, symbol: str) -> float:
        """Close a position at the last known price. Returns realized PnL."""
        if symbol not in self.prices:
            raise ValueError(f"no price for {symbol}")
        if symbol not in self.portfolio.positions:
            raise ValueError(f"no open position in {symbol}")
        from .fills import FEE_BPS
        price = self.prices[symbol]
        pos = self.portfolio.positions[symbol]
        fee = pos.quantity * price * FEE_BPS / 10_000
        pnl = self.portfolio.close_position(symbol, price, fee)
        self.ledger.append("fills", {
            "event": "close", "symbol": symbol, "exit_price": price,
            "quantity": pos.quantity, "fee": fee, "realized_pnl": pnl,
            "at": utcnow_iso(),
        })
        return pnl

    def snapshot_equity(self) -> dict:
        eq = self.portfolio.equity(self.prices)
        snap = {
            "equity": eq,
            "cash": self.portfolio.cash,
            "realized_pnl": self.portfolio.realized_pnl,
            "open_positions": len(self.portfolio.positions),
            "daily_pnl_pct": self.portfolio.daily_pnl_pct(self.prices),
            "drawdown_pct": self.portfolio.drawdown_pct(self.prices),
        }
        self.ledger.append("equity", snap)
        return snap
