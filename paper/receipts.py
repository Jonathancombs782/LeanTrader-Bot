"""Evidence receipts: pin every claim to data anyone can re-check.

A receipt records *where* a fact came from, *when* it was observed, and the
SHA-256 of the exact payload — so a skeptic can re-fetch or re-hash instead of
trusting us.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Receipt:
    """One verifiable fact backing a signal."""

    type: str           # e.g. "coingecko_price_snapshot", "block_explorer_tx"
    source: str         # URL or identifier of the origin
    observed_at: str    # ISO-8601 UTC when we captured it
    sha256: str         # hash of the captured payload
    payload_path: str | None = None  # local evidence file, if we kept one
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Receipt":
        return cls(**d)

    def verify_payload(self) -> bool:
        """Re-hash the stored payload; True if it matches the receipt."""
        if not self.payload_path:
            return False
        try:
            return hash_file(self.payload_path) == self.sha256
        except OSError:
            return False
