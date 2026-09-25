"""Fill simulator: what a paper trade would actually cost.

Fills happen at mid ± slippage (by liquidity tier) plus a fee in bps.
Deterministic given a quote — no randomness, no excuses.
"""
from __future__ import annotations

from dataclasses import dataclass

from .signals import SignalSide

# slippage in basis points by liquidity tier
SLIPPAGE_BPS = {"major": 5, "mid": 15, "small": 30}
FEE_BPS = 10  # 0.10% per side


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: SignalSide   # direction of the ORDER (long=open buy, short=open sell)
    quantity: float
    mid_price: float
    fill_price: float
    notional: float
    fee: float
    slippage_bps: int

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["side"] = self.side.value
        return d


def simulate_fill(
    symbol: str,
    side: SignalSide,
    quantity: float,
    mid_price: float,
    tier: str = "mid",
    fee_bps: int = FEE_BPS,
) -> Fill:
    """Simulate a market fill. Buys lift the offer, sells hit the bid."""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if mid_price <= 0:
        raise ValueError("mid_price must be positive")
    slip_bps = SLIPPAGE_BPS.get(tier, SLIPPAGE_BPS["mid"])
    slip = slip_bps / 10_000
    if side == SignalSide.LONG:  # buying
        fill_price = mid_price * (1 + slip)
    else:  # selling (short entry or long exit)
        fill_price = mid_price * (1 - slip)
    notional = quantity * fill_price
    fee = notional * fee_bps / 10_000
    return Fill(
        symbol=symbol,
        side=side,
        quantity=quantity,
        mid_price=mid_price,
        fill_price=fill_price,
        notional=notional,
        fee=fee,
        slippage_bps=slip_bps,
    )
