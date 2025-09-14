import os
import importlib
import numpy as np


def _reload_quantum_modules(enable: bool):
    # Control env and reload modules so flags are applied
    os.environ["Q_ENABLE_QUANTUM"] = "true" if enable else "false"
    try:
        import config as _cfg

        importlib.reload(_cfg)
    except Exception:
        pass
    # reload risk.pricing and allocators.portfolio to pick up updated config
    try:
        import risk.pricing as rp  # type: ignore

        importlib.reload(rp)
    except Exception:
        pass
    try:
        import allocators.portfolio as ap  # type: ignore

        importlib.reload(ap)
    except Exception:
        pass


def test_choose_assets_binary_within_budget():
    _reload_quantum_modules(enable=False)
    import allocators.portfolio as ap

    n = 12
    rng = np.random.default_rng(42)
    mu = rng.normal(0.01, 0.02, size=n)
    # positive semi-definite covariance via random diagonal
    diag = np.abs(rng.normal(0.02, 0.01, size=n)) + 1e-4
    Sigma = np.diag(diag)
    budget = 5
    x = ap.choose_assets(mu, Sigma, budget)
    assert isinstance(x, np.ndarray)
    assert x.dtype == int or np.issubdtype(x.dtype, np.integer)
    assert x.shape == (n,)
    assert np.all((x == 0) | (x == 1))
    assert int(x.sum()) <= budget


def test_price_call_matches_classical_when_quantum_disabled():
    _reload_quantum_modules(enable=False)
    import risk.pricing as rp

    S0, K, T, r, sigma = 100.0, 95.0, 0.5, 0.01, 0.25
    pc = rp.price_call(S0, K, T, r, sigma)
    bs = rp.price_call_classical(S0, K, T, r, sigma)
    assert isinstance(pc, float)
    # allow tiny tolerance
    assert abs(pc - bs) < 1e-8


def test_quantum_disabled_returns_valid_outputs():
    _reload_quantum_modules(enable=False)
    import allocators.portfolio as ap
    import risk.pricing as rp

    mu = np.array([0.01, 0.02, 0.015, -0.005])
    Sigma = np.diag([0.02, 0.03, 0.025, 0.04])
    x = ap.choose_assets(mu, Sigma, budget=2)
    assert isinstance(x, np.ndarray)
    assert x.shape == (4,)
    assert np.all((x == 0) | (x == 1))
    assert int(x.sum()) <= 2

    price = rp.price_call(100.0, 100.0, 0.25, 0.01, 0.2)
    assert isinstance(price, float)
    assert price >= 0.0

