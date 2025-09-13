import math

try:
    from config import Q_ENABLE_QUANTUM
except Exception:
    Q_ENABLE_QUANTUM = False


# Try to import quantum option pricing if present
_quantum_price_fn = None
try:
    from quantum.pricing_qae import quantum_option_price as _quantum_price_fn  # type: ignore
except Exception:
    _quantum_price_fn = None


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf to avoid external deps."""
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def price_call_classical(S0: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes European call price.

    S0: spot
    K: strike
    T: time to maturity in years
    r: risk-free rate (annual)
    sigma: volatility (annualized)
    """
    S0 = float(S0)
    K = float(K)
    T = max(0.0, float(T))
    r = float(r)
    sigma = max(1e-12, float(sigma))

    if T <= 0:
        return max(0.0, S0 - K)

    d1 = (math.log(S0 / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    Nd1 = _norm_cdf(d1)
    Nd2 = _norm_cdf(d2)
    return S0 * Nd1 - K * math.exp(-r * T) * Nd2


def price_call(S0: float, K: float, T: float, r: float, sigma: float) -> float:
    """Quantum-backed call pricing with classical fallback.

    If Q_ENABLE_QUANTUM and a quantum pricing function is available,
    use it. Otherwise, return Black-Scholes price.
    """
    if Q_ENABLE_QUANTUM and _quantum_price_fn is not None:
        try:
            return float(_quantum_price_fn(S0, K, T, r, sigma))
        except Exception:
            pass
    return price_call_classical(S0, K, T, r, sigma)


__all__ = ["price_call", "price_call_classical"]

