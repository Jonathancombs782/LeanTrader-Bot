from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TradeRecord:
    ts: str
    pair: str
    session: str
    regime: str
    policy: str
    features: Dict[str, float]
    outcome: float  # pnl or R multiple
    costs: float
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayBuffer:
    limit: int = 10000
    buf: List[TradeRecord] = field(default_factory=list)

    def add(self, rec: TradeRecord):
        self.buf.append(rec)
        if len(self.buf) > self.limit:
            self.buf = self.buf[-self.limit :]

    def query(self, **filters) -> List[TradeRecord]:
        res = self.buf
        for k, v in filters.items():
            res = [r for r in res if getattr(r, k) == v]
        return res
