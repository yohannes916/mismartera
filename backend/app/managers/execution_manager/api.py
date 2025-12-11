"""
ExecutionManager Public API

Handles all order execution and account management.
All CLI and API routes must use this interface.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.managers.execution_manager.integrations.base import (
    OrderSide, OrderType, OrderStatus, TimeInForce, BrokerageInterface
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
    
    def __init__(self, system_manager: object, brokerage: str = "alpaca"):
        """
        Initialize ExecutionManager
        
        Args:
            system_manager: Reference to SystemManager (single source of truth for mode)
            brokerage: Brokerage to use - "alpaca", "schwab", etc.
        """
        self.system_manager = system_manager
        self.brokerage_name = brokerage
        self._brokerage: Optional[BrokerageInterface] = None  # Lazy-loaded
        logger.info(f"ExecutionManager initialized with {brokerage}")
    
    def _get_brokerage(self) -> BrokerageInterface:
        """Lazy-load and return brokerage client."""
        if self._brokerage is None:
            if self.brokerage_name == "alpaca":
                from app.managers.execution_manager.integrations.alpaca_trading import AlpacaTradingClient
                self._brokerage = AlpacaTradingClient()
            elif self.brokerage_name == "schwab":
                from app.managers.execution_manager.integrations.schwab_trading import SchwabTradingClient
                self._brokerage = SchwabTradingClient()
            elif self.brokerage_name == "mismartera":
                from app.managers.execution_manager.integrations.mismartera_trading import MismarteraTradingClient
                self._brokerage = MismarteraTradingClient()
            else:
                raise ValueError(f"Unknown brokerage: {self.brokerage_name}")
            logger.info(f"Loaded {self.brokerage_name} brokerage client")
        return self._brokerage
    
    def set_brokerage(self, brokerage: str) -> None:
        """
        Switch the active brokerage provider.
        
        Args:
            brokerage: Brokerage name ("alpaca", "schwab", or "mismartera")
            
        Raises:
            ValueError: If brokerage is not supported
        """
        brokerage = brokerage.lower()
        
        if brokerage not in ["alpaca", "schwab", "mismartera"]:
            raise ValueError(f"Unknown brokerage: {brokerage}. Supported: alpaca, schwab, mismartera")
        
        self.brokerage_name = brokerage
        self._brokerage = None  # Reset to force reload with new provider
        logger.info(f"Switched execution manager to {brokerage} brokerage")
    
    def get_current_brokerage(self) -> str:
        """
        Get the currently active brokerage provider.
        
        Returns:
            Name of the current brokerage
        """
        return self.brokerage_name
    
    @property
    def mode(self) -> str:
        """Get operation mode from SystemManager (single source of truth).
        
        Returns:
            'live' or 'backtest'
        """
        return self.system_manager.mode.value
    
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
        
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
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
            created_at=current_time
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
            order.filled_at = current_time
            await session.commit()
        
        # In live mode, submit to brokerage
        elif self.mode == "live":
            try:
                broker = self._get_brokerage()
                
                # Convert to enums
                order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
                order_type_enum = OrderType[order_type]
                tif_enum = TimeInForce[time_in_force]
                
                # Submit to broker
                broker_response = await broker.place_order(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=quantity,
                    side=order_side,
                    order_type=order_type_enum,
                    price=price,
                    time_in_force=tif_enum
                )
                
                # Update order with broker details
                order.broker_order_id = broker_response.get("order_id")
                order.status = broker_response.get("status", "WORKING")
                order.submitted_at = current_time
                await session.commit()
                
                logger.info(f"Order submitted to broker: {order.broker_order_id}")
                
            except Exception as e:
                logger.error(f"Failed to submit order to broker: {e}")
                order.status = "REJECTED"
                order.error_message = str(e)
                await session.commit()
                raise
        
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
        
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
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
        order.cancelled_at = current_time
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
        account_id: str = "default",
        sync_from_broker: bool = True
    ) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Args:
            session: Database session
            account_id: Account identifier
            sync_from_broker: If True and in live mode, sync from broker first
            
        Returns:
            Balance information dictionary
        """
        from app.models.account import Account
        from sqlalchemy import select
        
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
        # Sync from broker if in live mode
        if self.mode == "live" and sync_from_broker:
            try:
                broker = self._get_brokerage()
                broker_balance = await broker.get_account_balance(account_id)
                
                # Update or create account in DB
                result = await session.execute(
                    select(Account).where(Account.account_id == account_id)
                )
                account = result.scalar_one_or_none()
                
                if not account:
                    account = Account(
                        account_id=account_id,
                        brokerage=self.brokerage_name,
                        mode=self.mode
                    )
                    session.add(account)
                
                # Update with broker data
                account.brokerage = self.brokerage_name  # Update brokerage in case it changed
                account.cash_balance = broker_balance.get("cash", 0)
                account.buying_power = broker_balance.get("buying_power", 0)
                account.total_value = broker_balance.get("portfolio_value", 0)
                account.updated_at = current_time
                
                await session.commit()
                await session.refresh(account)
                
                logger.info(f"Synced balance from {self.brokerage_name}")
                
            except Exception as e:
                logger.error(f"Failed to sync balance from broker: {e}")
                # Fall through to return DB data
        
        # Return from DB
        result = await session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            # Create default account for backtest mode
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
        else:
            # Update brokerage and mode in DB to match current settings (for record keeping)
            if account.brokerage != self.brokerage_name or account.mode != self.mode:
                account.brokerage = self.brokerage_name
                account.mode = self.mode
                account.updated_at = current_time
                await session.commit()
                await session.refresh(account)
        
        return {
            "account_id": account.account_id,
            "cash_balance": account.cash_balance,
            "buying_power": account.buying_power,
            "total_value": account.total_value,
            "brokerage": self.brokerage_name,  # Use current brokerage, not DB value
            "mode": self.mode  # Use current mode, not DB value
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
    
    async def get_positions(
        self,
        session: AsyncSession,
        account_id: str = "default",
        sync_from_broker: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Args:
            session: Database session
            account_id: Account identifier
            sync_from_broker: If True and in live mode, sync from broker first
            
        Returns:
            List of position dictionaries
        """
        from app.models.account import Position
        from sqlalchemy import select
        
        # Get current time from TimeManager
        time_mgr = self.system_manager.get_time_manager()
        current_time = time_mgr.get_current_time()
        
        # Sync from broker if in live mode
        if self.mode == "live" and sync_from_broker:
            try:
                broker = self._get_brokerage()
                broker_positions = await broker.get_positions(account_id)
                
                # Clear existing positions for this account
                await session.execute(
                    select(Position).where(Position.account_id == account_id)
                )
                existing_positions = (await session.execute(
                    select(Position).where(
                        Position.account_id == account_id,
                        Position.closed_at.is_(None)
                    )
                )).scalars().all()
                
                # Mark all as closed first
                for pos in existing_positions:
                    pos.closed_at = current_time
                
                # Add/update positions from broker
                for broker_pos in broker_positions:
                    # Find existing position or create new
                    result = await session.execute(
                        select(Position).where(
                            Position.account_id == account_id,
                            Position.symbol == broker_pos["symbol"],
                            Position.closed_at.is_(None)
                        )
                    )
                    position = result.scalar_one_or_none()
                    
                    if not position:
                        position = Position(
                            account_id=account_id,
                            symbol=broker_pos["symbol"],
                            opened_at=current_time
                        )
                        session.add(position)
                    
                    # Update position data
                    position.quantity = broker_pos["quantity"]
                    position.avg_entry_price = broker_pos["avg_entry_price"]
                    position.current_price = broker_pos["current_price"]
                    position.market_value = broker_pos["market_value"]
                    position.unrealized_pnl = broker_pos["unrealized_pnl"]
                    position.updated_at = current_time
                    position.closed_at = None  # Reopen if was marked closed
                
                await session.commit()
                logger.info(f"Synced {len(broker_positions)} positions from {self.brokerage_name}")
                
            except Exception as e:
                logger.error(f"Failed to sync positions from broker: {e}")
                # Fall through to return DB data
        
        # Return from DB (open positions only)
        result = await session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.closed_at.is_(None)
            )
        )
        positions = result.scalars().all()
        
        return [
            {
                "symbol": pos.symbol,
                "quantity": pos.quantity,
                "avg_entry_price": pos.avg_entry_price,
                "current_price": pos.current_price,
                "market_value": pos.market_value,
                "unrealized_pnl": pos.unrealized_pnl,
                "realized_pnl": pos.realized_pnl,
                "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                "updated_at": pos.updated_at.isoformat() if pos.updated_at else None,
            }
            for pos in positions
        ]
    
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
        # TODO: Implement P&L calculation from closed positions and order history
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
