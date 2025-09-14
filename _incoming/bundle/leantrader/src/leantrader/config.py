import os

from pydantic import BaseModel


class RiskCfg(BaseModel):
    max_daily_dd: float = float(os.getenv("MAX_DAILY_DD", "0.02"))
    per_trade_risk_min: float = float(os.getenv("PER_TRADE_RISK_MIN", "0.001"))
    per_trade_risk_max: float = float(os.getenv("PER_TRADE_RISK_MAX", "0.005"))


class Config(BaseModel):
    data_dir: str = os.getenv("DATA_DIR", "./data")
    broker: str = os.getenv("BROKER", "paper")
    risk: RiskCfg = RiskCfg()


CFG = Config()
