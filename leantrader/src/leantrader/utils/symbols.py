from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMeta:
    unified: str  # e.g., 'EUR/USD' or 'BTC/USDT'
    market: str  # 'fx' or 'crypto'
    base: str
    quote: str
    precision_price: int = 5
    precision_amount: int = 2
    lot_step: float = 0.01
    tick_size: float = 0.00001


def normalize_symbol(s: str):
    s = s.replace("-", "/").upper()
    if "USD" in s or "EUR" in s or "JPY" in s or "GBP" in s or "CHF" in s or "AUD" in s or "CAD" in s or "NZD" in s:
        # naive fx heuristic
        parts = s.split("/")
        if len(parts) == 2:
            return SymbolMeta(unified=f"{parts[0]}/{parts[1]}", market="fx", base=parts[0], quote=parts[1])
    # else assume crypto by default
    parts = s.split("/")
    if len(parts) == 2:
        return SymbolMeta(
            unified=f"{parts[0]}/{parts[1]}",
            market="crypto",
            base=parts[0],
            quote=parts[1],
            precision_price=2,
            precision_amount=6,
            lot_step=0.000001,
            tick_size=0.01,
        )
    return SymbolMeta(unified=s, market="unknown", base=s, quote="")
