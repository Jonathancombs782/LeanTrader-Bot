# guardrails.py
from dataclasses import dataclass

@dataclass
class GuardConfig:
    cooldown_bars: int = 3
    max_loss_streak: int = 3
    daily_profit_lock_bps: int = 50
    spread_bps_threshold: int = 8
    max_trades_per_day: int = 40

class TradeGuard:
    def __init__(self, cfg: GuardConfig):
        self.cfg = cfg
        self.cooldown = 0
        self.loss_streak = 0
        self.trades_today = 0

    def on_new_bar(self):
        if self.cooldown > 0:
            self.cooldown -= 1

    def can_enter_now(self, spread_bps: float) -> bool:
        if self.cooldown > 0:
            return False
        if self.trades_today >= self.cfg.max_trades_per_day:
            return False
        if spread_bps > self.cfg.spread_bps_threshold:
            return False
        return True

    def record_exit(self, pnl: float):
        self.trades_today += 1
        if pnl < 0:
            self.loss_streak += 1
        else:
            self.loss_streak = 0
        self.cooldown = max(self.cooldown, self.cfg.cooldown_bars)

    def require_pause(self) -> bool:
        return self.loss_streak >= self.cfg.max_loss_streak
    def reset_daily(self):
        self.trades_today = 0
        self.loss_streak = 0
        self.cooldown = 0
        