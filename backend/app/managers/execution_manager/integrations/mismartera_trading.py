"""
Mismartera Simulated Trading Client

Internal backtesting brokerage with full order execution simulation.
Uses session_data for pricing and database for state persistence.
"""
from datetime import date, datetime
from typing import List, Dict, Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.managers.execution_manager.integrations.base import (
    BrokerageInterface,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce
)
from app.models.account import Account, Position
from app.models.orders import Order, OrderExecution
from app.logger import logger
from app.config import settings


class MismarteraTradingClient(BrokerageInterface):
    """
    Simulated trading client for backtesting.
    
    Features:
    - Database-backed account balance and positions
    - Configurable buying power multiplier
    - Order execution using session_data pricing
    - Configurable execution costs (fees, commission, slippage)
    - Full order lifecycle management (PENDING → WORKING → FILLED)
    """
    
    @property
    def brokerage_name(self) -> str:
        return "mismartera"
    
    async def authenticate(self) -> bool:
        """
        Always returns True - no external authentication needed.
        """
        return True
    
    async def validate_connection(self) -> bool:
        """
        Always returns True - internal brokerage.
        """
        return True
    
    async def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balance from database.
        
        Returns:
            {
                "cash": float,
                "buying_power": float,
                "portfolio_value": float
            }
        """
        from app.models.database import SessionLocal
        
        with SessionLocal() as session:
            result = await session.execute(
                select(Account).where(Account.account_id == account_id)
            )
            account = result.scalar_one_or_none()
            
            if not account:
                # Create default account
                buying_power_multiplier = getattr(
                    settings, 'MISMARTERA_BUYING_POWER_MULTIPLIER', 1.0
                )
                initial_cash = getattr(settings, 'MISMARTERA_INITIAL_BALANCE', 100000.0)
                
                account = Account(
                    account_id=account_id,
                    brokerage="mismartera",
                    mode="backtest",
                    cash_balance=initial_cash,
                    buying_power=initial_cash * buying_power_multiplier,
                    total_value=initial_cash
                )
                session.add(account)
                await session.commit()
                await session.refresh(account)
            
            # Calculate total value (cash + positions)
            positions_result = await session.execute(
                select(Position).where(
                    Position.account_id == account_id,
                    Position.closed_at.is_(None)
                )
            )
            positions = positions_result.scalars().all()
            
            positions_value = sum(
                (pos.market_value or 0) for pos in positions
            )
            total_value = account.cash_balance + positions_value
            
            return {
                "cash": account.cash_balance,
                "buying_power": account.buying_power,
                "portfolio_value": total_value
            }
    
    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get current positions from database.
        Updates position prices from session_data if available.
        """
        from app.models.database import SessionLocal
        
        with SessionLocal() as session:
            result = await session.execute(
                select(Position).where(
                    Position.account_id == account_id,
                    Position.closed_at.is_(None)
                )
            )
            positions = result.scalars().all()
            
            # Try to update prices from session_data
            try:
                from app.managers.system_manager import get_system_manager
                system_mgr = get_system_manager()
                data_mgr = system_mgr.get_data_manager()
                
                for pos in positions:
                    try:
                        # Get latest bar for current price
                        latest_bar = await data_mgr.get_latest_bar(
                            session, pos.symbol, interval="1m"
                        )
                        if latest_bar:
                            pos.current_price = latest_bar.close
                            pos.market_value = pos.current_price * abs(pos.quantity)
                            pos.unrealized_pnl = (
                                pos.current_price - pos.avg_entry_price
                            ) * pos.quantity
                            # Get current time from TimeManager
                            time_mgr = self.system_manager.get_time_manager()
                            pos.updated_at = time_mgr.get_current_time()
                    except Exception as e:
                        logger.warning(
                            f"Could not update price for {pos.symbol}: {e}"
                        )
                
                await session.commit()
            except Exception as e:
                logger.warning(f"Could not update positions from session_data: {e}")
            
            return [
                {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_entry_price": pos.avg_entry_price,
                    "current_price": pos.current_price or pos.avg_entry_price,
                    "market_value": pos.market_value or 0,
                    "unrealized_pnl": pos.unrealized_pnl or 0
                }
                for pos in positions
            ]
    
    async def get_orders(
        self,
        account_id: str,
        status: Optional[OrderStatus] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get order history from database.
        """
        from app.models.database import SessionLocal
        from datetime import datetime as dt
        
        with SessionLocal() as session:
            conditions = [Order.account_id == account_id]
            
            if start_date:
                conditions.append(Order.created_at >= dt.combine(start_date, dt.min.time()))
            if end_date:
                conditions.append(Order.created_at <= dt.combine(end_date, dt.max.time()))
            if status:
                conditions.append(Order.status == status.value)
            
            result = await session.execute(
                select(Order).where(and_(*conditions)).order_by(Order.created_at.desc())
            )
            orders = result.scalars().all()
            
            return [
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "quantity": order.quantity,
                    "side": order.side,
                    "order_type": order.order_type,
                    "price": order.price,
                    "status": order.status,
                    "filled_quantity": order.filled_quantity,
                    "avg_fill_price": order.avg_fill_price,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "filled_at": order.filled_at.isoformat() if order.filled_at else None
                }
                for order in orders
            ]
    
    async def place_order(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY
    ) -> Dict[str, Any]:
        """
        Place order and immediately execute it using current session_data pricing.
        
        Process:
        1. Validate account has sufficient funds
        2. Get current price from session_data
        3. Calculate execution price (with slippage for market orders)
        4. Calculate execution cost (fees)
        5. Create order record
        6. Execute order (update positions and balance)
        7. Return confirmation
        """
        from app.models.database import SessionLocal
        
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
        with SessionLocal() as session:
            # Get account
            account_result = await session.execute(
                select(Account).where(Account.account_id == account_id)
            )
            account = account_result.scalar_one_or_none()
            
            if not account:
                raise ValueError(f"Account {account_id} not found")
            
            # Get current price from session_data
            execution_price = await self._get_execution_price(
                session, symbol, order_type, price, side
            )
            
            if execution_price is None:
                raise ValueError(
                    f"Cannot determine execution price for {symbol}. "
                    "No market data available."
                )
            
            # Calculate order value and costs
            order_value = execution_price * quantity
            execution_cost_pct = getattr(
                settings, 'MISMARTERA_EXECUTION_COST_PCT', 0.001
            )  # Default 0.1%
            execution_cost = order_value * execution_cost_pct
            total_cost = order_value + execution_cost
            
            # Validate funds for buy orders
            if side == OrderSide.BUY:
                if total_cost > account.buying_power:
                    raise ValueError(
                        f"Insufficient buying power. Required: ${total_cost:.2f}, "
                        f"Available: ${account.buying_power:.2f}"
                    )
            
            # Validate position for sell orders
            if side == OrderSide.SELL:
                position_result = await session.execute(
                    select(Position).where(
                        Position.account_id == account_id,
                        Position.symbol == symbol,
                        Position.closed_at.is_(None)
                    )
                )
                position = position_result.scalar_one_or_none()
                
                if not position or position.quantity < quantity:
                    current_qty = position.quantity if position else 0
                    raise ValueError(
                        f"Insufficient shares to sell. Required: {quantity}, "
                        f"Available: {current_qty}"
                    )
            
            # Create order record
            order_id = f"MSM_{uuid.uuid4().hex[:12].upper()}"
            order = Order(
                order_id=order_id,
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                side=side.value,
                order_type=order_type.value,
                price=price,
                time_in_force=time_in_force.value,
                status=OrderStatus.FILLED.value,
                filled_quantity=quantity,
                avg_fill_price=execution_price,
                mode="backtest",
                brokerage="mismartera",
                created_at=current_time,
                submitted_at=current_time,
                filled_at=current_time
            )
            session.add(order)
            
            # Create order execution record
            execution = OrderExecution(
                order_id=order_id,
                executed_quantity=quantity,
                execution_price=execution_price,
                execution_fee=execution_cost,
                executed_at=current_time
            )
            session.add(execution)
            
            # Update account balance
            if side == OrderSide.BUY:
                account.cash_balance -= total_cost
                account.buying_power -= total_cost
            else:  # SELL
                account.cash_balance += (order_value - execution_cost)
                account.buying_power += (order_value - execution_cost)
            
            account.updated_at = current_time
            
            # Update or create position
            await self._update_position(
                session, account_id, symbol, quantity, execution_price, side
            )
            
            await session.commit()
            
            logger.info(
                f"Mismartera executed {side.value} order: {quantity} {symbol} "
                f"@ ${execution_price:.2f} (cost: ${execution_cost:.2f})"
            )
            
            return {
                "order_id": order_id,
                "status": OrderStatus.FILLED.value,
                "filled_quantity": quantity,
                "avg_fill_price": execution_price,
                "execution_cost": execution_cost
            }
    
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel order (only if not yet filled).
        For Mismartera, orders are immediately filled, so this will fail for filled orders.
        """
        from app.models.database import SessionLocal
        
        with SessionLocal() as session:
            result = await session.execute(
                select(Order).where(
                    Order.order_id == order_id,
                    Order.account_id == account_id
                )
            )
            order = result.scalar_one_or_none()
            
            if not order:
                raise ValueError(f"Order {order_id} not found")
            
            if order.status == OrderStatus.FILLED.value:
                raise ValueError(f"Cannot cancel filled order {order_id}")
            
            if order.status == OrderStatus.CANCELLED.value:
                raise ValueError(f"Order {order_id} already cancelled")
            
            # Get current time from TimeManager
            time_mgr = self.system_manager.get_time_manager()
            current_time = time_mgr.get_current_time()
            
            order.status = OrderStatus.CANCELLED.value
            order.cancelled_at = current_time
            await session.commit()
            
            return {
                "order_id": order_id,
                "status": OrderStatus.CANCELLED.value
            }
    
    async def modify_order(
        self,
        account_id: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modify order (only if not yet filled).
        For Mismartera, orders are immediately filled, so this is not supported.
        """
        raise NotImplementedError(
            "Mismartera executes orders immediately. Cannot modify filled orders."
        )
    
    async def _get_execution_price(
        self,
        session: AsyncSession,
        symbol: str,
        order_type: OrderType,
        limit_price: Optional[float],
        side: OrderSide
    ) -> Optional[float]:
        """
        Get execution price from session_data.
        
        For MARKET orders: Uses current bar close + slippage
        For LIMIT orders: Uses limit price (if market allows)
        """
        try:
            from app.managers.system_manager import get_system_manager
            system_mgr = get_system_manager()
            data_mgr = system_mgr.get_data_manager()
            
            # Get latest bar
            latest_bar = await data_mgr.get_latest_bar(session, symbol, interval="1m")
            
            if not latest_bar:
                logger.warning(f"No market data available for {symbol}")
                return None
            
            market_price = latest_bar.close
            
            if order_type == OrderType.MARKET:
                # Apply slippage for market orders
                slippage_pct = getattr(settings, 'MISMARTERA_SLIPPAGE_PCT', 0.0001)  # 0.01%
                
                if side == OrderSide.BUY:
                    execution_price = market_price * (1 + slippage_pct)
                else:  # SELL
                    execution_price = market_price * (1 - slippage_pct)
                
                return execution_price
            
            elif order_type == OrderType.LIMIT:
                if limit_price is None:
                    raise ValueError("Limit price required for LIMIT orders")
                
                # Check if limit order would be filled
                if side == OrderSide.BUY and market_price <= limit_price:
                    return market_price  # Filled at market price
                elif side == OrderSide.SELL and market_price >= limit_price:
                    return market_price  # Filled at market price
                else:
                    raise ValueError(
                        f"Limit order cannot be filled. Market: ${market_price:.2f}, "
                        f"Limit: ${limit_price:.2f}"
                    )
            
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
        
        except Exception as e:
            logger.error(f"Error getting execution price for {symbol}: {e}")
            return None
    
    async def _update_position(
        self,
        session: AsyncSession,
        account_id: str,
        symbol: str,
        quantity: float,
        price: float,
        side: OrderSide
    ):
        """
        Update or create position after order execution.
        """
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
        result = await session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol == symbol,
                Position.closed_at.is_(None)
            )
        )
        position = result.scalar_one_or_none()
        
        if side == OrderSide.BUY:
            if position:
                # Update existing position (average in)
                total_cost = (position.avg_entry_price * position.quantity) + (price * quantity)
                new_quantity = position.quantity + quantity
                position.avg_entry_price = total_cost / new_quantity
                position.quantity = new_quantity
                position.market_value = position.current_price * new_quantity if position.current_price else None
                position.updated_at = current_time
            else:
                # Create new position
                position = Position(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=quantity,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=price * quantity,
                    unrealized_pnl=0,
                    opened_at=current_time
                )
                session.add(position)
        
        else:  # SELL
            if position:
                # Calculate realized P&L
                realized_pnl = (price - position.avg_entry_price) * quantity
                
                if position.quantity == quantity:
                    # Close position
                    position.closed_at = current_time
                    position.realized_pnl = (position.realized_pnl or 0) + realized_pnl
                    position.quantity = 0
                else:
                    # Reduce position
                    position.quantity -= quantity
                    position.realized_pnl = (position.realized_pnl or 0) + realized_pnl
                    position.market_value = position.current_price * position.quantity if position.current_price else None
                
                position.updated_at = current_time
                
                logger.info(f"Position {symbol}: Realized P&L = ${realized_pnl:.2f}")
