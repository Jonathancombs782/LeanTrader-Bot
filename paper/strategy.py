"""Evening scan strategy: simple trend-following with volatility-sized risk.

Rules (v1, deliberately plain — the edge here is the receipts, not exotic math):
  - LONG  when close > SMA20 > SMA50 (uptrend)
  - SHORT when close < SMA20 < SMA50 (downtrend)
  - FLAT  otherwise — no signal, and that is a result, not a failure.
  - Stop  = entry ∓ 1.5 × avg daily range (14d)
  - Target = entry ± 3.0 × avg daily range  →  2:1 reward-to-risk

For crypto symbols the free feed gives closes only, so the "daily range" is
the mean absolute close-to-close move. For stocks it is the mean true
high-low range. Both are labeled honestly in the thesis.
"""
from __future__ import annotations

from .history import Bar
from .receipts import Receipt
from .signals import Signal, SignalSide

SMA_FAST = 20
SMA_SLOW = 50
RANGE_DAYS = 14
STOP_MULT = 1.5
TARGET_MULT = 3.0


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def avg_daily_range(bars: list[Bar], crypto_closes_only: bool) -> float | None:
    if len(bars) < RANGE_DAYS + 1:
        return None
    recent = bars[-(RANGE_DAYS + 1):]
    if crypto_closes_only:
        moves = [abs(recent[i].close - recent[i - 1].close) for i in range(1, len(recent))]
    else:
        moves = [b.daily_range for b in recent[1:]]
    moves = [m for m in moves if m > 0]
    return sum(moves) / len(moves) if moves else None


def generate_signal(
    symbol: str,
    bars: list[Bar],
    price: float,
    receipts: tuple[Receipt, ...],
    crypto_closes_only: bool,
) -> Signal | None:
    """Build a trend signal, or return None when there is no trend."""
    closes = [b.close for b in bars]
    fast = sma(closes, SMA_FAST)
    slow = sma(closes, SMA_SLOW)
    adr = avg_daily_range(bars, crypto_closes_only)
    if fast is None or slow is None or adr is None or adr <= 0:
        return None

    if price > fast > slow:
        side = SignalSide.LONG
        stop = price - STOP_MULT * adr
        target = price + TARGET_MULT * adr
        direction = "uptrend"
    elif price < fast < slow:
        side = SignalSide.SHORT
        stop = price + STOP_MULT * adr
        target = price - TARGET_MULT * adr
        direction = "downtrend"
    else:
        return None

    if stop <= 0 or target <= 0:
        return None

    range_kind = "mean abs close-to-close move" if crypto_closes_only else "mean daily high-low range"
    rr = TARGET_MULT / STOP_MULT
    thesis = (
        f"{symbol} {direction}: close ${price:,.2f} vs 20d SMA ${fast:,.2f} vs "
        f"50d SMA ${slow:,.2f}. 14d {range_kind} ${adr:,.2f}; "
        f"risking {STOP_MULT}× range for {TARGET_MULT}× range ({rr:.0f}:1 reward-to-risk). "
        f"Entry ${price:,.2f}, stop ${stop:,.2f}, target ${target:,.2f}."
    )
    return Signal(
        symbol=symbol,
        side=side,
        entry=round(price, 4),
        stop=round(stop, 4),
        target=round(target, 4),
        thesis=thesis,
        receipts=receipts,
        inputs={
            "strategy": "trend_v1",
            "close": price,
            "sma20": round(fast, 4),
            "sma50": round(slow, 4),
            "avg_daily_range": round(adr, 4),
            "bars": len(bars),
        },
    )
