from __future__ import annotations

import argparse
import os
from security.vault import secure_write


def main() -> int:
    p = argparse.ArgumentParser(description="Securely snapshot selected env vars")
    p.add_argument("--out", default=os.getenv("SECRETS_SNAPSHOT_OUT", "runtime/secrets_snapshot.enc"))
    p.add_argument("--keys", default=os.getenv("SECRETS_KEYS", "API_KEY,API_SECRET,REDIS_URL"))
    args = p.parse_args()

    keys = [s.strip() for s in args.keys.split(",") if s.strip()]
    data = {k: os.getenv(k, "") for k in keys}
    secure_write(args.out, data)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

