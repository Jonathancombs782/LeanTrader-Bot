from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from qiskit_optimization import QuadraticProgram  # type: ignore
    from qiskit_optimization.algorithms import MinimumEigenOptimizer  # type: ignore
    from qiskit_algorithms import QAOA  # type: ignore
    from qiskit.primitives import Sampler  # type: ignore
except Exception:  # pragma: no cover
    QuadraticProgram = None  # type: ignore
    MinimumEigenOptimizer = None  # type: ignore
    QAOA = None  # type: ignore
    Sampler = None  # type: ignore


def build_exec_qubo(
    target_qty: int,
    venues: List[str],
    costs: List[float],
    max_slices: int,
    imbalance_lambda: float = 0.1,
):
    """Build a QuadraticProgram for venue execution allocation.

    Variables: y_{v,k} in {0,1} indicating slice k routes to venue v.
    Constraints: Exactly one venue per slice (sum_v y_{v,k} == 1).
    Objective: Minimize linear execution costs + imbalance penalty toward equal share.
    """
    if QuadraticProgram is None:
        raise RuntimeError("qiskit_optimization is required to build QUBO")

    n = len(venues)
    if len(costs) != n:
        raise ValueError("costs length must match venues length")

    qp = QuadraticProgram("venue_exec")
    # Create binary variables y_i_k
    var_names: List[str] = []
    for i in range(n):
        for k in range(max_slices):
            name = f"y_{i}_{k}"
            qp.binary_var(name)
            var_names.append(name)

    # Linear cost term: per-slice qty * venue cost
    slice_qty = float(target_qty) / float(max(1, max_slices))
    linear = {f"y_{i}_{k}": float(costs[i]) * slice_qty for i in range(n) for k in range(max_slices)}
    qp.minimize(linear=linear)

    # Imbalance penalty toward equal number of slices per venue
    # Add quadratic penalty: lambda * sum_v (nv - ideal)^2 where nv = sum_k y_{v,k}
    ideal = float(max_slices) / float(max(1, n))
    quad_linear: Dict[str, float] = {}
    quad_quad: Dict[Tuple[str, str], float] = {}
    for i in range(n):
        # nv^2 expands into sum_k y + 2 sum_{k<l} y_k y_l because y^2=y for binaries
        ys = [f"y_{i}_{k}" for k in range(max_slices)]
        for a in range(max_slices):
            name_a = ys[a]
            quad_linear[name_a] = quad_linear.get(name_a, 0.0) + imbalance_lambda * (1.0 - 2.0 * ideal)
            for b in range(a + 1, max_slices):
                name_b = ys[b]
                key = tuple(sorted((name_a, name_b)))
                quad_quad[key] = quad_quad.get(key, 0.0) + imbalance_lambda * 2.0

    # Add to current objective
    obj = qp.objective
    obj.linear.update({k: obj.linear.get(k, 0.0) + v for k, v in quad_linear.items()})
    for (a, b), w in quad_quad.items():
        obj.quadratic[a, b] = obj.quadratic.get((a, b), 0.0) + w

    # Constraints: exactly one venue per slice
    for k in range(max_slices):
        vars_for_slice = [f"y_{i}_{k}" for i in range(n)]
        qp.linear_constraint(linear={name: 1 for name in vars_for_slice}, sense="==", rhs=1, name=f"one_per_slice_{k}")

    return qp


def _solve_qaoa(qp, reps: int = 1, seed: int = 42, use_runtime: bool = True):
    if QAOA is None or MinimumEigenOptimizer is None:
        raise RuntimeError("qiskit_algorithms / optimization missing")

    # Prefer local sampler; try Runtime if requested
    sampler = None
    if use_runtime:
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService, Sampler as RuntimeSampler  # type: ignore

            token = None
            try:
                import os

                token = os.getenv("IBM_QUANTUM_API_KEY", "").strip() or None
            except Exception:
                token = None
            if token:
                _ = QiskitRuntimeService(channel="ibm_quantum", token=token)
            else:
                _ = QiskitRuntimeService()
            sampler = RuntimeSampler()  # default account/session
        except Exception:
            sampler = None
    if sampler is None:
        sampler = Sampler()

    qaoa = QAOA(reps=int(reps), sampler=sampler, seed=seed)
    opt = MinimumEigenOptimizer(qaoa)
    result = opt.solve(qp)
    return result


def quantum_exec_plan(
    target_qty: int,
    venues: List[str],
    costs: List[float],
    max_slices: int = 5,
    reps: int = 1,
    use_runtime: bool = True,
    seed: int = 42,
) -> Dict[str, object]:
    """Solve execution allocation via QUBO/QAOA. Fallback to equal TWAP.

    Returns dict: {plan: [{venue, qty}], slice_qty, method}
    """
    n = len(venues)
    slice_qty = float(target_qty) / float(max(1, max_slices))

    # Observe planning time
    try:
        from observability.metrics import time_exec_plan  # type: ignore
    except Exception:  # pragma: no cover
        from contextlib import contextmanager

        @contextmanager
        def time_exec_plan(name: str):
            yield

    with time_exec_plan("exec_plan"):
        try:
            qp = build_exec_qubo(target_qty, venues, costs, max_slices)
            res = _solve_qaoa(qp, reps=reps, seed=seed, use_runtime=use_runtime)
            # Extract y_{i,k}
            assign = np.zeros(n, dtype=int)
            for i in range(n):
                for k in range(max_slices):
                    var = f"y_{i}_{k}"
                    val = int(round(float(res.variables_dict.get(var, 0))))
                    assign[i] += val
            plan = []
            for i, v in enumerate(venues):
                if assign[i] <= 0:
                    continue
                plan.append({"venue": v, "qty": float(assign[i]) * slice_qty})
            if not plan:
                # edge: degenerate solution; fall back
                raise RuntimeError("empty plan")
            return {"plan": plan, "slice_qty": slice_qty, "method": "qaoa"}
        except Exception:
            # Fallback: equal TWAP across venues
            per_venue = float(target_qty) / float(max(1, n))
            plan = [{"venue": v, "qty": per_venue} for v in venues]
            return {"plan": plan, "slice_qty": per_venue, "method": "twap_equal"}


def _main():
    import argparse

    p = argparse.ArgumentParser(description="Quantum execution plan demo")
    p.add_argument("--qty", type=int, default=100)
    p.add_argument("--venues", type=str, default="bybit,binance,okx")
    p.add_argument("--costs", type=str, default="1.0,0.8,1.2")
    p.add_argument("--slices", type=int, default=5)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--use-runtime", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    venues = [s.strip() for s in args.venues.split(",") if s.strip()]
    costs = [float(x) for x in args.costs.split(",")]
    out = quantum_exec_plan(
        target_qty=int(args.qty),
        venues=venues,
        costs=costs,
        max_slices=int(args.slices),
        reps=int(args.reps),
        use_runtime=bool(args.use_runtime),
        seed=int(args.seed),
    )
    print(json.dumps(out))


if __name__ == "__main__":
    _main()
