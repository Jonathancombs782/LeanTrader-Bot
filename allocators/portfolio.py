import numpy as np

try:
    from config import Q_ENABLE_QUANTUM, Q_USE_RUNTIME
except Exception:
    # Safe defaults if config is not importable in some environments
    Q_ENABLE_QUANTUM, Q_USE_RUNTIME = False, True


# Try to import a quantum optimizer if present
quantum_portfolio_optimize = None
for _mod in (
    "quantum_portfolio",
    "quantum",
    "traders_core.quantum_portfolio",
):
    try:
        m = __import__(_mod, fromlist=["quantum_portfolio_optimize"])  # type: ignore
        if hasattr(m, "quantum_portfolio_optimize"):
            quantum_portfolio_optimize = getattr(m, "quantum_portfolio_optimize")
            break
    except Exception:
        continue

# Observability hooks (safe no-ops if missing)
try:
    from observability.metrics import (
        record_q_selection,
        record_q_fallback,
        time_block,
        set_obj_q_value,
    )
except Exception:  # pragma: no cover
    def record_q_selection():
        return None

    def record_q_fallback():
        return None

    from contextlib import contextmanager

    @contextmanager
    def time_block(name: str):
        yield 0.0

    def set_obj_q_value(val: float):
        return None


def _to_binary_selection(weights: np.ndarray, budget: int) -> np.ndarray:
    w = np.asarray(weights, dtype=float).reshape(-1)
    n = w.shape[0]
    budget = int(budget)
    if budget <= 0:
        return np.zeros(n, dtype=int)
    if budget >= n:
        return np.ones(n, dtype=int)
    # pick top-k by weight
    idx = np.argsort(-w)[:budget]
    sel = np.zeros(n, dtype=int)
    sel[idx] = 1
    return sel


def choose_assets(mu, Sigma, budget, *, force_quantum: bool | None = None, force_use_runtime: bool | None = None) -> np.ndarray:
    """Return a 0/1 selection vector of length len(mu).

    - If quantum optimization is enabled and available, use it.
    - Otherwise fall back to classical score = mu / sqrt(diag(Sigma)).
    """
    mu_arr = np.asarray(mu, dtype=float).reshape(-1)
    n = mu_arr.shape[0]

    # Build a valid covariance matrix (use diagonal if needed)
    try:
        Sig = np.asarray(Sigma, dtype=float)
        if Sig.ndim == 1:
            diag = Sig.reshape(-1)
            if diag.shape[0] != n:
                diag = np.resize(diag, n)
            Sig = np.diag(diag)
        else:
            if Sig.shape != (n, n):
                # coerce to diagonal covariance using its diagonal or ones
                diag = np.diag(Sig) if Sig.size >= n else np.ones(n, dtype=float)
                Sig = np.diag(np.resize(diag, n))
    except Exception:
        Sig = np.diag(np.ones(n, dtype=float))

    # Determine quantum enablement
    q_enabled = Q_ENABLE_QUANTUM if force_quantum is None else bool(force_quantum)
    use_runtime = Q_USE_RUNTIME if force_use_runtime is None else bool(force_use_runtime)

    # Try quantum path
    if q_enabled and quantum_portfolio_optimize is not None:
        try:
            with time_block("qaoa_select"):
                qsel = quantum_portfolio_optimize(
                    returns=mu_arr,
                    covariance=Sig,
                    budget=int(budget),
                    reps=2,
                    resilience_level=1,
                    use_runtime=use_runtime,
                )
            record_q_selection()
            qsel = np.asarray(qsel)
            # If the optimizer returns a dict/meta with objective, publish it
            try:
                if isinstance(qsel, dict):
                    obj = qsel.get("objective_value") or qsel.get("objective") or qsel.get("fval")
                    if obj is not None:
                        set_obj_q_value(float(obj))
            except Exception:
                pass
            if qsel.size == n:
                # Convert any real weights to a binary selection of exactly budget assets
                return _to_binary_selection(qsel, int(budget))
        except Exception:
            record_q_fallback()
            # fall through to classical
            pass

    # Classical heuristic: Sharpe-like score using diagonal risk proxy
    diag = np.diag(Sig)
    safe = np.sqrt(np.maximum(diag, 1e-12))
    scores = mu_arr / safe
    sel = _to_binary_selection(scores, int(budget))
    return sel.astype(int)
