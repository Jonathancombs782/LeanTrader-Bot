from __future__ import annotations

import math
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Any


def _norm_inv(p: float) -> float:
    """Inverse CDF for standard normal via approximation (Acklam)."""
    # pylint: disable=too-many-locals
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if phigh < p:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r) + 1
    )


def scenario(
    *,
    rates_up: float = 0.0,
    oil_shock: float = 0.0,
    recession_prob: float = 0.0,
) -> Dict[str, float]:
    """Return simple regime-conditioned shock scalars for mu/Sigma.

    Output keys:
      mu_shift: additive shift multiplier on expected return (portfolio-level proxy)
      vol_mult: multiplicative factor on volatility (covariance scaling)
      corr_mult: multiplicative factor on average correlation
    """
    # Bound inputs
    r = max(-1.0, min(1.0, float(rates_up)))
    o = max(-1.0, min(1.0, float(oil_shock)))
    rec = max(0.0, min(1.0, float(recession_prob)))

    # Heuristics: higher rates and recession hurt risk assets; oil shocks raise vol and correlation.
    mu_shift = -0.06 * r - 0.1 * rec + 0.02 * o
    vol_mult = 1.0 + 0.5 * abs(r) + 0.8 * abs(o) + 1.2 * rec
    corr_mult = 1.0 + 0.3 * abs(o) + 0.7 * rec
    return {"mu_shift": mu_shift, "vol_mult": vol_mult, "corr_mult": corr_mult}


def _portfolio_stats(w: Sequence[float], Sigma: Sequence[Sequence[float]], mu: Optional[Sequence[float]] = None) -> Tuple[float, float]:
    n = len(w)
    mu_p = 0.0
    if mu is not None:
        mu_p = sum(float(w[i]) * float(mu[i]) for i in range(n))
    # variance
    var = 0.0
    for i in range(n):
        for j in range(n):
            var += float(w[i]) * float(w[j]) * float(Sigma[i][j])
    sigma = math.sqrt(max(var, 0.0))
    return mu_p, sigma


def _scale_cov(Sigma: Sequence[Sequence[float]], vol_mult: float, corr_mult: float) -> List[List[float]]:
    # Decompose Sigma into vol * corr * vol and rescale
    n = len(Sigma)
    vol = [math.sqrt(max(0.0, float(Sigma[i][i]))) for i in range(n)]
    # Build correlation
    corr = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            denom = vol[i] * vol[j] if vol[i] and vol[j] else 0.0
            corr[i][j] = float(Sigma[i][j]) / denom if denom > 0 else (1.0 if i == j else 0.0)
    # Scale
    vol2 = [v * vol_mult for v in vol]
    for i in range(n):
        for j in range(n):
            c = corr[i][j] * (corr_mult if i != j else 1.0)
            Sigma_ij = vol2[i] * vol2[j] * c
            corr[i][j] = Sigma_ij
    return corr


def _var_cvar(mu_p: float, sigma: float, alpha: float = 0.95) -> Tuple[float, float]:
    # Loss distribution L = -R, normal approximation
    z = _norm_inv(alpha)
    VaR = -mu_p + z * sigma
    # CVaR for normal loss
    phi = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    CVaR = -mu_p + sigma * (phi / (1 - alpha))
    return VaR, CVaR


def run_scenarios(
    w: Sequence[float],
    Sigma: Sequence[Sequence[float]],
    scenarios: Sequence[Mapping[str, float]],
    mu: Optional[Sequence[float]] = None,
    alpha: float = 0.95,
) -> Dict[str, Any]:
    """Compute VaR/CVaR deltas vs baseline and identify worst-case asset contributions.

    Returns dict with baseline, per-scenario deltas, and ranking of risk contributions.
    """
    base_mu, base_sig = _portfolio_stats(w, Sigma, mu=mu)
    base_VaR, base_CVaR = _var_cvar(base_mu, base_sig, alpha)
    out: Dict[str, Any] = {
        "baseline": {"mu": base_mu, "sigma": base_sig, "VaR": base_VaR, "CVaR": base_CVaR},
        "scenarios": [],
    }
    # Risk contributions: w_i * (Sigma w)_i
    n = len(w)
    Sw = [sum(float(Sigma[i][j]) * float(w[j]) for j in range(n)) for i in range(n)]
    rc = [float(w[i]) * Sw[i] for i in range(n)]
    out["risk_contrib"] = rc

    for s in scenarios:
        params = scenario(
            rates_up=float(s.get("rates_up", 0.0) or 0.0),
            oil_shock=float(s.get("oil_shock", 0.0) or 0.0),
            recession_prob=float(s.get("recession_prob", 0.0) or 0.0),
        )
        mu_s = None if mu is None else [float(m) + float(params["mu_shift"]) for m in mu]
        Sig_s = _scale_cov(Sigma, float(params["vol_mult"]), float(params["corr_mult"]))
        m, s_p = _portfolio_stats(w, Sig_s, mu=mu_s)
        VaR, CVaR = _var_cvar(m, s_p, alpha)
        out["scenarios"].append(
            {
                "input": dict(s),
                "mu": m,
                "sigma": s_p,
                "VaR": VaR,
                "CVaR": CVaR,
                "delta_VaR": VaR - base_VaR,
                "delta_CVaR": CVaR - base_CVaR,
            }
        )
    return out


__all__ = ["scenario", "run_scenarios"]

