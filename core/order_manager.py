"""
Order Management System
Handles order lifecycle, tracking, and execution
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """Represents a trading order"""
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_amount: float = 0.0
    remaining_amount: float = 0.0
    average_price: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    exchange: str = "unknown"
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    fees: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.remaining_amount == 0.0:
            self.remaining_amount = self.amount


@dataclass
class Fill:
    """Represents a trade fill"""
    id: str
    order_id: str
    symbol: str
    side: OrderSide
    amount: float
    price: float
    fee: float
    fee_currency: str
    timestamp: datetime
    exchange: str
    exchange_trade_id: Optional[str] = None


class OrderManager:
    """Manages order lifecycle and execution"""
    
    def __init__(self, exchange_manager, risk_manager=None):
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.logger = logging.getLogger("order_manager")
        
        # Order storage
        self.orders: Dict[str, Order] = {}
        self.fills: Dict[str, Fill] = {}
        self.order_history: List[Order] = []
        
        # Callbacks
        self.on_order_update: Optional[Callable[[Order], None]] = None
        self.on_fill: Optional[Callable[[Fill], None]] = None
        
        # Order tracking
        self._next_order_id = 1
        self._tracking_tasks: Dict[str, asyncio.Task] = {}
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        order_id = f"ord_{int(time.time() * 1000)}_{self._next_order_id}"
        self._next_order_id += 1
        return order_id
    
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        exchange: str = "binance",
        client_order_id: Optional[str] = None,
        live: bool = False,
        **kwargs
    ) -> Order:
        """Create and place a new order"""
        
        # Risk check
        if self.risk_manager:
            risk_check = await self.risk_manager.check_order_risk(
                symbol, side, amount, price, order_type
            )
            if not risk_check.allowed:
                order = Order(
                    id=self._generate_order_id(),
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    amount=amount,
                    price=price,
                    stop_price=stop_price,
                    status=OrderStatus.REJECTED,
                    exchange=exchange,
                    client_order_id=client_order_id,
                    metadata={"rejection_reason": risk_check.reason}
                )
                self.orders[order.id] = order
                self.order_history.append(order)
                return order
        
        # Create order object
        order = Order(
            id=self._generate_order_id(),
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            stop_price=stop_price,
            exchange=exchange,
            client_order_id=client_order_id,
            metadata=kwargs
        )
        
        # Place order on exchange
        try:
            if live:
                result = await self.exchange_manager.create_order(
                    symbol=symbol,
                    order_type=order_type.value,
                    side=side.value,
                    amount=amount,
                    price=price,
                    exchange_name=exchange,
                    live=True
                )
                
                if result.get("ok"):
                    order.exchange_order_id = result["order"].get("id")
                    order.status = OrderStatus.OPEN
                else:
                    order.status = OrderStatus.REJECTED
                    order.metadata["rejection_reason"] = result.get("error", "Unknown error")
            else:
                # Paper trading
                order.status = OrderStatus.OPEN
                order.exchange_order_id = f"paper_{order.id}"
                order.metadata["simulated"] = True
        
        except Exception as e:
            self.logger.error(f"Failed to place order {order.id}: {e}")
            order.status = OrderStatus.REJECTED
            order.metadata["rejection_reason"] = str(e)
        
        # Store order
        self.orders[order.id] = order
        self.order_history.append(order)
        
        # Start tracking if live order
        if live and order.status == OrderStatus.OPEN:
            self._tracking_tasks[order.id] = asyncio.create_task(
                self._track_order(order.id)
            )
        
        # Notify callback
        if self.on_order_update:
            self.on_order_update(order)
        
        return order
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if order_id not in self.orders:
            return False
        
        order = self.orders[order_id]
        
        if order.status not in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            return False
        
        try:
            if order.metadata.get("simulated"):
                # Paper trading
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now(timezone.utc)
            else:
                # Live trading - cancel on exchange
                if order.exchange_order_id:
                    # This would need to be implemented in exchange_manager
                    # await self.exchange_manager.cancel_order(order.exchange_order_id, order.exchange)
                    pass
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now(timezone.utc)
            
            # Stop tracking
            if order_id in self._tracking_tasks:
                self._tracking_tasks[order_id].cancel()
                del self._tracking_tasks[order_id]
            
            # Notify callback
            if self.on_order_update:
                self.on_order_update(order)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def _track_order(self, order_id: str):
        """Track order status and fills"""
        order = self.orders.get(order_id)
        if not order:
            return
        
        try:
            while order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                # Fetch order status from exchange
                if order.exchange_order_id:
                    # This would need to be implemented in exchange_manager
                    # status = await self.exchange_manager.fetch_order_status(order.exchange_order_id, order.exchange)
                    # if status:
                    #     await self._update_order_from_exchange(order, status)
                    pass
                
                # Check for fills
                await self._check_fills(order)
                
                # Wait before next check
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error tracking order {order_id}: {e}")
        finally:
            if order_id in self._tracking_tasks:
                del self._tracking_tasks[order_id]
    
    async def _check_fills(self, order: Order):
        """Check for new fills for an order"""
        try:
            # Fetch recent trades for the symbol
            trades = await self.exchange_manager.fetch_trades(
                order.symbol, order.exchange, limit=100
            )
            
            for trade in trades:
                if trade.get("order") == order.exchange_order_id:
                    fill_id = f"fill_{trade['id']}"
                    if fill_id not in self.fills:
                        fill = Fill(
                            id=fill_id,
                            order_id=order.id,
                            symbol=order.symbol,
                            side=OrderSide(trade["side"]),
                            amount=float(trade["amount"]),
                            price=float(trade["price"]),
                            fee=float(trade.get("fee", {}).get("cost", 0)),
                            fee_currency=trade.get("fee", {}).get("currency", "USDT"),
                            timestamp=datetime.fromtimestamp(trade["timestamp"] / 1000, timezone.utc),
                            exchange=order.exchange,
                            exchange_trade_id=trade["id"]
                        )
                        
                        self.fills[fill_id] = fill
                        await self._process_fill(fill)
                        
        except Exception as e:
            self.logger.error(f"Error checking fills for order {order.id}: {e}")
    
    async def _process_fill(self, fill: Fill):
        """Process a new fill"""
        order = self.orders.get(fill.order_id)
        if not order:
            return
        
        # Update order
        order.filled_amount += fill.amount
        order.remaining_amount = order.amount - order.filled_amount
        
        # Calculate average price
        if order.filled_amount > 0:
            total_cost = sum(f.price * f.amount for f in self.fills.values() if f.order_id == order.id)
            order.average_price = total_cost / order.filled_amount
        
        # Update status
        if order.remaining_amount <= 0:
            order.status = OrderStatus.FILLED
            # Stop tracking
            if order.id in self._tracking_tasks:
                self._tracking_tasks[order.id].cancel()
                del self._tracking_tasks[order.id]
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        
        order.updated_at = datetime.now(timezone.utc)
        
        # Notify callbacks
        if self.on_fill:
            self.on_fill(fill)
        if self.on_order_update:
            self.on_order_update(order)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders, optionally filtered by status"""
        orders = list(self.orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return sorted(orders, key=lambda x: x.created_at, reverse=True)
    
    def get_fills(self, order_id: Optional[str] = None) -> List[Fill]:
        """Get fills, optionally filtered by order ID"""
        fills = list(self.fills.values())
        if order_id:
            fills = [f for f in fills if f.order_id == order_id]
        return sorted(fills, key=lambda x: x.timestamp, reverse=True)
    
    def get_open_orders(self) -> List[Order]:
        """Get all open orders"""
        return self.get_orders(OrderStatus.OPEN)
    
    def get_position(self, symbol: str) -> Dict[str, float]:
        """Calculate net position for a symbol"""
        position = {"amount": 0.0, "cost": 0.0, "fees": 0.0}
        
        for fill in self.fills.values():
            if fill.symbol == symbol:
                if fill.side == OrderSide.BUY:
                    position["amount"] += fill.amount
                    position["cost"] += fill.amount * fill.price
                else:
                    position["amount"] -= fill.amount
                    position["cost"] -= fill.amount * fill.price
                
                position["fees"] += fill.fee
        
        return position
    
    async def close_all_orders(self):
        """Cancel all open orders"""
        open_orders = self.get_open_orders()
        tasks = [self.cancel_order(order.id) for order in open_orders]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get order manager statistics"""
        total_orders = len(self.order_history)
        filled_orders = len([o for o in self.order_history if o.status == OrderStatus.FILLED])
        cancelled_orders = len([o for o in self.order_history if o.status == OrderStatus.CANCELLED])
        rejected_orders = len([o for o in self.order_history if o.status == OrderStatus.REJECTED])
        
        total_fills = len(self.fills)
        total_volume = sum(f.amount * f.price for f in self.fills.values())
        total_fees = sum(f.fee for f in self.fills.values())
        
        return {
            "total_orders": total_orders,
            "filled_orders": filled_orders,
            "cancelled_orders": cancelled_orders,
            "rejected_orders": rejected_orders,
            "fill_rate": filled_orders / total_orders if total_orders > 0 else 0,
            "total_fills": total_fills,
            "total_volume": total_volume,
            "total_fees": total_fees,
            "open_orders": len(self.get_open_orders())
        }