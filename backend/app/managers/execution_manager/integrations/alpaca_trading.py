"""
Alpaca Trading API Integration for ExecutionManager

Leverages existing AlpacaClient authentication from app/integrations/alpaca_client.py
API Documentation: https://docs.alpaca.markets/reference/
"""
import httpx
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from app.config import settings
from app.logger import logger
from app.managers.execution_manager.integrations.base import (
    BrokerageInterface,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce
)


class AlpacaTradingClient(BrokerageInterface):
    """
    Alpaca Trading API Client for order execution and account management.
    
    Uses API key authentication (simpler than OAuth).
    Supports both paper and live trading via ALPACA_PAPER_TRADING setting.
    """
    
    def __init__(self):
        # Use trading API base URL for orders/account
        self.base_url = settings.ALPACA.api_base_url.rstrip("/")
        self.api_key = settings.ALPACA.api_key_id
        self.api_secret = settings.ALPACA.api_secret_key
        self.paper_trading = settings.ALPACA.paper_trading
        
        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not configured")
    
    @property
    def brokerage_name(self) -> str:
        return "alpaca"
    
    def _headers(self) -> Dict[str, str]:
        """Build authentication headers for Alpaca API."""
        return {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.api_secret or "",
            "accept": "application/json",
            "content-type": "application/json"
        }
    
    async def authenticate(self) -> bool:
        """
        Validate Alpaca authentication.
        
        Returns:
            True if credentials are valid
        """
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca API credentials missing")
            return False
        
        # Test with account endpoint
        return await self.validate_connection()
    
    async def validate_connection(self) -> bool:
        """
        Validate Alpaca API connection.
        
        Returns:
            True if connection is valid
        """
        try:
            url = f"{self.base_url}/v2/account"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self._headers())
                
            if response.status_code == 200:
                logger.info("Alpaca connection validated")
                return True
            
            logger.error(f"Alpaca connection failed: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
            return False
    
    async def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Args:
            account_id: Account identifier (ignored for Alpaca, uses API key)
            
        Returns:
            Balance information dictionary with keys:
            - cash: Cash balance
            - buying_power: Available buying power
            - portfolio_value: Total portfolio value
            - equity: Account equity
        
        API: GET /v2/account
        """
        logger.info("Fetching Alpaca account balance")
        
        url = f"{self.base_url}/v2/account"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self._headers())
            
            if response.status_code != 200:
                logger.error(f"Failed to get account balance: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get account balance: {response.status_code}")
            
            data = response.json()
            
            # Normalize to our standard format
            return {
                "cash": float(data.get("cash", 0)),
                "buying_power": float(data.get("buying_power", 0)),
                "portfolio_value": float(data.get("portfolio_value", 0)),
                "equity": float(data.get("equity", 0)),
                "last_equity": float(data.get("last_equity", 0)),
                "account_number": data.get("account_number", ""),
                "status": data.get("status", ""),
                "pattern_day_trader": data.get("pattern_day_trader", False),
                "trading_blocked": data.get("trading_blocked", False),
                "transfers_blocked": data.get("transfers_blocked", False),
            }
    
    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Args:
            account_id: Account identifier (ignored for Alpaca)
            
        Returns:
            List of position dictionaries with keys:
            - symbol: Stock symbol
            - quantity: Number of shares
            - avg_entry_price: Average entry price
            - current_price: Current market price
            - market_value: Current market value
            - unrealized_pnl: Unrealized profit/loss
            - unrealized_pnl_percent: Unrealized P&L percentage
        
        API: GET /v2/positions
        """
        logger.info("Fetching Alpaca positions")
        
        url = f"{self.base_url}/v2/positions"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self._headers())
            
            if response.status_code != 200:
                logger.error(f"Failed to get positions: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get positions: {response.status_code}")
            
            positions = response.json()
            
            # Normalize to our standard format
            return [
                {
                    "symbol": pos.get("symbol", ""),
                    "quantity": float(pos.get("qty", 0)),
                    "avg_entry_price": float(pos.get("avg_entry_price", 0)),
                    "current_price": float(pos.get("current_price", 0)),
                    "market_value": float(pos.get("market_value", 0)),
                    "unrealized_pnl": float(pos.get("unrealized_pl", 0)),
                    "unrealized_pnl_percent": float(pos.get("unrealized_plpc", 0)) * 100,  # Convert to percentage
                    "side": pos.get("side", "long"),
                    "exchange": pos.get("exchange", ""),
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
        Get order history.
        
        Args:
            account_id: Account identifier (ignored for Alpaca)
            status: Filter by order status (open, closed, all)
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            List of order dictionaries
        
        API: GET /v2/orders
        """
        logger.info(f"Fetching Alpaca orders (status={status})")
        
        url = f"{self.base_url}/v2/orders"
        
        # Build query params
        params = {}
        
        # Status mapping
        if status:
            if status in [OrderStatus.PENDING, OrderStatus.WORKING]:
                params["status"] = "open"
            elif status == OrderStatus.FILLED:
                params["status"] = "closed"
            elif status == OrderStatus.CANCELLED:
                params["status"] = "closed"  # Alpaca groups all closed statuses
            else:
                params["status"] = "all"
        else:
            params["status"] = "all"
        
        # Date filters (ISO 8601 format)
        if start_date:
            params["after"] = start_date.isoformat()
        if end_date:
            # Add one day to include end_date orders
            from datetime import timedelta
            params["until"] = (end_date + timedelta(days=1)).isoformat()
        
        # Limit results
        params["limit"] = 500
        params["direction"] = "desc"  # Most recent first
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to get orders: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get orders: {response.status_code}")
            
            orders = response.json()
            
            # Normalize to our standard format
            return [
                {
                    "order_id": order.get("id", ""),
                    "client_order_id": order.get("client_order_id", ""),
                    "symbol": order.get("symbol", ""),
                    "quantity": float(order.get("qty", 0)),
                    "filled_quantity": float(order.get("filled_qty", 0)),
                    "side": order.get("side", "").upper(),  # buy/sell -> BUY/SELL
                    "order_type": order.get("type", "").upper(),  # market/limit -> MARKET/LIMIT
                    "time_in_force": order.get("time_in_force", "").upper(),
                    "limit_price": float(order.get("limit_price")) if order.get("limit_price") else None,
                    "stop_price": float(order.get("stop_price")) if order.get("stop_price") else None,
                    "status": order.get("status", "").upper(),
                    "created_at": order.get("created_at", ""),
                    "submitted_at": order.get("submitted_at", ""),
                    "filled_at": order.get("filled_at"),
                    "updated_at": order.get("updated_at", ""),
                    "filled_avg_price": float(order.get("filled_avg_price")) if order.get("filled_avg_price") else None,
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
        Place a new order.
        
        Args:
            account_id: Account identifier (ignored for Alpaca)
            symbol: Stock symbol
            quantity: Number of shares
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            price: Limit price (required for LIMIT orders)
            time_in_force: DAY, GTC, IOC, FOK
            
        Returns:
            Order confirmation dictionary
        
        API: POST /v2/orders
        """
        logger.info(f"Placing Alpaca order: {side.value} {quantity} {symbol} @ {order_type.value}")
        
        url = f"{self.base_url}/v2/orders"
        
        # Build order payload
        payload = {
            "symbol": symbol.upper(),
            "qty": quantity,
            "side": side.value.lower(),  # BUY -> buy, SELL -> sell
            "type": order_type.value.lower(),  # MARKET -> market, LIMIT -> limit
            "time_in_force": time_in_force.value.lower(),  # DAY -> day, GTC -> gtc
        }
        
        # Add limit price if LIMIT order
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit price required for LIMIT orders")
            payload["limit_price"] = price
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to place order: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to place order: {response.status_code} - {response.text}")
            
            order_data = response.json()
            
            logger.success(f"Order placed successfully: {order_data.get('id')}")
            
            # Normalize response
            return {
                "order_id": order_data.get("id", ""),
                "client_order_id": order_data.get("client_order_id", ""),
                "symbol": order_data.get("symbol", ""),
                "quantity": float(order_data.get("qty", 0)),
                "side": order_data.get("side", "").upper(),
                "order_type": order_data.get("type", "").upper(),
                "status": order_data.get("status", "").upper(),
                "created_at": order_data.get("created_at", ""),
            }
    
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            account_id: Account identifier (ignored for Alpaca)
            order_id: Order ID to cancel
            
        Returns:
            Cancellation confirmation
        
        API: DELETE /v2/orders/{order_id}
        """
        logger.info(f"Cancelling Alpaca order: {order_id}")
        
        url = f"{self.base_url}/v2/orders/{order_id}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(url, headers=self._headers())
            
            if response.status_code not in [200, 204]:
                logger.error(f"Failed to cancel order: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to cancel order: {response.status_code}")
            
            logger.success(f"Order {order_id} cancelled successfully")
            
            return {
                "order_id": order_id,
                "status": "CANCELLED",
                "message": "Order cancelled successfully"
            }
    
    async def modify_order(
        self,
        account_id: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing order (Alpaca uses PATCH to replace order).
        
        Args:
            account_id: Account identifier (ignored for Alpaca)
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            
        Returns:
            Modified order confirmation
        
        API: PATCH /v2/orders/{order_id}
        """
        logger.info(f"Modifying Alpaca order: {order_id}")
        
        url = f"{self.base_url}/v2/orders/{order_id}"
        
        # Build modification payload
        payload = {}
        if quantity is not None:
            payload["qty"] = quantity
        if price is not None:
            payload["limit_price"] = price
        
        if not payload:
            raise ValueError("Must specify at least one field to modify (quantity or price)")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(url, headers=self._headers(), json=payload)
            
            if response.status_code != 200:
                logger.error(f"Failed to modify order: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to modify order: {response.status_code}")
            
            order_data = response.json()
            
            logger.success(f"Order {order_id} modified successfully")
            
            return {
                "order_id": order_data.get("id", ""),
                "symbol": order_data.get("symbol", ""),
                "quantity": float(order_data.get("qty", 0)),
                "status": order_data.get("status", "").upper(),
            }
