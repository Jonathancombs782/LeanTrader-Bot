"""
Risk Management System
Handles position sizing, risk limits, and safety checks
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum

from .order_manager import OrderSide, OrderType


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskCheck:
    allowed: bool
    reason: str
    risk_level: RiskLevel
    suggested_size: Optional[float] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class Position:
    symbol: str
    amount: float
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    timestamp: datetime


class RiskManager:
    """Comprehensive risk management system"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger("risk_manager")
        
        # Risk limits
        self.max_position_size = self.config.get("max_position_size", 0.1)  # 10% of portfolio
        self.max_total_exposure = self.config.get("max_total_exposure", 0.8)  # 80% of portfolio
        self.max_drawdown = self.config.get("max_drawdown", 0.15)  # 15% max drawdown
        self.max_var = self.config.get("max_var", 0.05)  # 5% VaR
        self.max_correlation = self.config.get("max_correlation", 0.7)  # 70% max correlation
        self.max_concentration = self.config.get("max_concentration", 0.3)  # 30% max concentration
        
        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.portfolio_value = self.config.get("initial_capital", 10000.0)
        self.peak_value = self.portfolio_value
        self.current_drawdown = 0.0
        
        # Risk metrics
        self.daily_pnl: List[float] = []
        self.volatility_window = 30  # days
        
    def update_portfolio_value(self, value: float):
        """Update portfolio value and calculate drawdown"""
        self.portfolio_value = value
        
        if value > self.peak_value:
            self.peak_value = value
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = (self.peak_value - value) / self.peak_value
    
    def update_position(self, symbol: str, amount: float, price: float, realized_pnl: float = 0.0):
        """Update position information"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.amount = amount
            pos.current_price = price
            pos.unrealized_pnl = amount * (price - pos.average_price)
            pos.realized_pnl += realized_pnl
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                amount=amount,
                average_price=price,
                current_price=price,
                unrealized_pnl=0.0,
                realized_pnl=realized_pnl,
                timestamp=datetime.now(timezone.utc)
            )
    
    async def check_order_risk(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        price: Optional[float],
        order_type: OrderType
    ) -> RiskCheck:
        """Comprehensive risk check for an order"""
        warnings = []
        
        # 1. Position size check
        position_size_check = self._check_position_size(symbol, amount, price)
        if not position_size_check.allowed:
            return position_size_check
        warnings.extend(position_size_check.warnings)
        
        # 2. Total exposure check
        exposure_check = self._check_total_exposure(symbol, amount, price)
        if not exposure_check.allowed:
            return exposure_check
        warnings.extend(exposure_check.warnings)
        
        # 3. Drawdown check
        drawdown_check = self._check_drawdown()
        if not drawdown_check.allowed:
            return drawdown_check
        warnings.extend(drawdown_check.warnings)
        
        # 4. VaR check
        var_check = self._check_var(symbol, amount, price)
        if not var_check.allowed:
            return var_check
        warnings.extend(var_check.warnings)
        
        # 5. Correlation check
        correlation_check = self._check_correlation(symbol, amount, price)
        if not correlation_check.allowed:
            return correlation_check
        warnings.extend(correlation_check.warnings)
        
        # 6. Concentration check
        concentration_check = self._check_concentration(symbol, amount, price)
        if not concentration_check.allowed:
            return concentration_check
        warnings.extend(concentration_check.warnings)
        
        # Determine overall risk level
        risk_level = self._calculate_risk_level(warnings)
        
        return RiskCheck(
            allowed=True,
            reason="All risk checks passed",
            risk_level=risk_level,
            warnings=warnings
        )
    
    def _check_position_size(self, symbol: str, amount: float, price: Optional[float]) -> RiskCheck:
        """Check if position size is within limits"""
        if not price:
            return RiskCheck(True, "Price not available for position size check", RiskLevel.LOW)
        
        order_value = amount * price
        max_order_value = self.portfolio_value * self.max_position_size
        
        if order_value > max_order_value:
            suggested_size = (max_order_value / price) * 0.9  # 90% of max
            return RiskCheck(
                False,
                f"Order value ${order_value:.2f} exceeds max position size ${max_order_value:.2f}",
                RiskLevel.HIGH,
                suggested_size=suggested_size
            )
        
        if order_value > max_order_value * 0.8:
            return RiskCheck(
                True,
                "Position size within limits",
                RiskLevel.MEDIUM,
                warnings=["Position size approaching limit"]
            )
        
        return RiskCheck(True, "Position size within limits", RiskLevel.LOW)
    
    def _check_total_exposure(self, symbol: str, amount: float, price: Optional[float]) -> RiskCheck:
        """Check total portfolio exposure"""
        if not price:
            return RiskCheck(True, "Price not available for exposure check", RiskLevel.LOW)
        
        # Calculate current exposure
        current_exposure = sum(
            abs(pos.amount * pos.current_price) for pos in self.positions.values()
        )
        
        new_exposure = current_exposure + (amount * price)
        max_exposure = self.portfolio_value * self.max_total_exposure
        
        if new_exposure > max_exposure:
            return RiskCheck(
                False,
                f"Total exposure ${new_exposure:.2f} would exceed limit ${max_exposure:.2f}",
                RiskLevel.HIGH
            )
        
        if new_exposure > max_exposure * 0.8:
            return RiskCheck(
                True,
                "Total exposure within limits",
                RiskLevel.MEDIUM,
                warnings=["Total exposure approaching limit"]
            )
        
        return RiskCheck(True, "Total exposure within limits", RiskLevel.LOW)
    
    def _check_drawdown(self) -> RiskCheck:
        """Check current drawdown"""
        if self.current_drawdown > self.max_drawdown:
            return RiskCheck(
                False,
                f"Current drawdown {self.current_drawdown:.2%} exceeds limit {self.max_drawdown:.2%}",
                RiskLevel.CRITICAL
            )
        
        if self.current_drawdown > self.max_drawdown * 0.8:
            return RiskCheck(
                True,
                "Drawdown within limits",
                RiskLevel.MEDIUM,
                warnings=["Drawdown approaching limit"]
            )
        
        return RiskCheck(True, "Drawdown within limits", RiskLevel.LOW)
    
    def _check_var(self, symbol: str, amount: float, price: Optional[float]) -> RiskCheck:
        """Check Value at Risk"""
        if not price or len(self.daily_pnl) < 10:
            return RiskCheck(True, "Insufficient data for VaR calculation", RiskLevel.LOW)
        
        # Simple VaR calculation (95% confidence)
        sorted_pnl = sorted(self.daily_pnl)
        var_index = int(len(sorted_pnl) * 0.05)
        var_95 = sorted_pnl[var_index] if var_index < len(sorted_pnl) else 0
        
        # Estimate impact of new position
        position_impact = amount * price * 0.01  # Assume 1% daily volatility
        
        if abs(var_95 + position_impact) > self.portfolio_value * self.max_var:
            return RiskCheck(
                False,
                f"VaR would exceed limit {self.max_var:.2%}",
                RiskLevel.HIGH
            )
        
        return RiskCheck(True, "VaR within limits", RiskLevel.LOW)
    
    def _check_correlation(self, symbol: str, amount: float, price: Optional[float]) -> RiskCheck:
        """Check correlation with existing positions"""
        if len(self.positions) < 2:
            return RiskCheck(True, "Insufficient positions for correlation check", RiskLevel.LOW)
        
        # Simplified correlation check - in practice would use actual price correlation
        # For now, just check if we're adding to an existing position
        if symbol in self.positions:
            existing_amount = self.positions[symbol].amount
            if (existing_amount > 0 and amount > 0) or (existing_amount < 0 and amount < 0):
                return RiskCheck(
                    True,
                    "Adding to existing position",
                    RiskLevel.MEDIUM,
                    warnings=["Adding to existing position increases concentration"]
                )
        
        return RiskCheck(True, "Correlation check passed", RiskLevel.LOW)
    
    def _check_concentration(self, symbol: str, amount: float, price: Optional[float]) -> RiskCheck:
        """Check concentration in single asset"""
        if not price:
            return RiskCheck(True, "Price not available for concentration check", RiskLevel.LOW)
        
        position_value = amount * price
        max_concentration_value = self.portfolio_value * self.max_concentration
        
        if position_value > max_concentration_value:
            return RiskCheck(
                False,
                f"Position concentration ${position_value:.2f} exceeds limit ${max_concentration_value:.2f}",
                RiskLevel.HIGH
            )
        
        return RiskCheck(True, "Concentration within limits", RiskLevel.LOW)
    
    def _calculate_risk_level(self, warnings: List[str]) -> RiskLevel:
        """Calculate overall risk level based on warnings"""
        if len(warnings) >= 3:
            return RiskLevel.HIGH
        elif len(warnings) >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def calculate_position_size(
        self,
        symbol: str,
        side: OrderSide,
        confidence: float,
        stop_loss_pct: float,
        risk_per_trade: float = 0.02
    ) -> float:
        """Calculate optimal position size using Kelly Criterion and risk management"""
        
        # Kelly Criterion: f = (bp - q) / b
        # where b = odds, p = probability of win, q = probability of loss
        
        # Simplified calculation
        win_rate = confidence
        avg_win = 1.0 + (stop_loss_pct * 2)  # Assume 2:1 reward/risk
        avg_loss = 1.0 - stop_loss_pct
        
        kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        
        # Apply safety factor and risk limits
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
        kelly_fraction *= 0.5  # Safety factor
        
        # Calculate position size
        risk_amount = self.portfolio_value * risk_per_trade
        position_value = risk_amount / stop_loss_pct
        position_size = position_value * kelly_fraction
        
        # Apply position size limits
        max_position_value = self.portfolio_value * self.max_position_size
        position_size = min(position_size, max_position_value)
        
        return position_size
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics"""
        total_exposure = sum(abs(pos.amount * pos.current_price) for pos in self.positions.values())
        total_pnl = sum(pos.unrealized_pnl + pos.realized_pnl for pos in self.positions.values())
        
        return {
            "portfolio_value": self.portfolio_value,
            "peak_value": self.peak_value,
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "total_exposure": total_exposure,
            "exposure_ratio": total_exposure / self.portfolio_value if self.portfolio_value > 0 else 0,
            "max_exposure": self.portfolio_value * self.max_total_exposure,
            "total_pnl": total_pnl,
            "num_positions": len(self.positions),
            "risk_level": self._calculate_risk_level([]).value
        }
    
    def add_daily_pnl(self, pnl: float):
        """Add daily P&L for VaR calculation"""
        self.daily_pnl.append(pnl)
        if len(self.daily_pnl) > self.volatility_window * 2:
            self.daily_pnl = self.daily_pnl[-self.volatility_window:]
    
    def should_reduce_risk(self) -> bool:
        """Check if risk should be reduced"""
        return (
            self.current_drawdown > self.max_drawdown * 0.8 or
            len(self.positions) > 10 or
            any(abs(pos.amount * pos.current_price) > self.portfolio_value * self.max_concentration 
                for pos in self.positions.values())
        )
    
    def get_risk_recommendations(self) -> List[str]:
        """Get risk management recommendations"""
        recommendations = []
        
        if self.current_drawdown > self.max_drawdown * 0.8:
            recommendations.append("Consider reducing position sizes due to high drawdown")
        
        if len(self.positions) > 10:
            recommendations.append("Consider consolidating positions - too many open positions")
        
        total_exposure = sum(abs(pos.amount * pos.current_price) for pos in self.positions.values())
        if total_exposure > self.portfolio_value * self.max_total_exposure * 0.8:
            recommendations.append("Total exposure approaching limit - consider reducing positions")
        
        return recommendations