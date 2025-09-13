import numpy as np

from allocators.sizing import vol_scaled_weights, apply_exposure_caps


def test_vol_scaled_obeys_mask_and_sums():
    mu = np.array([0.01, 0.02, 0.015])
    Sigma = np.diag([0.01, 0.04, 0.09])
    x = np.array([1, 0, 1])
    w = vol_scaled_weights(mu, Sigma, x, cap=0.8)
    assert w.shape == (3,)
    # zero for masked-out asset
    assert abs(w[1]) < 1e-9
    s = float(np.sum(np.abs(w)))
    assert abs(s - 1.0) < 1e-6


def test_sector_caps_respected():
    # initial equal weights
    w = np.array([0.34, 0.33, 0.33])
    # sectors: first two in A, third in B
    sector_map = {0: "A", 1: "A", 2: "B"}
    w_cap = apply_exposure_caps(w, sector_map=sector_map, sector_cap=0.6)
    # sum remains ~1
    assert abs(float(np.sum(w_cap)) - 1.0) < 1e-6
    # sector A sum <= 0.6
    a_sum = float(w_cap[0] + w_cap[1])
    assert a_sum <= 0.600001

