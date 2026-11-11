"""Append-only evidence ledger (JSONL).

Every signal, fill, risk event, and equity snapshot is appended as one JSON
line. Nothing is ever edited or deleted — the ledger is the receipts drawer.

Hash chain (Nov 11, 2026 — B4/D4): every NEW line carries `prev_hash`
(hash of the previous line) + `record_sha` (SHA-256 of this line's content
including `prev_hash`). `verify_chain()` walks a stream and fails on any
edited, deleted, reordered, or unchained-after-chained line.

The chain starts at the next append: lines written before Nov 11, 2026
carry no chain fields and are left exactly as they are (annotate, never
delete). They are the legacy prefix — `verify_chain()` counts them as
legacy, not as failures. The first chained line after a legacy prefix
anchors on the SHA-256 of the previous line's raw bytes, so the legacy
history is still bound into the chain. A stream's very first line uses
prev_hash "GENESIS".

Caveats: the chain proves a line's content and order, not that an
in-place edit was never made to a legacy line — legacy lines have no
record_sha to check against. And in-place annotation of a CHAINED line
invalidates its record_sha: `paper.annotate_ledger` refuses to run once
any line carries a record_sha (it is a one-time, pre-chain script).
Appends read the stream tail fresh each time, but there is no file
locking — two processes appending to the same stream concurrently can
still fork the chain, exactly as they could already interleave lines.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .receipts import Receipt, utcnow_iso

STREAMS = ("signals", "fills", "risk_events", "equity")

GENESIS_PREV_HASH = "GENESIS"


def _canonical(record: dict) -> bytes:
    """Canonical bytes of a record for hashing: sorted keys, no spaces."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_sha(record: dict) -> str:
    """SHA-256 of a line's content (everything except record_sha itself)."""
    content = {k: v for k, v in record.items() if k != "record_sha"}
    return _sha256(_canonical(content))


class Ledger:
    def __init__(self, root: str | Path = "paper/ledger"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, stream: str) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"unknown stream: {stream}")
        return self.root / f"{stream}.ndjson"

    def _tail_hash(self, stream: str) -> str:
        """Hash the stream's last line anchors the next append to.

        Returns the last line's record_sha when it has one, else the
        SHA-256 of the last line's raw bytes (legacy anchor), else
        GENESIS for an empty stream. Raises ValueError if the tail line
        is not valid JSON — never extend a corrupt chain silently.
        """
        path = self._path(stream)
        if not path.exists():
            return GENESIS_PREV_HASH
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        if not lines:
            return GENESIS_PREV_HASH
        try:
            last = json.loads(lines[-1])
        except json.JSONDecodeError as e:
            raise ValueError(
                f"cannot append to {stream}: last line is not valid JSON "
                f"({e}) — refusing to extend a corrupt chain") from e
        if isinstance(last, dict) and last.get("record_sha"):
            return last["record_sha"]
        return _sha256(lines[-1].encode("utf-8"))

    def append(self, stream: str, record: dict) -> dict:
        record = {"logged_at": utcnow_iso(), **record,
                  "prev_hash": self._tail_hash(stream)}
        record["record_sha"] = _record_sha(record)
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

    def verify_chain(self, stream: str) -> dict:
        """Check one stream's hash chain.

        Returns {"stream", "ok", "chained", "legacy", "failures"}.
        Legacy (pre-chain) lines are valid only as a prefix: any legacy
        line after a chained line, any prev_hash mismatch, any record_sha
        mismatch, and any unparseable line is a failure.
        """
        path = self._path(stream)
        result: dict = {"stream": stream, "ok": True, "chained": 0,
                        "legacy": 0, "failures": []}
        if not path.exists():
            return result
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        prev_expected = GENESIS_PREV_HASH
        seen_chained = False
        for i, raw in enumerate(lines, start=1):
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                result["ok"] = False
                result["failures"].append(f"line {i}: not valid JSON")
                return result
            if not isinstance(rec, dict) or not rec.get("record_sha"):
                if seen_chained:
                    result["ok"] = False
                    result["failures"].append(
                        f"line {i}: unchained line after chained history "
                        f"— chain broken")
                    return result
                result["legacy"] += 1
                prev_expected = _sha256(raw.encode("utf-8"))
                continue
            seen_chained = True
            result["chained"] += 1
            if rec.get("prev_hash") != prev_expected:
                result["ok"] = False
                result["failures"].append(
                    f"line {i}: prev_hash mismatch (expected "
                    f"{prev_expected[:16]}…, got "
                    f"{str(rec.get('prev_hash'))[:16]}…) — line deleted, "
                    f"reordered, or edited")
                return result
            if rec["record_sha"] != _record_sha(rec):
                result["ok"] = False
                result["failures"].append(
                    f"line {i}: record_sha mismatch — line content edited "
                    f"after it was written")
                return result
            prev_expected = rec["record_sha"]
        return result

    def verify_all_chains(self) -> dict[str, dict]:
        """verify_chain() for every stream."""
        return {s: self.verify_chain(s) for s in STREAMS}
