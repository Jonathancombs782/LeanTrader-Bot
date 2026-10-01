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
from .signals import Signal, SignalSide


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

    def roll_day_if_new(self, today: str | None = None) -> bool:
        """Advance the daily PnL baseline when the UTC date has changed.

        The baseline is the current mark-to-market equity; a day_roll event is
        appended so ledger replay can restore the marker. Returns True when a
        roll happened.
        """
        today = today or utcnow_iso()[:10]
        if today == self.portfolio.trading_day:
            return False
        baseline = self.portfolio.equity(self.prices)
        self.portfolio.trading_day = today
        self.portfolio.day_start_equity = baseline
        self.ledger.append("risk_events", {
            "event": "day_roll", "trading_day": today,
            "day_start_equity": baseline,
        })
        return True

    def _reject(self, signal: Signal, limit: str, detail: str) -> EngineResult:
        self.ledger.append("risk_events", {
            "event": "breach", "limit": limit, "detail": detail,
            "signal_id": signal.signal_id, "symbol": signal.symbol,
        })
        self.ledger.append("signals", {**signal.to_dict(), "disposition": "rejected"})
        return EngineResult(False, f"[{limit}] {detail}")

    # -- trading ---------------------------------------------------------
    def submit_signal(self, signal: Signal) -> EngineResult:
        """Validate a signal against risk gates and simulate the fill."""
        if signal.symbol not in self.prices:
            return EngineResult(False, f"no price for {signal.symbol}")
        price = self.prices[signal.symbol]
        self.roll_day_if_new()
        equity = self.portfolio.equity(self.prices)

        # One open position per symbol: a second fill would silently discard
        # the first Position while keeping its cash debit.
        if signal.symbol in self.portfolio.positions:
            return self._reject(
                signal, "single_position_per_symbol",
                f"position already open in {signal.symbol} — "
                "close it before opening another",
            )

        try:
            asset = universe_mod.by_symbol(signal.symbol, self.universe)
            tier = asset.tier
        except KeyError:
            tier = "mid"

        # Size from the actual fill, not the declared entry. The fill price is
        # quantity-independent, so probe it with a unit fill first, then size
        # quantity and risk from the fill-to-stop distance.
        probe = simulate_fill(signal.symbol, signal.side, 1.0, price, tier)
        risk_per_unit = abs(probe.fill_price - signal.stop)
        if risk_per_unit <= 0:
            return self._reject(
                signal, "per_trade_risk",
                "stop equals the simulated fill price — risk is undefined",
            )

        quantity = size_position(equity, self.limits, risk_per_unit,
                                 probe.fill_price)
        trade_risk = quantity * risk_per_unit
        trade_notional = quantity * probe.fill_price

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
            # the actual risk taken: quantity x fill-to-stop distance
            "risk_amount": trade_risk,
            "at": utcnow_iso(),
        })
        return EngineResult(True, "filled", position, fill.fill_price)

    def close(self, symbol: str) -> float:
        """Close a position with simulated slippage. Returns realized PnL."""
        if symbol not in self.prices:
            raise ValueError(f"no price for {symbol}")
        if symbol not in self.portfolio.positions:
            raise ValueError(f"no open position in {symbol}")
        price = self.prices[symbol]
        pos = self.portfolio.positions[symbol]
        try:
            tier = universe_mod.by_symbol(symbol, self.universe).tier
        except KeyError:
            tier = "mid"
        # Closing is the opposite-side order: a long sells into the bid,
        # a short buys back at the offer. Entries pay slippage, so exits do too.
        close_side = SignalSide.LONG if pos.side == SignalSide.SHORT else SignalSide.SHORT
        fill = simulate_fill(symbol, close_side, pos.quantity, price, tier)
        pnl = self.portfolio.close_position(symbol, fill.fill_price, fill.fee)
        self.ledger.append("fills", {
            "event": "close", "symbol": symbol, "exit_price": fill.fill_price,
            "quantity": pos.quantity, "fee": fill.fee,
            "slippage_bps": fill.slippage_bps, "realized_pnl": pnl,
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
            "trading_day": self.portfolio.trading_day,
            "day_start_equity": self.portfolio.day_start_equity,
        }
        self.ledger.append("equity", snap)
        return snap


def replay_ledger(ledger: Ledger, starting_equity: float = 100_000.0) -> PaperEngine:
    """Rebuild engine state by replaying the ledger's recorded fills.

    Milestone 1 correctness: commands like `paper.cli status` must reflect the
    recorded trading history, not a freshly funded portfolio. Replay applies
    each recorded fill in ledger order — entry fills reconstruct their
    positions (stop/target/risk come from the matching *accepted* signal),
    close fills settle cash and realized PnL. Peak equity is restored from the
    max recorded equity snapshot so drawdown stays meaningful.

    The replay is read-only with respect to the ledger: nothing is appended.
    """
    engine = PaperEngine(starting_equity=starting_equity, ledger=ledger)

    # Restore the trading-day marker: day_start_equity is meaningless without
    # the date it belongs to. The last day_roll wins; later fills do not move
    # the baseline.
    for ev in ledger.read("risk_events"):
        if ev.get("event") == "day_roll":
            engine.portfolio.trading_day = ev["trading_day"]
            engine.portfolio.day_start_equity = float(ev["day_start_equity"])

    accepted = {
        s["signal_id"]: s
        for s in ledger.read("signals")
        if s.get("disposition") == "accepted"
    }
    for rec in ledger.read("fills"):
        if rec.get("event") == "close":
            engine.portfolio.close_position(
                rec["symbol"], float(rec["exit_price"]), float(rec["fee"])
            )
            continue
        sig = accepted.get(rec.get("signal_id"))
        if sig is None:
            continue  # fill without a recorded accepted signal; skip it
        side = SignalSide(rec["side"])
        # risk_amount is ledgered at fill time (quantity x fill-to-stop
        # distance); fall back to entry-based for older ledgers.
        if "risk_amount" in rec:
            risk_amount = float(rec["risk_amount"])
        else:
            risk_per_unit = abs(float(sig["entry"]) - float(sig["stop"]))
            risk_amount = float(rec["quantity"]) * risk_per_unit
        position = Position(
            symbol=rec["symbol"],
            side=side,
            quantity=float(rec["quantity"]),
            avg_price=float(rec["fill_price"]),
            stop=float(sig["stop"]),
            target=float(sig["target"]),
            risk_amount=risk_amount,
            fees_paid=float(rec["fee"]),
        )
        if side == SignalSide.LONG:
            engine.portfolio.open_position(
                position, float(rec["notional"]) + float(rec["fee"])
            )
        else:  # short: fee only; proceeds are credited inside open_position
            engine.portfolio.open_position(position, float(rec["fee"]))
    peaks = [e.get("equity", 0.0) for e in ledger.read("equity")]
    if peaks:
        engine.portfolio.peak_equity = max(starting_equity, max(peaks))
    return engine
