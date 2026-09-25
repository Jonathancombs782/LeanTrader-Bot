"""Paper portfolio: cash, positions, and honest accounting."""
from __future__ import annotations

from dataclasses import dataclass, field

from .signals import SignalSide


@dataclass
class Position:
    symbol: str
    side: SignalSide          # LONG or SHORT
    quantity: float
    avg_price: float          # average fill price
    stop: float
    target: float
    risk_amount: float        # equity risked at entry
    fees_paid: float = 0.0

    def market_value(self, price: float) -> float:
        if self.side == SignalSide.LONG:
            return self.quantity * price
        return -self.quantity * price  # short market value (liability)

    def unrealized_pnl(self, price: float) -> float:
        if self.side == SignalSide.LONG:
            return self.quantity * (price - self.avg_price)
        return self.quantity * (self.avg_price - price)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["side"] = self.side.value
        return d


@dataclass
class PaperPortfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    day_start_equity: float = 0.0
    peak_equity: float = 0.0

    @classmethod
    def funded(cls, equity: float) -> "PaperPortfolio":
        return cls(cash=equity, day_start_equity=equity, peak_equity=equity)

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for sym, pos in self.positions.items():
            if sym in prices:
                if pos.side == SignalSide.LONG:
                    total += pos.quantity * prices[sym]
                else:
                    # short: cash already credited at entry; subtract current cost to cover
                    total -= pos.quantity * prices[sym]
        return total

    def open_risk(self) -> float:
        return sum(p.risk_amount for p in self.positions.values())

    def open_notional(self, symbol: str, prices: dict[str, float]) -> float:
        pos = self.positions.get(symbol)
        if not pos or symbol not in prices:
            return 0.0
        return pos.quantity * prices[symbol]

    def open_position(self, position: Position, fill_cost: float) -> None:
        """Record a filled entry. fill_cost = notional + fee (buy) or fee (short)."""
        if position.side == SignalSide.LONG:
            self.cash -= fill_cost
        else:
            # short sale: receive notional, pay fee
            self.cash += position.quantity * position.avg_price - position.fees_paid
        self.positions[position.symbol] = position
        self.fees_paid += position.fees_paid

    def close_position(self, symbol: str, exit_price: float, fee: float) -> float:
        """Close at exit_price; returns realized PnL net of the exit fee."""
        pos = self.positions.pop(symbol)
        if pos.side == SignalSide.LONG:
            proceeds = pos.quantity * exit_price - fee
            pnl = proceeds - pos.quantity * pos.avg_price
            self.cash += proceeds
        else:
            cost = pos.quantity * exit_price + fee
            pnl = pos.quantity * pos.avg_price - cost
            self.cash -= cost
        self.realized_pnl += pnl
        self.fees_paid += fee
        return pnl

    def daily_pnl_pct(self, prices: dict[str, float]) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity(prices) - self.day_start_equity) / self.day_start_equity * 100

    def drawdown_pct(self, prices: dict[str, float]) -> float:
        eq = self.equity(prices)
        if eq > self.peak_equity:
            self.peak_equity = eq
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - eq) / self.peak_equity * 100
