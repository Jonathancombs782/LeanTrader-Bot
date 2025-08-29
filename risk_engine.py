# risk_engine.py
# Dynamic sizing, portfolio exposure limits, ATR-based stops, TP ladder helpers.

from __future__ import annotations
import os, math, time
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

# ---------- ENV ----------
def _envf(k: str, d: float) -> float:
    try: return float(os.getenv(k, str(d)))
    except: return d

def _envi(k: str, d: int) -> int:
    try: return int(float(os.getenv(k, str(d))))
    except: return d

def _envb(k: str, d: bool) -> bool:
    return os.getenv(k, str(d)).strip().lower() in ("1","true","yes","on")

RISK_PCT_PER_TRADE = _envf("RISK_PCT_PER_TRADE", 1.0)      # % of equity
RISK_PCT_TOTAL_MAX = _envf("RISK_PCT_TOTAL_MAX", 3.0)       # cap on agg open risk
MAX_TRADES_AT_ONCE  = _envi("MAX_TRADES_AT_ONCE", 6)
MIN_NOTIONAL_USD    = _envf("MIN_NOTIONAL_USD", 5.0)        # avoid dust
FUT_MAX_LEVERAGE    = _envi("FUT_MAX_LEVERAGE", 5)
FUT_DEFAULT_LEV     = _envi("FUT_DEFAULT_LEVERAGE", 3)

# ---------- helpers ----------
@dataclass
class Equity:
    usd: float
    ts: float

@dataclass
class Plan:
    qty: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    r_multiple: float        # (entry - sl) distance in price units
    notional_usd: float
    leverage: int | None
    warnings: list[str]

# ATR/volatility → targets
def make_targets(entry: float, sl: float, side: str, atr: float | None = None,
                 rr: Tuple[float,float,float] = (1.0, 1.8, 3.0)) -> Tuple[float,float,float]:
    dist = abs(entry - sl)
    if atr and atr > 0:
        # Let ATR slightly stretch the 2nd/3rd target in noisy markets
        bump = min(1.5, 1.0 + (atr / max(1e-9, entry)) * 5.0)
        rr = (rr[0], rr[1]*bump, rr[2]*bump)
    if side.lower() == "buy":
        return (entry + rr[0]*dist, entry + rr[1]*dist, entry + rr[2]*dist)
    else:
        return (entry - rr[0]*dist, entry - rr[1]*dist, entry - rr[2]*dist)

# basic equity fetch (works with your router.account())
def equity_from_router(router) -> Equity:
    try:
        acct = router.account()
        if acct.get("ok"):
            # paper broker path
            cash = acct.get("paper_cash")
            if cash is not None:
                return Equity(float(cash), time.time())
            # ccxt path
            bal = acct.get("balance", {})
            total = bal.get("total", {}) if isinstance(bal, dict) else {}
            usd = float(total.get("USDT") or total.get("USD") or 0.0)
            if usd <= 0 and "info" in bal:
                # very rough fallback
                usd = float(bal["info"].get("equity", 0.0) or 0.0)
            return Equity(usd, time.time())
    except Exception:
        pass
    return Equity(0.0, time.time())

# contract/qty sizing
def size_crypto_from_risk(entry: float, sl: float, equity_usd: float, risk_pct: float) -> float:
    risk_usd = max(0.0, equity_usd * (risk_pct/100.0))
    dist = abs(entry - sl)
    if dist <= 0: return 0.0
    qty_base = risk_usd / dist
    # round to 6 decimals to be safe
    return max(0.0, round(qty_base, 6))

# very simplified FX lot sizing (USD quote; JPY pip fix handled)
def lots_fx_from_risk(entry: float, sl: float, equity_usd: float, risk_pct: float, symbol: str) -> float:
    risk_usd = max(0.0, equity_usd * (risk_pct/100.0))
    dist = abs(entry - sl)
    if dist <= 0: return 0.0
    # pip value per 1.00 lot is ~$10 for most USD quote FX; JPY pairs ~ $9–$10 at typical prices
    if "JPY" in symbol.upper():
        pip = 0.01
        pip_value_per_lot = 1000.0 * pip  # ≈$10
    else:
        pip = 0.0001
        pip_value_per_lot = 100000.0 * pip  # ≈$10
    # distance in pips:
    pips = dist / pip
    if pips <= 0: return 0.0
    # 1 lot risk for given stop:
    usd_risk_per_lot = pips * (pip_value_per_lot / 10.0)  # ~ $1 per 0.1 pip → normalize
    lots = risk_usd / max(1e-9, usd_risk_per_lot)
    return round(max(0.0, lots), 2)

# exposure accounting (simple counters per quote or currency block)
class ExposureBook:
    def __init__(self):
        self.blocks: Dict[str, float] = {}   # block -> % risk used
        self.total_pct: float = 0.0
        self.trades_open: int = 0

    def can_add(self, block: str, add_pct: float) -> bool:
        if self.trades_open >= MAX_TRADES_AT_ONCE:
            return False
        if self.total_pct + add_pct > RISK_PCT_TOTAL_MAX:
            return False
        if self.blocks.get(block, 0.0) + add_pct > max(RISK_PCT_TOTAL_MAX/2.0, RISK_PCT_PER_TRADE*2.0):
            # don't let one block dominate
            return False
        return True

    def add(self, block: str, add_pct: float) -> None:
        self.blocks[block] = self.blocks.get(block, 0.0) + add_pct
        self.total_pct += add_pct
        self.trades_open += 1

# master planner for crypto (spot/linear)
def plan_crypto(entry: float, sl: float, side: str, equity: Equity,
                leverage: Optional[int] = None,
                atr: Optional[float] = None) -> Plan:
    warnings: list[str] = []
    lev = leverage or FUT_DEFAULT_LEV
    if lev > FUT_MAX_LEVERAGE:
        warnings.append(f"leverage clipped to {FUT_MAX_LEVERAGE}")
        lev = FUT_MAX_LEVERAGE

    qty = size_crypto_from_risk(entry, sl, equity.usd, RISK_PCT_PER_TRADE)
    if qty * entry < MIN_NOTIONAL_USD:
        warnings.append("min notional guard applied")
    tp1, tp2, tp3 = make_targets(entry, sl, side, atr=atr)
    return Plan(
        qty=qty, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
        r_multiple=abs(entry - sl),
        notional_usd=qty*entry,
        leverage=lev,
        warnings=warnings,
    )

# FX plan (lots, notional approximate via entry)
def plan_fx(entry: float, sl: float, side: str, equity: Equity,
            symbol: str, atr: Optional[float] = None) -> Plan:
    qty_lots = lots_fx_from_risk(entry, sl, equity.usd, RISK_PCT_PER_TRADE, symbol)
    tp1, tp2, tp3 = make_targets(entry, sl, side, atr=atr)
    return Plan(
        qty=qty_lots, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
        r_multiple=abs(entry - sl),
        notional_usd=qty_lots * 100000.0,  # rough
        leverage=None, warnings=[]
    )
