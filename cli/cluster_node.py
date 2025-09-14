from __future__ import annotations

import argparse

from infra.process.supervisor import Supervisor


def main() -> int:
    p = argparse.ArgumentParser(description="Cluster node supervisor")
    p.add_argument("--role", choices=["leader", "standby"], default="standby")
    p.add_argument("--namespace", default="lt")
    p.add_argument("--node-id", default="")
    p.add_argument("--ttl", type=int, default=15)
    p.add_argument("--redis", default="")
    p.add_argument("--http-port", type=int, default=8081)
    args = p.parse_args()

    sup = Supervisor(node_id=(args.node_id or "node"), namespace=args.namespace, ttl_sec=args.ttl, redis_url=(args.redis or None))
    sup.run(role=args.role, http_port=args.http_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

