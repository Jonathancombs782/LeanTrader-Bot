
import math

def pip_size(pair: str) -> float:
    # JPY pairs typically 0.01 pip size; others 0.0001
    base, quote = normalize_pair(pair)
    if 'JPY' in (base, quote):
        return 0.01
    return 0.0001

def normalize_pair(pair: str):
    pair = pair.replace('_','/').replace('-','/')
    if '/' in pair:
        a,b = pair.split('/')
        return a.upper(), b.upper()
    return pair[:3].upper(), pair[3:].upper()

def pip_value_per_unit(pair: str, quote_to_usd: float = 1.0) -> float:
    # Approximate pip value in USD per 1 unit of base currency.
    base, quote = normalize_pair(pair)
    ps = pip_size(pair)
    if quote == 'USD':
        return ps  # e.g., EUR/USD: each pip is 0.0001 USD per unit
    elif base == 'USD':
        # e.g., USD/JPY: pip value in quote; convert to USD via quote_to_usd
        return ps * quote_to_usd
    else:
        # Cross pair: approximate via quote->USD conversion given as param
        return ps * quote_to_usd

def units_for_risk(fixed_risk_usd: float, atr_pips: float, pip_value_unit_usd: float) -> float:
    # units = risk / (ATR_pips * pip_value_per_unit)
    den = max(1e-9, atr_pips * pip_value_unit_usd)
    return max(0.0, fixed_risk_usd / den)
