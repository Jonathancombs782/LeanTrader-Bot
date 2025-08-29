# risk.py
from dataclasses import dataclass

@dataclass
class RiskConfig:
    initial_equity: float = 10000.0
    risk_per_trade_bps: float = 50.0
    max_daily_loss_bps: float = 100.0
    max_open_positions: int = 2
    atr_stop_mult: float = 2.0
    atr_trail_mult: float = 1.3
    atr_period: int = 14
    min_atr: float = 0.0003
    fixed_stake_usd: float = 1.0
    max_drawdown_bps: float = 100.0
    min_drawdown_bps: float = 0.0
    max_position_size: float = 1.0
    min_position_size: float = 0.01
    position_size_step: float = 0.01
    max_position_size: float = 1.0
    min_position_size: float = 0.01
    position_size_step: float = 0.01
    max_position_size: float = 1.0
    min_position_size: float = 0.01
    position_size_step: float = 0.01
    max_position_size: float = 1.0
    