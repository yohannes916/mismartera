"""
Base interface for brokerage integrations.
All brokerage integrations must implement this interface.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    WORKING = "WORKING"
    FILLED = "FILLED"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TimeInForce(str, Enum):
    DAY = "DAY"  # Good for day (all orders must be DAY for this system)
    GTC = "GTC"  # Good till cancelled
    IOC = "IOC"  # Immediate or cancel
    FOK = "FOK"  # Fill or kill


class BrokerageInterface(ABC):
    """
    Abstract base class for brokerage integrations.
    Ensures all brokerages provide a consistent interface.
    """
    
    @property
    @abstractmethod
    def brokerage_name(self) -> str:
        """Name of the brokerage (e.g., 'schwab', 'ibkr', 'paper')"""
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the brokerage.
        
        Returns:
            True if authentication successful
        """
        pass
    
    @abstractmethod
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
            account_id: Account identifier
            symbol: Stock symbol
            quantity: Number of shares
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            price: Limit price (required for LIMIT orders)
            time_in_force: DAY, GTC, IOC, FOK (default: DAY)
            
        Returns:
            Order confirmation dictionary
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            account_id: Account identifier
            order_id: Order ID to cancel
            
        Returns:
            Cancellation confirmation
        """
        pass
    
    @abstractmethod
    async def modify_order(
        self,
        account_id: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing order.
        
        Args:
            account_id: Account identifier
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            
        Returns:
            Modification confirmation
        """
        pass
    
    @abstractmethod
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
            account_id: Account identifier
            status: Filter by order status
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            List of order dictionaries
        """
        pass
    
    @abstractmethod
    async def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balance information.
        
        Args:
            account_id: Account identifier
            
        Returns:
            Balance information dictionary
        """
        pass
    
    @abstractmethod
    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Args:
            account_id: Account identifier
            
        Returns:
            List of position dictionaries
        """
        pass
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the brokerage connection is active.
        
        Returns:
            True if connection is valid
        """
        pass
