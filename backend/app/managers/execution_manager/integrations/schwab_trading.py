"""
Charles Schwab Trading API Integration for ExecutionManager

Leverages existing SchwabClient OAuth authentication from app/integrations/schwab_client.py
API Documentation: https://developer.schwab.com/products/trader-api--individual
"""
import httpx
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from app.config import settings
from app.logger import logger
from app.integrations.schwab_client import schwab_client  # Existing OAuth client
from app.managers.execution_manager.integrations.base import (
    BrokerageInterface,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce
)


class SchwabTradingClient(BrokerageInterface):
    """
    Charles Schwab Trading API Client for order execution and account management.
    
    Uses OAuth 2.0 authentication (managed by existing schwab_client).
    Requires user authorization flow before use.
    """
    
    def __init__(self):
        self.base_url = settings.SCHWAB.api_base_url.rstrip("/")
        self.client = schwab_client  # Use existing OAuth-enabled client
        
        if not self.client.app_key or not self.client.app_secret:
            logger.warning("Schwab API credentials not configured")
    
    @property
    def brokerage_name(self) -> str:
        return "schwab"
    
    async def _headers(self) -> Dict[str, str]:
        """Build authentication headers with valid access token."""
        access_token = await self.client.get_valid_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "accept": "application/json",
            "content-type": "application/json"
        }
    
    async def authenticate(self) -> bool:
        """
        Validate Schwab authentication.
        
        Returns:
            True if authenticated (has valid tokens)
        """
        return self.client.is_authenticated()
    
    async def validate_connection(self) -> bool:
        """
        Validate Schwab API connection.
        
        Returns:
            True if connection is valid
        """
        try:
            if not self.client.is_authenticated():
                logger.error("Schwab: Not authenticated. Run 'schwab auth-start' first")
                return False
            
            # Test with account numbers endpoint
            url = f"{self.base_url}/trader/v1/accounts/accountNumbers"
            headers = await self._headers()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                
            if response.status_code == 200:
                logger.info("Schwab connection validated")
                return True
            
            logger.error(f"Schwab connection failed: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Schwab connection error: {e}")
            return False
    
    async def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Args:
            account_id: Schwab account number (encrypted hash)
            
        Returns:
            Balance information dictionary with keys:
            - cash: Cash balance
            - buying_power: Available buying power
            - portfolio_value: Total portfolio value
            - equity: Account equity
        
        API: GET /trader/v1/accounts/{accountNumber}
        """
        logger.info(f"Fetching Schwab account balance for {account_id}")
        
        url = f"{self.base_url}/trader/v1/accounts/{account_id}"
        headers = await self._headers()
        
        # Request with fields parameter to get full details
        params = {"fields": "positions"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to get account balance: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get account balance: {response.status_code}")
            
            data = response.json()
            account_data = data.get("securitiesAccount", {})
            
            # Extract balance information
            current_balances = account_data.get("currentBalances", {})
            initial_balances = account_data.get("initialBalances", {})
            
            # Normalize to our standard format
            return {
                "cash": float(current_balances.get("cashBalance", 0)),
                "buying_power": float(current_balances.get("buyingPower", 0)),
                "portfolio_value": float(current_balances.get("liquidationValue", 0)),
                "equity": float(current_balances.get("equity", 0)),
                "account_number": account_data.get("accountNumber", ""),
                "account_type": account_data.get("type", ""),
                "is_day_trader": account_data.get("isDayTrader", False),
                "is_closing_only_restricted": account_data.get("isClosingOnlyRestricted", False),
            }
    
    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Args:
            account_id: Schwab account number
            
        Returns:
            List of position dictionaries with keys:
            - symbol: Stock symbol
            - quantity: Number of shares
            - avg_entry_price: Average entry price
            - current_price: Current market price
            - market_value: Current market value
            - unrealized_pnl: Unrealized profit/loss
        
        API: GET /trader/v1/accounts/{accountNumber}
        Note: Positions are embedded in account response
        """
        logger.info(f"Fetching Schwab positions for account {account_id}")
        
        url = f"{self.base_url}/trader/v1/accounts/{account_id}"
        headers = await self._headers()
        
        # Request with positions field
        params = {"fields": "positions"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to get positions: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get positions: {response.status_code}")
            
            data = response.json()
            account_data = data.get("securitiesAccount", {})
            positions = account_data.get("positions", [])
            
            # Normalize to our standard format
            normalized_positions = []
            for pos in positions:
                instrument = pos.get("instrument", {})
                
                # Only handle equity positions
                if instrument.get("assetType") != "EQUITY":
                    continue
                
                quantity = float(pos.get("longQuantity", 0)) - float(pos.get("shortQuantity", 0))
                avg_price = float(pos.get("averagePrice", 0))
                market_value = float(pos.get("marketValue", 0))
                
                # Calculate unrealized P&L
                current_price = market_value / quantity if quantity != 0 else 0
                cost_basis = avg_price * abs(quantity)
                unrealized_pnl = market_value - cost_basis
                unrealized_pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis != 0 else 0
                
                normalized_positions.append({
                    "symbol": instrument.get("symbol", ""),
                    "quantity": quantity,
                    "avg_entry_price": avg_price,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_percent": unrealized_pnl_percent,
                    "asset_type": instrument.get("assetType", ""),
                    "cusip": instrument.get("cusip", ""),
                })
            
            return normalized_positions
    
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
            account_id: Schwab account number
            status: Filter by order status
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            List of order dictionaries
        
        API: GET /trader/v1/accounts/{accountNumber}/orders
        """
        logger.info(f"Fetching Schwab orders for account {account_id}")
        
        url = f"{self.base_url}/trader/v1/accounts/{account_id}/orders"
        headers = await self._headers()
        
        # Build query params
        params = {}
        
        # Date filters (ISO 8601 format)
        if start_date:
            params["fromEnteredTime"] = f"{start_date.isoformat()}T00:00:00.000Z"
        if end_date:
            params["toEnteredTime"] = f"{end_date.isoformat()}T23:59:59.999Z"
        
        # Status mapping
        if status:
            # Schwab statuses: AWAITING_PARENT_ORDER, AWAITING_CONDITION, AWAITING_STOP_CONDITION,
            # AWAITING_MANUAL_REVIEW, ACCEPTED, AWAITING_UR_OUT, PENDING_ACTIVATION, QUEUED,
            # WORKING, REJECTED, PENDING_CANCEL, CANCELED, PENDING_REPLACE, REPLACED, FILLED, EXPIRED, etc.
            if status == OrderStatus.WORKING:
                params["status"] = "WORKING"
            elif status == OrderStatus.FILLED:
                params["status"] = "FILLED"
            elif status == OrderStatus.CANCELLED:
                params["status"] = "CANCELED"  # Note: Schwab uses CANCELED not CANCELLED
            elif status == OrderStatus.REJECTED:
                params["status"] = "REJECTED"
        
        params["maxResults"] = 3000  # Max allowed by Schwab
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to get orders: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to get orders: {response.status_code}")
            
            orders = response.json()
            
            # Normalize to our standard format
            normalized_orders = []
            for order in orders:
                # Extract order leg (usually first leg for equity orders)
                order_legs = order.get("orderLegCollection", [])
                if not order_legs:
                    continue
                
                first_leg = order_legs[0]
                instrument = first_leg.get("instrument", {})
                
                # Map Schwab instruction to our side
                instruction = first_leg.get("instruction", "")
                side = "BUY" if instruction in ["BUY", "BUY_TO_OPEN"] else "SELL"
                
                normalized_orders.append({
                    "order_id": str(order.get("orderId", "")),
                    "symbol": instrument.get("symbol", ""),
                    "quantity": float(first_leg.get("quantity", 0)),
                    "filled_quantity": float(order.get("filledQuantity", 0)),
                    "side": side,
                    "order_type": order.get("orderType", "").upper(),
                    "status": order.get("status", "").upper(),
                    "price": float(order.get("price", 0)) if order.get("price") else None,
                    "stop_price": float(order.get("stopPrice", 0)) if order.get("stopPrice") else None,
                    "entered_time": order.get("enteredTime", ""),
                    "close_time": order.get("closeTime"),
                    "account_id": order.get("accountNumber", ""),
                    "duration": order.get("duration", ""),
                    "order_strategy_type": order.get("orderStrategyType", ""),
                })
            
            return normalized_orders
    
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
            account_id: Schwab account number
            symbol: Stock symbol
            quantity: Number of shares
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            price: Limit price (required for LIMIT orders)
            time_in_force: DAY, GTC (Schwab uses "duration")
            
        Returns:
            Order confirmation dictionary
        
        API: POST /trader/v1/accounts/{accountNumber}/orders
        """
        logger.info(f"Placing Schwab order: {side.value} {quantity} {symbol} @ {order_type.value}")
        
        url = f"{self.base_url}/trader/v1/accounts/{account_id}/orders"
        headers = await self._headers()
        
        # Map our order types to Schwab format
        schwab_order_type = order_type.value  # MARKET, LIMIT, STOP, STOP_LIMIT
        
        # Map instruction
        instruction = "BUY" if side == OrderSide.BUY else "SELL"
        
        # Map duration (time in force)
        duration_map = {
            TimeInForce.DAY: "DAY",
            TimeInForce.GTC: "GOOD_TILL_CANCEL",
            TimeInForce.FOK: "FILL_OR_KILL",
            TimeInForce.IOC: "IMMEDIATE_OR_CANCEL",
        }
        duration = duration_map.get(time_in_force, "DAY")
        
        # Build order payload
        payload = {
            "orderType": schwab_order_type,
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": int(quantity),  # Schwab requires integer
                    "instrument": {
                        "symbol": symbol.upper(),
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        # Add price for LIMIT orders
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit price required for LIMIT orders")
            payload["price"] = price
        
        # Add stop price for STOP orders
        elif order_type == OrderType.STOP:
            if price is None:
                raise ValueError("Stop price required for STOP orders")
            payload["stopPrice"] = price
        
        # Add both for STOP_LIMIT orders
        elif order_type == OrderType.STOP_LIMIT:
            if price is None:
                raise ValueError("Limit and stop price required for STOP_LIMIT orders")
            # For STOP_LIMIT, need both stopPrice and price
            payload["stopPrice"] = price  # Stop trigger
            payload["price"] = price  # Limit price after triggered
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code not in [200, 201]:
                logger.error(f"Failed to place order: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to place order: {response.status_code} - {response.text}")
            
            # Schwab returns order ID in Location header
            location = response.headers.get("Location", "")
            order_id = location.split("/")[-1] if location else ""
            
            logger.success(f"Order placed successfully: {order_id}")
            
            return {
                "order_id": order_id,
                "symbol": symbol,
                "quantity": quantity,
                "side": side.value,
                "order_type": order_type.value,
                "status": "PENDING",  # Schwab doesn't return status in response
                "message": "Order submitted successfully"
            }
    
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            account_id: Schwab account number
            order_id: Order ID to cancel
            
        Returns:
            Cancellation confirmation
        
        API: DELETE /trader/v1/accounts/{accountNumber}/orders/{orderId}
        """
        logger.info(f"Cancelling Schwab order: {order_id}")
        
        url = f"{self.base_url}/trader/v1/accounts/{account_id}/orders/{order_id}"
        headers = await self._headers()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(url, headers=headers)
            
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
        Modify an existing order.
        
        Note: Schwab doesn't have a native modify endpoint. 
        This will cancel the old order and place a new one (cancel/replace pattern).
        
        Args:
            account_id: Schwab account number
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            
        Returns:
            Modified order confirmation
        """
        logger.warning("Schwab doesn't support direct order modification")
        logger.info(f"Modifying Schwab order via cancel/replace: {order_id}")
        
        # This would require:
        # 1. Get the current order details
        # 2. Cancel the current order
        # 3. Place a new order with modified parameters
        
        # For now, raise NotImplementedError
        raise NotImplementedError(
            "Schwab order modification requires cancel and replace. "
            "Use cancel_order() then place_order() manually for now."
        )
