"""Multi-timeframe aggregator.

Reads candidate signals from `runtime/signals-<date>.ndjson` (or accept a list)
and produces a reduced set where a symbol+side is agreed across multiple timeframes.

Simple strategy:
- Group signals by (market,symbol,side)
- For each group, consider unique timeframes present and compute an "agreement_score"
  = (# of TFs present) / (# of TFs configured)
- Promote signals where agreement_score >= threshold (default 1.0 means all TFs present)

This is intentionally conservative: you can configure `REQUIRED_TFS` via env var
to control the TFs to require (comma-separated, e.g., '1m,5m,1h,4h').
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Load .env if present so CLI/script runs pick up configuration without shell export
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"

DEFAULT_TFS = [t.strip().lower() for t in os.getenv("MTF_REQUIRED_TFS", "1m,5m,1h,4h").split(",") if t.strip()]
THRESHOLD = float(os.getenv("MTF_THRESHOLD", "1.0"))


def _read_ndjson(path: Path) -> List[Dict]:
    out = []
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def aggregate_signals(signals: List[Dict]) -> List[Dict]:
    # normalize tfs and group
    by_key = defaultdict(list)
    for s in signals:
        key = (s.get("market", ""), s.get("symbol", ""), s.get("side", ""))
        by_key[key].append(s)

    out: List[Dict] = []
    required = [t.strip().lower() for t in DEFAULT_TFS if t.strip()]

    for key, items in by_key.items():
        tfs = set([str(i.get("tf", "")).lower() for i in items])
        # If any item is already marked as promoted with mtf_agreement, honor that value
        pre_promoted = [i for i in items if isinstance(i.get("mtf_agreement"), (int, float))]
        if pre_promoted:
            # pick the max precomputed agreement
            agreement = max(float(i.get("mtf_agreement", 0.0)) for i in pre_promoted)
        else:
            agreement = len(tfs.intersection(required)) / max(1, len(required))
        # choose the highest-confidence representative
        rep = max(items, key=lambda x: float(x.get("confidence", 0.0)))
        rep = dict(rep)
        rep["mtf_agreement"] = agreement
        rep["mtf_tfs"] = list(tfs)
        if agreement >= THRESHOLD:
            out.append(rep)
    return out


def read_and_aggregate(queue_dir: str | Path = None) -> List[Dict]:
    qd = Path(queue_dir) if queue_dir else RUNTIME
    day = datetime.utcnow().strftime("%Y%m%d")
    p = qd / f"signals-{day}.ndjson"
    if not p.exists():
        # fallback to any signals file in runtime
        for f in qd.glob("signals-*.ndjson"):
            p = f
            break
    signals = _read_ndjson(p)
    return aggregate_signals(signals)


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else None
    out = read_and_aggregate(q)
    print(json.dumps(out, indent=2))
