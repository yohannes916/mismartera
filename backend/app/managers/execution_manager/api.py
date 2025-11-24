"""
ExecutionManager Public API

Handles all order execution and account management.
All CLI and API routes must use this interface.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.managers.execution_manager.integrations.base import (
    OrderSide, OrderType, OrderStatus, TimeInForce
)
from app.logger import logger


class ExecutionManager:
    """
    📈 ExecutionManager - All order execution and account management
    
    Provides:
    - Order placement (buy/sell, limit/market)
    - Order management (cancel, modify)
    - Open orders information
    - Order history
    - Account balance and trading power
    - Profit & Loss reporting
    
    Supports both Real and Backtest modes.
    """
    
    def __init__(self, mode: str = "live", brokerage: str = "schwab"):
        """
        Initialize ExecutionManager
        
        Args:
            mode: Operating mode - "live" or "backtest"
            brokerage: Brokerage to use - "schwab", "paper", etc.
        """
        self.mode = mode
        self.brokerage_name = brokerage
        self.brokerage = None  # Will be initialized on first use
        logger.info(f"ExecutionManager initialized in {mode} mode with {brokerage}")
    
    # ==================== ORDER PLACEMENT ====================
    
    async def place_order(
        self,
        session: AsyncSession,
        account_id: str,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        time_in_force: str = "DAY"
    ) -> Dict[str, Any]:
        """
        Place a new order.
        All orders expire at End-of-Day (DAY).
        
        Args:
            session: Database session
            account_id: Account identifier
            symbol: Stock symbol
            quantity: Number of shares
            side: "BUY" or "SELL"
            order_type: "MARKET", "LIMIT", "STOP", "STOP_LIMIT"
            price: Limit price (required for LIMIT orders)
            time_in_force: "DAY" (default), "GTC", "IOC", "FOK"
            
        Returns:
            Order result dictionary
        """
        from app.models.orders import Order
        import uuid
        
        # Validate inputs
        if side not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}")
        
        if order_type not in ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]:
            raise ValueError(f"Invalid order type: {order_type}")
        
        if order_type == "LIMIT" and price is None:
            raise ValueError("Price required for LIMIT orders")
        
        # Create order record
        order_id = f"ORD_{uuid.uuid4().hex[:12].upper()}"
        
        order = Order(
            order_id=order_id,
            account_id=account_id,
            symbol=symbol.upper(),
            quantity=quantity,
            side=side,
            order_type=order_type,
            price=price,
            time_in_force=time_in_force,
            status="PENDING",
            mode=self.mode,
            brokerage=self.brokerage_name,
            created_at=datetime.utcnow()
        )
        
        session.add(order)
        await session.commit()
        await session.refresh(order)
        
        logger.info(f"Order placed: {order_id} {side} {quantity} {symbol} @ {order_type}")
        
        # In backtest mode, handle order immediately
        if self.mode == "backtest":
            # TODO: Implement backtest order simulation
            order.status = "FILLED"
            order.filled_quantity = quantity
            order.avg_fill_price = price or 0.0
            order.filled_at = datetime.utcnow()
            await session.commit()
        
        # In live mode, submit to brokerage
        elif self.mode == "live":
            # TODO: Submit to actual brokerage
            logger.warning("Real mode order execution not yet implemented")
            order.status = "PENDING"
            await session.commit()
        
        return {
            "order_id": order.order_id,
            "status": order.status,
            "symbol": order.symbol,
            "quantity": order.quantity,
            "side": order.side,
            "order_type": order.order_type,
            "created_at": order.created_at.isoformat()
        }
    
    # ==================== ORDER MANAGEMENT ====================
    
    async def cancel_order(
        self,
        session: AsyncSession,
        order_id: str
    ) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            session: Database session
            order_id: Order ID to cancel
            
        Returns:
            Cancellation result dictionary
        """
        from app.models.orders import Order
        from sqlalchemy import select
        
        # Find order
        result = await session.execute(
            select(Order).where(Order.order_id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        
        if order.status in ["FILLED", "CANCELLED"]:
            raise ValueError(f"Cannot cancel order in {order.status} status")
        
        # Cancel order
        order.status = "CANCELLED"
        order.cancelled_at = datetime.utcnow()
        await session.commit()
        
        logger.info(f"Order cancelled: {order_id}")
        
        return {
            "order_id": order.order_id,
            "status": order.status,
            "cancelled_at": order.cancelled_at.isoformat()
        }
    
    async def modify_order(
        self,
        session: AsyncSession,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing order.
        
        Args:
            session: Database session
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            
        Returns:
            Modification result dictionary
        """
        from app.models.orders import Order
        from sqlalchemy import select
        
        # Find order
        result = await session.execute(
            select(Order).where(Order.order_id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        
        if order.status not in ["PENDING", "WORKING"]:
            raise ValueError(f"Cannot modify order in {order.status} status")
        
        # Modify order
        if quantity is not None:
            order.quantity = quantity
            order.remaining_quantity = quantity - order.filled_quantity
        
        if price is not None:
            order.price = price
        
        await session.commit()
        
        logger.info(f"Order modified: {order_id}")
        
        return {
            "order_id": order.order_id,
            "status": order.status,
            "quantity": order.quantity,
            "price": order.price
        }
    
    # ==================== ORDER INFORMATION ====================
    
    async def get_open_orders(
        self,
        session: AsyncSession,
        account_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Get all open orders (pending, working, partial-filled).
        
        Args:
            session: Database session
            account_id: Account identifier
            
        Returns:
            List of order dictionaries
        """
        from app.models.orders import Order
        from sqlalchemy import select
        
        result = await session.execute(
            select(Order).where(
                Order.account_id == account_id,
                Order.status.in_(["PENDING", "WORKING", "PARTIAL_FILLED"])
            ).order_by(Order.created_at.desc())
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
                "created_at": order.created_at.isoformat()
            }
            for order in orders
        ]
    
    async def get_order_history(
        self,
        session: AsyncSession,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get order history for a date range.
        
        Args:
            session: Database session
            account_id: Account identifier
            start_date: Start date (optional)
            end_date: End date (optional)
            status: Filter by status (optional)
            
        Returns:
            List of order dictionaries
        """
        from app.models.orders import Order
        from sqlalchemy import select, and_
        from datetime import datetime as dt
        
        conditions = [Order.account_id == account_id]
        
        if start_date:
            conditions.append(Order.created_at >= dt.combine(start_date, dt.min.time()))
        if end_date:
            conditions.append(Order.created_at <= dt.combine(end_date, dt.max.time()))
        if status:
            conditions.append(Order.status == status)
        
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
                "created_at": order.created_at.isoformat(),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None
            }
            for order in orders
        ]
    
    # ==================== ACCOUNT INFORMATION ====================
    
    async def get_balance(
        self,
        session: AsyncSession,
        account_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Args:
            session: Database session
            account_id: Account identifier
            
        Returns:
            Balance information dictionary
        """
        from app.models.account import Account
        from sqlalchemy import select
        
        result = await session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            # Create default account if it doesn't exist
            account = Account(
                account_id=account_id,
                brokerage=self.brokerage_name,
                mode=self.mode,
                cash_balance=100000.0,  # Default starting balance
                buying_power=100000.0,
                total_value=100000.0
            )
            session.add(account)
            await session.commit()
            await session.refresh(account)
        
        return {
            "account_id": account.account_id,
            "cash_balance": account.cash_balance,
            "buying_power": account.buying_power,
            "total_value": account.total_value,
            "brokerage": account.brokerage,
            "mode": account.mode
        }
    
    async def get_trading_power(
        self,
        session: AsyncSession,
        account_id: str = "default"
    ) -> float:
        """
        Get available trading power.
        
        Args:
            session: Database session
            account_id: Account identifier
            
        Returns:
            Available trading power
        """
        balance = await self.get_balance(session, account_id)
        return balance["buying_power"]
    
    async def get_pnl(
        self,
        session: AsyncSession,
        account_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get Profit & Loss report for a date range.
        
        Args:
            session: Database session
            account_id: Account identifier
            start_date: Start date
            end_date: End date
            
        Returns:
            P&L report dictionary
        """
        # TODO: Implement P&L calculation
        logger.warning("P&L calculation not yet implemented")
        
        return {
            "account_id": account_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_pnl": 0.0,
            "trades_count": 0
        }
