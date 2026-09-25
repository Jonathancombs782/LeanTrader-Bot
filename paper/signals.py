"""Signals: evidence-bearing trade ideas.

A Signal bundles the trade plan (side/entry/stop/target) with the receipts
that justify it and a hash of the inputs that produced it. Same inputs +
same code => same signal (reproducibility is the whole point).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum

from .receipts import Receipt, utcnow_iso


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: SignalSide
    entry: float
    stop: float
    target: float
    thesis: str
    receipts: tuple[Receipt, ...] = ()
    inputs: dict = field(default_factory=dict)  # raw inputs that produced it
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=utcnow_iso)

    def __post_init__(self):
        if self.entry <= 0 or self.stop <= 0 or self.target <= 0:
            raise ValueError("entry/stop/target must be positive")
        if self.side == SignalSide.LONG:
            if not (self.stop < self.entry < self.target):
                raise ValueError("long requires stop < entry < target")
        else:
            if not (self.target < self.entry < self.stop):
                raise ValueError("short requires target < entry < stop")
        if not self.thesis.strip():
            raise ValueError("thesis is required — no naked signals")

    @property
    def inputs_hash(self) -> str:
        payload = json.dumps(self.inputs, sort_keys=True, default=str).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.stop)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["side"] = self.side.value
        d["receipts"] = [r.to_dict() for r in self.receipts]
        d["inputs_hash"] = self.inputs_hash
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Signal":
        d = dict(d)
        d.pop("inputs_hash", None)
        d["side"] = SignalSide(d["side"])
        d["receipts"] = tuple(Receipt.from_dict(r) for r in d.get("receipts", []))
        return cls(**d)
