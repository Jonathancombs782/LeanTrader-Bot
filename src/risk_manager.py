"""
Risk Manager for Trading Bot
Advanced risk management and portfolio protection
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
from dataclasses import dataclass

@dataclass
class RiskMetrics:
    """Risk metrics data structure"""
    portfolio_value: float
    total_exposure: float
    max_drawdown: float
    var_95: float  # Value at Risk 95%
    sharpe_ratio: float
    volatility: float
    correlation_risk: float
    concentration_risk: float
    leverage_risk: float

@dataclass
class RiskLimits:
    """Risk limits configuration"""
    max_position_size: float  # Maximum position size as % of portfolio
    max_total_exposure: float  # Maximum total exposure as % of portfolio
    max_drawdown: float  # Maximum drawdown %
    max_var: float  # Maximum Value at Risk
    max_correlation: float  # Maximum correlation between positions
    max_concentration: float  # Maximum concentration in single asset
    max_leverage: float  # Maximum leverage
    stop_loss_pct: float  # Default stop loss %
    take_profit_pct: float  # Default take profit %

class RiskManager:
    """Advanced risk management system for trading bot"""
    
    def __init__(self, database):
        self.database = database
        
        # Risk configuration
        self.limits = RiskLimits(
            max_position_size=float(os.getenv('MAX_POSITION_SIZE', 0.1)),
            max_total_exposure=float(os.getenv('MAX_TOTAL_EXPOSURE', 0.8)),
            max_drawdown=float(os.getenv('MAX_DRAWDOWN', 0.15)),
            max_var=float(os.getenv('MAX_VAR', 0.05)),
            max_correlation=float(os.getenv('MAX_CORRELATION', 0.7)),
            max_concentration=float(os.getenv('MAX_CONCENTRATION', 0.3)),
            max_leverage=float(os.getenv('MAX_LEVERAGE', 1.0)),
            stop_loss_pct=float(os.getenv('STOP_LOSS_PCT', 0.05)),
            take_profit_pct=float(os.getenv('TAKE_PROFIT_PCT', 0.1))
        )
        
        # Risk state
        self.current_metrics = None
        self.risk_history = []
        self.alert_levels = {
            'low': 0.5,
            'medium': 0.7,
            'high': 0.9,
            'critical': 1.0
        }
        
        # Risk monitoring
        self.risk_checks_enabled = True
        self.emergency_stop = False
        
    async def initialize(self):
        """Initialize the risk manager"""
        logger.info("🛡️ Initializing Risk Manager...")
        
        try:
            # Load risk history
            await self._load_risk_history()
            
            # Initialize risk metrics
            await self._calculate_initial_metrics()
            
            logger.info("✅ Risk Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize risk manager: {e}")
            raise
            
    async def _load_risk_history(self):
        """Load historical risk data"""
        try:
            # This would load from database in a real implementation
            self.risk_history = []
            logger.info("📊 Risk history loaded")
            
        except Exception as e:
            logger.error(f"Error loading risk history: {e}")
            
    async def _calculate_initial_metrics(self):
        """Calculate initial risk metrics"""
        try:
            # Get portfolio data
            portfolio_data = await self.database.get_portfolio_history(limit=100)
            
            if portfolio_data and len(portfolio_data) > 0:
                self.current_metrics = await self._calculate_risk_metrics(portfolio_data)
            else:
                # Default metrics
                self.current_metrics = RiskMetrics(
                    portfolio_value=float(os.getenv('INITIAL_CAPITAL', 10000)),
                    total_exposure=0.0,
                    max_drawdown=0.0,
                    var_95=0.0,
                    sharpe_ratio=0.0,
                    volatility=0.0,
                    correlation_risk=0.0,
                    concentration_risk=0.0,
                    leverage_risk=0.0
                )
                
            logger.info("📈 Initial risk metrics calculated")
            
        except Exception as e:
            logger.error(f"Error calculating initial metrics: {e}")
            
    async def calculate_risk_metrics(self, positions: Dict, portfolio_value: float, historical_data: Optional[pd.DataFrame] = None) -> RiskMetrics:
        """Calculate comprehensive risk metrics"""
        try:
            # Total exposure
            total_exposure = sum(pos.size * pos.current_price for pos in positions.values())
            exposure_pct = total_exposure / portfolio_value if portfolio_value > 0 else 0
            
            # Calculate returns for VaR and Sharpe ratio
            returns = []
            if historical_data is not None and len(historical_data) > 0:
                if 'portfolio_value' in historical_data.columns:
                    returns = historical_data['portfolio_value'].pct_change().dropna().values
                    
            # Value at Risk (95%)
            var_95 = np.percentile(returns, 5) if len(returns) > 0 else 0
            
            # Maximum drawdown
            max_drawdown = await self._calculate_max_drawdown(historical_data) if historical_data is not None else 0
            
            # Sharpe ratio
            sharpe_ratio = 0
            if len(returns) > 0:
                risk_free_rate = 0.02  # 2% annual risk-free rate
                excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
                sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252) if np.std(excess_returns) > 0 else 0
                
            # Volatility
            volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
            
            # Correlation risk
            correlation_risk = await self._calculate_correlation_risk(positions)
            
            # Concentration risk
            concentration_risk = await self._calculate_concentration_risk(positions, portfolio_value)
            
            # Leverage risk
            leverage_risk = exposure_pct  # Simplified for now
            
            metrics = RiskMetrics(
                portfolio_value=portfolio_value,
                total_exposure=exposure_pct,
                max_drawdown=max_drawdown,
                var_95=abs(var_95),
                sharpe_ratio=sharpe_ratio,
                volatility=volatility,
                correlation_risk=correlation_risk,
                concentration_risk=concentration_risk,
                leverage_risk=leverage_risk
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
            return RiskMetrics(
                portfolio_value=portfolio_value,
                total_exposure=0.0,
                max_drawdown=0.0,
                var_95=0.0,
                sharpe_ratio=0.0,
                volatility=0.0,
                correlation_risk=0.0,
                concentration_risk=0.0,
                leverage_risk=0.0
            )
            
    async def _calculate_max_drawdown(self, historical_data: pd.DataFrame) -> float:
        """Calculate maximum drawdown"""
        try:
            if historical_data is None or 'portfolio_value' not in historical_data.columns:
                return 0.0
                
            values = historical_data['portfolio_value'].values
            peak = np.maximum.accumulate(values)
            drawdown = (values - peak) / peak
            max_drawdown = abs(np.min(drawdown))
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0
            
    async def _calculate_correlation_risk(self, positions: Dict) -> float:
        """Calculate correlation risk between positions"""
        try:
            if len(positions) < 2:
                return 0.0
                
            # This is a simplified correlation calculation
            # In a real implementation, you would use actual price correlation data
            
            position_values = [pos.size * pos.current_price for pos in positions.values()]
            
            if len(position_values) < 2:
                return 0.0
                
            # Calculate correlation coefficient between position values
            correlation_matrix = np.corrcoef(position_values, position_values[::-1])
            max_correlation = np.max(np.abs(correlation_matrix[np.triu_indices_from(correlation_matrix, k=1)]))
            
            return max_correlation
            
        except Exception as e:
            logger.error(f"Error calculating correlation risk: {e}")
            return 0.0
            
    async def _calculate_concentration_risk(self, positions: Dict, portfolio_value: float) -> float:
        """Calculate concentration risk"""
        try:
            if portfolio_value <= 0 or len(positions) == 0:
                return 0.0
                
            position_values = [pos.size * pos.current_price for pos in positions.values()]
            max_position_value = max(position_values)
            concentration_risk = max_position_value / portfolio_value
            
            return concentration_risk
            
        except Exception as e:
            logger.error(f"Error calculating concentration risk: {e}")
            return 0.0
            
    async def can_open_position(self, symbol: str, position_value: float) -> bool:
        """Check if a new position can be opened based on risk limits"""
        try:
            if self.emergency_stop:
                logger.warning("🚨 Emergency stop active - blocking new positions")
                return False
                
            # Check position size limit
            if position_value > self.limits.max_position_size:
                logger.warning(f"🚫 Position size exceeds limit: {position_value:.2f} > {self.limits.max_position_size}")
                return False
                
            # Check total exposure limit
            current_exposure = self.current_metrics.total_exposure if self.current_metrics else 0
            new_exposure = current_exposure + position_value
            
            if new_exposure > self.limits.max_total_exposure:
                logger.warning(f"🚫 Total exposure would exceed limit: {new_exposure:.2f} > {self.limits.max_total_exposure}")
                return False
                
            # Check concentration limit
            if position_value > self.limits.max_concentration:
                logger.warning(f"🚫 Position concentration exceeds limit: {position_value:.2f} > {self.limits.max_concentration}")
                return False
                
            # Check correlation with existing positions
            if not await self._check_correlation_limit(symbol, position_value):
                logger.warning(f"🚫 Position correlation exceeds limit for {symbol}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error checking position limits: {e}")
            return False
            
    async def _check_correlation_limit(self, symbol: str, position_value: float) -> bool:
        """Check if new position violates correlation limits"""
        try:
            # This is a simplified check
            # In a real implementation, you would check actual correlation with existing positions
            
            # For now, allow all positions
            return True
            
        except Exception as e:
            logger.error(f"Error checking correlation limit: {e}")
            return True
            
    async def check_risk_limits(self, positions: Dict, portfolio_value: float):
        """Check all risk limits and take action if necessary"""
        try:
            if not self.risk_checks_enabled:
                return
                
            # Calculate current risk metrics
            self.current_metrics = await self.calculate_risk_metrics(positions, portfolio_value)
            
            # Check each risk limit
            risk_violations = []
            
            # Check exposure limit
            if self.current_metrics.total_exposure > self.limits.max_total_exposure:
                risk_violations.append(f"Total exposure: {self.current_metrics.total_exposure:.2%} > {self.limits.max_total_exposure:.2%}")
                
            # Check drawdown limit
            if self.current_metrics.max_drawdown > self.limits.max_drawdown:
                risk_violations.append(f"Max drawdown: {self.current_metrics.max_drawdown:.2%} > {self.limits.max_drawdown:.2%}")
                
            # Check VaR limit
            if self.current_metrics.var_95 > self.limits.max_var:
                risk_violations.append(f"VaR 95%: {self.current_metrics.var_95:.2%} > {self.limits.max_var:.2%}")
                
            # Check concentration limit
            if self.current_metrics.concentration_risk > self.limits.max_concentration:
                risk_violations.append(f"Concentration: {self.current_metrics.concentration_risk:.2%} > {self.limits.max_concentration:.2%}")
                
            # Check leverage limit
            if self.current_metrics.leverage_risk > self.limits.max_leverage:
                risk_violations.append(f"Leverage: {self.current_metrics.leverage_risk:.2%} > {self.limits.max_leverage:.2%}")
                
            # Take action based on violations
            if risk_violations:
                await self._handle_risk_violations(risk_violations, positions)
            else:
                # Log risk metrics
                logger.debug(f"📊 Risk metrics: Exposure={self.current_metrics.total_exposure:.2%}, "
                           f"Drawdown={self.current_metrics.max_drawdown:.2%}, "
                           f"VaR={self.current_metrics.var_95:.2%}")
                           
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            
    async def _handle_risk_violations(self, violations: List[str], positions: Dict):
        """Handle risk limit violations"""
        try:
            logger.warning(f"🚨 Risk limit violations detected: {violations}")
            
            # Determine severity
            severity = self._assess_risk_severity(violations)
            
            if severity == 'critical':
                # Emergency stop - close all positions
                logger.critical("🚨 CRITICAL RISK - Initiating emergency stop")
                self.emergency_stop = True
                await self._emergency_close_positions(positions)
                
            elif severity == 'high':
                # Close largest positions
                logger.warning("⚠️ HIGH RISK - Closing largest positions")
                await self._close_largest_positions(positions, close_pct=0.5)
                
            elif severity == 'medium':
                # Close some positions
                logger.warning("⚠️ MEDIUM RISK - Closing some positions")
                await self._close_largest_positions(positions, close_pct=0.3)
                
            else:  # low
                # Just log warning
                logger.warning("⚠️ LOW RISK - Monitoring closely")
                
        except Exception as e:
            logger.error(f"Error handling risk violations: {e}")
            
    def _assess_risk_severity(self, violations: List[str]) -> str:
        """Assess the severity of risk violations"""
        try:
            # Count violations and assess severity
            violation_count = len(violations)
            
            # Check for critical violations
            critical_keywords = ['drawdown', 'VaR']
            critical_violations = sum(1 for violation in violations 
                                    if any(keyword in violation.lower() for keyword in critical_keywords))
            
            if critical_violations > 0 or violation_count >= 3:
                return 'critical'
            elif violation_count >= 2:
                return 'high'
            elif violation_count >= 1:
                return 'medium'
            else:
                return 'low'
                
        except Exception as e:
            logger.error(f"Error assessing risk severity: {e}")
            return 'medium'
            
    async def _emergency_close_positions(self, positions: Dict):
        """Emergency close all positions"""
        try:
            logger.critical("🚨 EMERGENCY CLOSE - Closing all positions immediately")
            
            # This would trigger the bot to close all positions
            # In a real implementation, this would send signals to close positions
            
            # For now, just log the action
            for symbol in positions.keys():
                logger.critical(f"🚨 Emergency close signal for {symbol}")
                
        except Exception as e:
            logger.error(f"Error in emergency close: {e}")
            
    async def _close_largest_positions(self, positions: Dict, close_pct: float = 0.5):
        """Close largest positions to reduce risk"""
        try:
            if not positions:
                return
                
            # Sort positions by value (size * price)
            sorted_positions = sorted(
                positions.items(),
                key=lambda x: x[1].size * x[1].current_price,
                reverse=True
            )
            
            # Calculate how many positions to close
            positions_to_close = max(1, int(len(sorted_positions) * close_pct))
            
            logger.warning(f"🔄 Closing {positions_to_close} largest positions")
            
            for symbol, position in sorted_positions[:positions_to_close]:
                logger.warning(f"🔄 Risk management close signal for {symbol}")
                # This would trigger the bot to close the position
                
        except Exception as e:
            logger.error(f"Error closing largest positions: {e}")
            
    async def calculate_position_size(self, symbol: str, confidence: float, volatility: float, portfolio_value: float) -> float:
        """Calculate optimal position size using Kelly Criterion and risk management"""
        try:
            # Kelly Criterion: f = (bp - q) / b
            # where b = odds, p = probability of win, q = probability of loss
            
            # Simplified Kelly calculation
            win_rate = confidence
            avg_win = 0.05  # 5% average win
            avg_loss = 0.03  # 3% average loss
            
            kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
            
            # Apply risk management constraints
            max_kelly = min(kelly_fraction, 0.25)  # Cap at 25%
            
            # Adjust for volatility
            volatility_adjustment = 1 / (1 + volatility * 10)
            adjusted_size = max_kelly * volatility_adjustment
            
            # Apply position size limits
            final_size = min(adjusted_size, self.limits.max_position_size)
            
            # Calculate position value
            position_value = final_size * portfolio_value
            
            return position_value
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return self.limits.max_position_size * portfolio_value
            
    async def get_stop_loss_price(self, entry_price: float, side: str) -> float:
        """Calculate stop loss price"""
        try:
            if side.upper() == 'BUY' or side.upper() == 'LONG':
                return entry_price * (1 - self.limits.stop_loss_pct)
            else:  # SELL or SHORT
                return entry_price * (1 + self.limits.stop_loss_pct)
                
        except Exception as e:
            logger.error(f"Error calculating stop loss price: {e}")
            return entry_price * 0.95 if side.upper() == 'BUY' else entry_price * 1.05
            
    async def get_take_profit_price(self, entry_price: float, side: str) -> float:
        """Calculate take profit price"""
        try:
            if side.upper() == 'BUY' or side.upper() == 'LONG':
                return entry_price * (1 + self.limits.take_profit_pct)
            else:  # SELL or SHORT
                return entry_price * (1 - self.limits.take_profit_pct)
                
        except Exception as e:
            logger.error(f"Error calculating take profit price: {e}")
            return entry_price * 1.1 if side.upper() == 'BUY' else entry_price * 0.9
            
    async def update_risk_limits(self, new_limits: Dict):
        """Update risk limits configuration"""
        try:
            for key, value in new_limits.items():
                if hasattr(self.limits, key):
                    setattr(self.limits, key, value)
                    logger.info(f"Updated risk limit {key}: {value}")
                    
        except Exception as e:
            logger.error(f"Error updating risk limits: {e}")
            
    async def get_risk_report(self) -> Dict:
        """Generate comprehensive risk report"""
        try:
            return {
                'current_metrics': {
                    'portfolio_value': self.current_metrics.portfolio_value if self.current_metrics else 0,
                    'total_exposure': self.current_metrics.total_exposure if self.current_metrics else 0,
                    'max_drawdown': self.current_metrics.max_drawdown if self.current_metrics else 0,
                    'var_95': self.current_metrics.var_95 if self.current_metrics else 0,
                    'sharpe_ratio': self.current_metrics.sharpe_ratio if self.current_metrics else 0,
                    'volatility': self.current_metrics.volatility if self.current_metrics else 0,
                    'correlation_risk': self.current_metrics.correlation_risk if self.current_metrics else 0,
                    'concentration_risk': self.current_metrics.concentration_risk if self.current_metrics else 0,
                    'leverage_risk': self.current_metrics.leverage_risk if self.current_metrics else 0
                },
                'risk_limits': {
                    'max_position_size': self.limits.max_position_size,
                    'max_total_exposure': self.limits.max_total_exposure,
                    'max_drawdown': self.limits.max_drawdown,
                    'max_var': self.limits.max_var,
                    'max_correlation': self.limits.max_correlation,
                    'max_concentration': self.limits.max_concentration,
                    'max_leverage': self.limits.max_leverage,
                    'stop_loss_pct': self.limits.stop_loss_pct,
                    'take_profit_pct': self.limits.take_profit_pct
                },
                'status': {
                    'emergency_stop': self.emergency_stop,
                    'risk_checks_enabled': self.risk_checks_enabled,
                    'last_update': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating risk report: {e}")
            return {}
            
    async def is_healthy(self) -> bool:
        """Check if risk manager is healthy"""
        try:
            # Check if emergency stop is not active
            if self.emergency_stop:
                return False
                
            # Check if risk metrics are reasonable
            if self.current_metrics:
                if (self.current_metrics.total_exposure > 1.0 or  # More than 100% exposure
                    self.current_metrics.max_drawdown > 0.5):  # More than 50% drawdown
                    return False
                    
            return True
            
        except Exception:
            return False