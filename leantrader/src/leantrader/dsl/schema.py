from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

Timeframe = Literal["D1", "H4", "H1", "M15", "M5", "M1"]


class Condition(BaseModel):
    feature: str
    timeframe: Timeframe
    lookback_ok: int = 0


class SignalRule(BaseModel):
    name: str
    side: Literal["long", "short"]
    entry: List[Condition]
    confirm_any: Optional[List[Condition]] = None
    exit: List[Condition] = []
    stop: Optional[str] = None
    take: Optional[str] = None


class StrategySpec(BaseModel):
    meta: Dict[str, str] = {}
    timeframes: List[Timeframe] = ["D1", "H4", "H1", "M15"]
    signals: List[SignalRule]
