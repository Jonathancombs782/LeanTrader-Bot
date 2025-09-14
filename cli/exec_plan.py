from __future__ import annotations

import json
import sys

from execution.quantum_exec import quantum_exec_plan


def main():
    import argparse

    p = argparse.ArgumentParser(description="Execution plan demo")
    p.add_argument("--qty", type=int, default=100)
    p.add_argument("--venues", type=str, default="bybit,binance,okx")
    p.add_argument("--costs", type=str, default="1.0,0.8,1.2")
    p.add_argument("--slices", type=int, default=5)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--use-runtime", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    try:
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
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

