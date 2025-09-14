from dataclasses import dataclass
from typing import Literal

PolicyID = Literal["house_smc", "trader_ensemble"]


@dataclass
class Context:
    pair: str
    session: Literal["asia", "london", "ny"]
    regime: Literal["trend", "range", "news"]
    vol_bucket: Literal["low", "med", "high"]
    news_window: Literal["pre", "post", "none"]


def route(ctx: Context) -> PolicyID:
    if ctx.regime == "trend" and ctx.vol_bucket in ("med", "high") and ctx.news_window != "pre":
        return "house_smc"
    return "trader_ensemble"
