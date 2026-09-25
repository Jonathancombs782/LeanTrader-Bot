"""Append-only evidence ledger (JSONL).

Every signal, fill, risk event, and equity snapshot is appended as one JSON
line. Nothing is ever edited or deleted — the ledger is the receipts drawer.
"""
from __future__ import annotations

import json
from pathlib import Path

from .receipts import Receipt, utcnow_iso

STREAMS = ("signals", "fills", "risk_events", "equity")


class Ledger:
    def __init__(self, root: str | Path = "paper/ledger"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, stream: str) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"unknown stream: {stream}")
        return self.root / f"{stream}.ndjson"

    def append(self, stream: str, record: dict) -> dict:
        record = {"logged_at": utcnow_iso(), **record}
        with self._path(stream).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return record

    def read(self, stream: str) -> list[dict]:
        path = self._path(stream)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def verify_receipts(self) -> dict[str, list[str]]:
        """Re-hash every stored payload referenced by signal receipts.

        Returns {signal_id: [failed receipt types]}; empty dict = all clean.
        """
        failures: dict[str, list[str]] = {}
        for sig in self.read("signals"):
            bad = []
            for r in sig.get("receipts", []):
                receipt = Receipt.from_dict(r)
                if receipt.payload_path and not receipt.verify_payload():
                    bad.append(receipt.type)
            if bad:
                failures[sig.get("signal_id", "?")] = bad
        return failures
