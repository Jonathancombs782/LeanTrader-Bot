import os
import importlib
import numpy as np
import pandas as pd


def reload_all():
    try:
        import config as _cfg

        importlib.reload(_cfg)
    except Exception:
        pass
    import features.pipeline as fp
    import strategies.pipeline as sp
    import research.regime as rr
    importlib.reload(fp)
    importlib.reload(sp)
    importlib.reload(rr)
    return fp, sp, rr


def test_regime_gates():
    from research.regime import quantum_allowed_for_regime, select_quantum_mode

    assert quantum_allowed_for_regime("range_bound") is True
    assert quantum_allowed_for_regime("low_vol_trend") is True
    assert quantum_allowed_for_regime("calm") is True
    for bad in (None, "storm", "trend", "unknown"):
        assert quantum_allowed_for_regime(bad) is False

    os.environ["Q_ENABLE_QUANTUM"] = "true"
    reload_all()
    assert select_quantum_mode("calm", default_on=True) is True
    assert select_quantum_mode(None, default_on=True) is False
    assert select_quantum_mode("storm", default_on=True) is False


def _make_df(n=300, m=6):
    rng = np.random.default_rng(123)
    data = {}
    for i in range(m):
        steps = rng.normal(0.0003 + 0.0001 * (i % 2), 0.01, size=n)
        data[f"A{i}"] = 100 * np.cumprod(1.0 + steps)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=n, freq="1min")
    return pd.DataFrame(data, index=idx)


def test_compute_mu_cov_shapes_psd():
    from features.pipeline import compute_mu_cov, ensure_psd

    df = _make_df(300, 6)
    mu, Sigma = compute_mu_cov(df, window=252, min_history=126)
    n = mu.shape[0]
    assert n >= 3
    assert Sigma.shape == (n, n)
    # PSD check via eigenvalues
    vals = np.linalg.eigvalsh(Sigma)
    assert np.all(vals >= -1e-8)


def test_daily_rebalance_job_regime_gate():
    os.environ["Q_ENABLE_QUANTUM"] = "true"
    fp, sp, rr = reload_all()
    df = _make_df(260, 5)
    # calm regime -> enabled
    res = sp.daily_rebalance_job(df, latest_regime="calm", budget=4)
    assert res.get("ok") is True
    assert res.get("q_enabled") is True
    assert res.get("regime") == "calm"
    # None regime -> disabled
    res2 = sp.daily_rebalance_job(df, latest_regime=None, budget=4)
    assert res2.get("ok") is True
    assert res2.get("q_enabled") is False

