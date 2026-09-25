"""Paper-trading brain: verifiable signals, simulated fills, hard risk limits.

Milestone 1. Stdlib only. No credentials, no exchange access, no real money.
"""

from .engine import PaperEngine
from .fills import Fill, simulate_fill
from .ledger import Ledger
from .portfolio import PaperPortfolio, Position
from .receipts import Receipt, hash_bytes, hash_file, utcnow_iso
from .risk import RiskBreach, RiskLimits
from .signals import Signal, SignalSide
from .universe import BLUE_CHIPS, Asset

__all__ = [
    "Asset",
    "BLUE_CHIPS",
    "Fill",
    "Ledger",
    "PaperEngine",
    "PaperPortfolio",
    "Position",
    "Receipt",
    "RiskBreach",
    "RiskLimits",
    "Signal",
    "SignalSide",
    "hash_bytes",
    "hash_file",
    "simulate_fill",
    "utcnow_iso",
]
