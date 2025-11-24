"""
Charles Schwab API Client Integration
"""
import httpx
import json
import base64
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
from app.config import settings
from app.logger import logger


class SchwabClient:
    """
    Client for interacting with Charles Schwab Trader API
    
    Documentation: https://developer.schwab.com/
    
    OAuth 2.0 Flow:
    1. Generate authorization URL
    2. User authorizes via browser
    3. Receive callback with auth code
    4. Exchange code for access token
    5. Use access token for API calls
    6. Refresh token when expired
    """
    
    def __init__(self):
        self.base_url = settings.SCHWAB_API_BASE_URL
        self.app_key = settings.SCHWAB_APP_KEY
        self.app_secret = settings.SCHWAB_APP_SECRET
        self.callback_url = settings.SCHWAB_CALLBACK_URL
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self._token_file = Path.home() / ".mismartera" / "schwab_tokens.json"
        
        if not self.app_key or not self.app_secret:
            logger.warning("Schwab API credentials not configured")
        else:
            # Try to load existing tokens
            self._load_tokens()
    
    async def validate_connection(self) -> bool:
        """
        Validate Schwab API configuration and connectivity.
        
        Returns:
            True if configuration is valid and API is reachable, False otherwise
        """
        try:
            # Check if credentials are configured
            if not self.app_key or not self.app_secret:
                logger.error("Schwab API credentials not configured")
                return False
            
            if not self.base_url:
                logger.error("Schwab API base URL not configured")
                return False
            
            # Test basic connectivity to Schwab API
            # For now, just verify the configuration is present
            # Full OAuth flow requires user interaction
            logger.info("Schwab API configuration validated")
            logger.info(f"  Base URL: {self.base_url}")
            logger.info(f"  App Key: {self.app_key[:8]}..." if self.app_key else "  App Key: Not set")
            logger.info(f"  Callback URL: {self.callback_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"Schwab connection validation error: {e}")
            return False
    
    def generate_authorization_url(self) -> tuple[str, str]:
        """
        Generate OAuth 2.0 authorization URL for user to visit.
        
        Returns:
            Tuple of (authorization_url, state) where state should be verified in callback
        """
        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Schwab OAuth authorization endpoint
        auth_base_url = "https://api.schwabapi.com/v1/oauth/authorize"
        
        # Request 'readonly' scope for market data access
        params = {
            "client_id": self.app_key,
            "redirect_uri": self.callback_url,
            "response_type": "code",
            "scope": "readonly",  # Required for market data API access
            "state": state,
        }
        
        auth_url = f"{auth_base_url}?{urlencode(params)}"
        logger.info(f"Generated authorization URL with state: {state[:8]}... and scope: readonly")
        
        return auth_url, state
    
    async def exchange_code_for_token(self, authorization_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: OAuth authorization code from callback (URL-encoded or decoded)
            
        Returns:
            Token response with access_token and refresh_token
        """
        from urllib.parse import unquote
        
        # URL decode if it contains encoded characters, otherwise use as-is
        # This handles both manual paste (encoded) and server callback (decoded)
        if '%' in authorization_code:
            decoded_code = unquote(authorization_code)
            logger.info(f"URL decoded authorization code (length: {len(decoded_code)})")
        else:
            decoded_code = authorization_code
            logger.info(f"Using authorization code as-is (length: {len(decoded_code)})")
        
        token_url = "https://api.schwabapi.com/v1/oauth/token"
        
        # Prepare Basic Auth header
        credentials = f"{self.app_key}:{self.app_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        # httpx will automatically URL-encode form data, so pass the decoded code
        data = {
            "grant_type": "authorization_code",
            "code": decoded_code,
            "redirect_uri": self.callback_url,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, headers=headers, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to exchange authorization code: {response.status_code}")
            
            token_data = response.json()
            
            # Store tokens
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            expires_in = token_data.get("expires_in", 1800)  # Default 30 minutes
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            # Save to disk
            self._save_tokens()
            
            logger.success("Successfully obtained access token")
            return token_data
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Returns:
            New token response
        """
        if not self.refresh_token:
            raise RuntimeError("No refresh token available. Please authorize first.")
        
        logger.info("Refreshing Schwab access token")
        
        token_url = "https://api.schwabapi.com/v1/oauth/token"
        
        # Prepare Basic Auth header
        credentials = f"{self.app_key}:{self.app_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, headers=headers, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} {response.text}")
                raise RuntimeError(f"Failed to refresh token: {response.status_code}")
            
            token_data = response.json()
            
            # Update tokens
            self.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            expires_in = token_data.get("expires_in", 1800)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            # Save to disk
            self._save_tokens()
            
            logger.success("Successfully refreshed access token")
            return token_data
    
    async def get_valid_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token
            
        Raises:
            RuntimeError: If no tokens available or refresh fails
        """
        if not self.access_token:
            raise RuntimeError(
                "No access token available. Please authorize first using 'schwab auth-start'"
            )
        
        # Note: Schwab tokens are proprietary format (not standard JWT), so we can't decode them
        # The token is valid if we received it from Schwab's OAuth flow with the readonly scope
        
        # Check if token is expired or will expire soon (5 minutes buffer)
        if self.token_expires_at:
            time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()
            if time_until_expiry < 300:  # Less than 5 minutes
                logger.info("Access token expired or expiring soon, refreshing...")
                await self.refresh_access_token()
        
        return self.access_token
    
    def _load_tokens(self) -> None:
        """Load tokens from disk if they exist."""
        if not self._token_file.exists():
            return
        
        try:
            with open(self._token_file, 'r') as f:
                data = json.load(f)
            
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            expires_at_str = data.get("expires_at")
            
            if expires_at_str:
                self.token_expires_at = datetime.fromisoformat(expires_at_str)
            
            logger.info("Loaded Schwab tokens from disk")
            
        except Exception as e:
            logger.warning(f"Failed to load Schwab tokens: {e}")
    
    def _save_tokens(self) -> None:
        """Save tokens to disk."""
        try:
            # Create directory if it doesn't exist
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
                "saved_at": datetime.now().isoformat(),
            }
            
            # Write with restricted permissions
            with open(self._token_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Set file permissions to owner-only (600)
            import os
            os.chmod(self._token_file, 0o600)
            
            logger.info(f"Saved Schwab tokens to {self._token_file}")
            
        except Exception as e:
            logger.error(f"Failed to save Schwab tokens: {e}")
    
    def clear_tokens(self) -> None:
        """Clear tokens from memory and disk."""
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        
        if self._token_file.exists():
            try:
                self._token_file.unlink()
                logger.info("Cleared Schwab tokens")
            except Exception as e:
                logger.error(f"Failed to delete token file: {e}")
    
    def is_authenticated(self) -> bool:
        """Check if we have valid tokens."""
        return self.access_token is not None and self.refresh_token is not None
    
    async def get_account_info(self, account_id: str) -> Dict[str, Any]:
        """
        Get account information
        
        Args:
            account_id: Schwab account ID
            
        Returns:
            Account information
        """
        logger.info(f"Fetching account info for {account_id}")
        
        # TODO: Implement account info API call
        raise NotImplementedError("Account info API not yet implemented")
    
    async def get_account_balances(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balances
        
        Args:
            account_id: Schwab account ID
            
        Returns:
            Balance information
        """
        logger.info(f"Fetching balances for account {account_id}")
        
        # TODO: Implement balances API call
        raise NotImplementedError("Balances API not yet implemented")
    
    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get current positions
        
        Args:
            account_id: Schwab account ID
            
        Returns:
            List of positions
        """
        logger.info(f"Fetching positions for account {account_id}")
        
        # TODO: Implement positions API call
        raise NotImplementedError("Positions API not yet implemented")
    
    async def place_order(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        time_in_force: str = "DAY"
    ) -> Dict[str, Any]:
        """
        Place a new order
        
        Args:
            account_id: Schwab account ID
            symbol: Stock symbol
            quantity: Number of shares
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            price: Limit price (for LIMIT orders)
            time_in_force: DAY, GTC, IOC, FOK
            
        Returns:
            Order confirmation
        """
        logger.info(f"Placing order: {side} {quantity} {symbol} ({order_type})")
        
        if settings.PAPER_TRADING:
            logger.warning("Paper trading mode - order not sent to broker")
            return {
                "orderId": "PAPER_" + str(hash(f"{symbol}{quantity}")),
                "status": "SIMULATED",
                "message": "Paper trading order"
            }
        
        # TODO: Implement order placement API call
        raise NotImplementedError("Order placement API not yet implemented")
    
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order
        
        Args:
            account_id: Schwab account ID
            order_id: Order ID to cancel
            
        Returns:
            Cancellation confirmation
        """
        logger.info(f"Cancelling order {order_id}")
        
        # TODO: Implement order cancellation
        raise NotImplementedError("Order cancellation not yet implemented")
    
    async def get_orders(
        self,
        account_id: str,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get order history
        
        Args:
            account_id: Schwab account ID
            status: Filter by status (FILLED, CANCELLED, etc.)
            from_date: Start date
            to_date: End date
            
        Returns:
            List of orders
        """
        logger.info(f"Fetching orders for account {account_id}")
        
        # TODO: Implement order history API call
        raise NotImplementedError("Order history API not yet implemented")
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-+time quote
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Quote data
        """
        logger.info(f"Fetching quote for {symbol}")
        
        # TODO: Implement quote API call
        raise NotImplementedError("Quote API not yet implemented")
    
    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get quotes for multiple symbols
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            Dictionary of symbol -> quote data
        """
        logger.info(f"Fetching quotes for {len(symbols)} symbols")
        
        # TODO: Implement bulk quotes API call
        raise NotImplementedError("Bulk quotes API not yet implemented")
    
    async def get_price_history(
        self,
        symbol: str,
        period_type: str = "day",
        period: int = 10,
        frequency_type: str = "minute",
        frequency: int = 5
    ) -> Dict[str, Any]:
        """
        Get historical price data
        
        Args:
            symbol: Stock symbol
            period_type: day, month, year, ytd
            period: Number of periods
            frequency_type: minute, daily, weekly, monthly
            frequency: Frequency value
            
        Returns:
            Historical price data (OHLCV)
        """
        logger.info(f"Fetching price history for {symbol}")
        
        # TODO: Implement price history API call
        raise NotImplementedError("Price history API not yet implemented")
    
    async def stream_quotes(self, symbols: List[str]):
        """
        Stream real-+time quotes via WebSocket
        
        Args:
            symbols: List of symbols to stream
            
        Yields:
            Quote updates
        """
        logger.info(f"Starting quote stream for {symbols}")
        
        # TODO: Implement WebSocket streaming
        raise NotImplementedError("WebSocket streaming not yet implemented")


# Global client instance
schwab_client = SchwabClient()
