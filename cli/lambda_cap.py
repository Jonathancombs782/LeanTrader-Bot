from __future__ import annotations

import argparse
import json
import sys

from ops.auto_throttle import set_lambda_cap, get_lambda_cap, clear_lambda_cap


def main():
    p = argparse.ArgumentParser(description="Get/Set/Clear ensemble lambda cap")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", dest="setval", type=float, help="set cap value (e.g., 0.4)")
    g.add_argument("--clear", action="store_true", help="clear cap")
    g.add_argument("--get", action="store_true", help="get current cap")
    args = p.parse_args()

    try:
        if args.setval is not None:
            set_lambda_cap(float(args.setval))
            print(json.dumps({"cap": float(args.setval)}))
        elif args.clear:
            clear_lambda_cap()
            print(json.dumps({"cap": None}))
        elif args.get:
            cap = get_lambda_cap(None)
            print(json.dumps({"cap": cap}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

