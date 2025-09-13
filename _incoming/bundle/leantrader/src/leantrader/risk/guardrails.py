from ..config import CFG


def position_size(equity: float, risk_cfg=CFG.risk) -> float:
    return max(
        min(
            risk_cfg.per_trade_risk_max,
            risk_cfg.per_trade_risk_min + (risk_cfg.per_trade_risk_max - risk_cfg.per_trade_risk_min) * 0.5,
        ),
        risk_cfg.per_trade_risk_min,
    )
