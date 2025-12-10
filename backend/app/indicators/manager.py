"""Indicator Manager - integrates indicators with SessionData.

This manager is parameterized and reusable:
- Works per-symbol
- Works for pre-session and mid-session insertion
- Handles warmup periods
- Maintains state for stateful indicators (EMA, OBV, VWAP)
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

from .base import BarData, IndicatorConfig, IndicatorResult, IndicatorData
from .registry import calculate_indicator

logger = logging.getLogger(__name__)


class IndicatorManager:
    """Manages indicator calculation for session data.
    
    This is parameterized and reusable for:
    - Pre-session initialization (all symbols)
    - Mid-session insertion (new symbol)
    - Real-time updates (on new bars)
    
    All indicators stored in SessionData for fast access by AnalysisEngine.
    
    Pattern: "Infer from data structures"
    - No separate tracking of configs or state
    - Everything stored in session_data.indicators with embedded metadata
    - Registration creates self-describing structures
    - Calculation scans structures to find what needs updating
    """
    
    def __init__(self, session_data):
        """Initialize indicator manager.
        
        Args:
            session_data: SessionData instance
        """
        self.session_data = session_data
        # No internal state! Everything lives in session_data structures
    
    def register_symbol_indicators(
        self,
        symbol: str,
        indicators: List[IndicatorConfig],
        historical_bars: Optional[Dict[str, List[BarData]]] = None
    ):
        """Register indicators for a symbol.
        
        Registration = Creating self-describing structures in session_data.
        Each IndicatorData contains its config and state - no separate tracking.
        
        This works for:
        - Pre-session: Register all symbols at start
        - Mid-session: Register new symbol dynamically
        
        Args:
            symbol: Stock symbol
            indicators: List of indicator configurations
            historical_bars: Historical bars for warmup (optional)
        """
        logger.info(f"{symbol}: Registering {len(indicators)} indicators")
        
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            logger.error(f"{symbol}: Cannot register indicators - symbol not found in session_data")
            return
        
        # Create self-describing structures
        for config in indicators:
            key = config.make_key()
            
            # Registration = Create structure with embedded config
            symbol_data.indicators[key] = IndicatorData(
                name=config.name,
                type="session",
                interval=config.interval,
                current_value=None,
                last_updated=None,
                valid=False,
                config=config,  # Store config in structure
                state=None      # Store state in structure
            )
            
            logger.debug(f"{symbol}: Registered indicator {key}")
        
        # If historical bars provided, calculate initial values (warmup)
        if historical_bars:
            for key, ind_data in symbol_data.indicators.items():
                if ind_data.config and ind_data.interval in historical_bars:
                    bars = historical_bars[ind_data.interval]
                    logger.debug(
                        f"{symbol}: Calculating {key} on {ind_data.interval} ({len(bars)} bars)"
                    )
                    self._calculate_and_store(symbol, ind_data, bars)
        
        logger.info(f"{symbol}: Indicator registration complete")
    
    def update_indicators(
        self,
        symbol: str,
        interval: str,
        bars: List[BarData]
    ):
        """Update indicators when new bar arrives.
        
        Scans session_data to find which indicators need calculation.
        No separate tracking - infer from data structures.
        
        Called by:
        - DataProcessor (on new base interval bar)
        - Session Coordinator (on derived bar generation)
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "5m")
            bars: All bars for this interval (enough for warmup)
        """
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return
        
        # Infer which indicators need updating by scanning session_data
        indicators_to_update = [
            ind_data for ind_data in symbol_data.indicators.values()
            if ind_data.interval == interval and ind_data.config is not None
        ]
        
        if not indicators_to_update:
            return
        
        logger.debug(
            f"{symbol}: Updating {len(indicators_to_update)} indicators on {interval}"
        )
        
        for ind_data in indicators_to_update:
            self._calculate_and_store(symbol, ind_data, bars)
    
    def _calculate_and_store(
        self,
        symbol: str,
        ind_data: IndicatorData,
        bars: List[BarData]
    ):
        """Calculate indicator and update in place.
        
        All metadata (config, state) stored in the structure itself.
        No separate tracking needed.
        
        Args:
            symbol: Stock symbol
            ind_data: IndicatorData from session_data (has config and state)
            bars: Historical bars
        """
        if ind_data.config is None:
            logger.warning(f"{symbol}: Indicator missing config, skipping")
            return
        
        # Calculate indicator using embedded config and state
        result = calculate_indicator(
            bars=bars,
            config=ind_data.config,
            symbol=symbol,
            previous_result=ind_data.state  # Use stored state
        )
        
        # Update in place (no separate storage)
        ind_data.current_value = result.value
        ind_data.last_updated = result.timestamp
        ind_data.valid = result.valid
        ind_data.state = result  # Store for next iteration
        
        if result.valid:
            logger.debug(
                f"{symbol}: {ind_data.config.make_key()} = "
                f"{result.value if not isinstance(result.value, dict) else 'dict'}"
            )
    
    
    def get_indicator_configs(
        self,
        symbol: str,
        interval: Optional[str] = None
    ) -> List[IndicatorConfig]:
        """Get registered indicator configs for a symbol.
        
        Infers from session_data structures (no separate tracking).
        
        Args:
            symbol: Stock symbol
            interval: Filter by interval (None = all)
            
        Returns:
            List of indicator configurations
        """
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return []
        
        # Infer configs from data structures
        configs = [
            ind_data.config 
            for ind_data in symbol_data.indicators.values()
            if ind_data.config is not None
        ]
        
        # Filter by interval if specified
        if interval:
            configs = [c for c in configs if c.interval == interval]
        
        return configs
    
    def remove_symbol(self, symbol: str):
        """Remove symbol and all its indicators.
        
        Indicators are stored in session_data, so this is just cleanup if needed.
        SessionData.remove_symbol() already handles the actual deletion.
        
        Args:
            symbol: Stock symbol to remove
        """
        # No internal state to clean up anymore!
        logger.info(f"{symbol}: Indicator manager cleanup (no-op, managed by session_data)")
    
    def get_indicator_count(self, symbol: str) -> int:
        """Get total number of indicators for a symbol.
        
        Infers from session_data structures.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Total indicator count
        """
        symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
        if not symbol_data:
            return 0
        
        # Count indicators with configs
        return sum(
            1 for ind_data in symbol_data.indicators.values()
            if ind_data.config is not None
        )


# Convenience functions for SessionData API enhancement

def get_indicator(
    session_data,
    symbol: str,
    indicator_key: str
) -> Optional[IndicatorData]:
    """Get indicator by key from SessionData.
    
    Args:
        session_data: SessionData instance
        symbol: Stock symbol
        indicator_key: Indicator key (e.g., "sma_20_5m")
    
    Returns:
        IndicatorData or None if not found
    """
    symbol_data = session_data.get_symbol_data(symbol, internal=True)
    if not symbol_data or not hasattr(symbol_data, 'indicators'):
        return None
    
    return symbol_data.indicators.get(indicator_key)


def get_indicator_value(
    session_data,
    symbol: str,
    indicator_key: str,
    field: Optional[str] = None
):
    """Get indicator value directly from SessionData.
    
    Args:
        session_data: SessionData instance
        symbol: Stock symbol
        indicator_key: Indicator key
        field: Field name for multi-value indicators (e.g., "upper" for BB)
    
    Returns:
        Indicator value or None
    """
    indicator = get_indicator(session_data, symbol, indicator_key)
    if not indicator or not indicator.valid:
        return None
    
    value = indicator.current_value
    
    # Handle multi-value indicators (dictionaries)
    if isinstance(value, dict):
        if field is None:
            raise ValueError(
                f"Indicator {indicator_key} returns multiple values. "
                f"Specify field: {list(value.keys())}"
            )
        return value.get(field)
    
    # Single value
    if field is not None:
        raise ValueError(
            f"Indicator {indicator_key} returns single value, "
            f"but field '{field}' was specified"
        )
    return value


def is_indicator_ready(
    session_data,
    symbol: str,
    indicator_key: str
) -> bool:
    """Check if indicator has completed warmup.
    
    Args:
        session_data: SessionData instance
        symbol: Stock symbol
        indicator_key: Indicator key
    
    Returns:
        True if indicator is valid (warmup complete)
    """
    indicator = get_indicator(session_data, symbol, indicator_key)
    return indicator.valid if indicator else False


def get_all_indicators(
    session_data,
    symbol: str,
    indicator_type: Optional[str] = None
) -> Dict[str, IndicatorData]:
    """Get all indicators for a symbol from SessionData.
    
    Args:
        session_data: SessionData instance
        symbol: Stock symbol
        indicator_type: Filter by "session" or "historical" (None = all)
    
    Returns:
        Dict of {indicator_key: IndicatorData}
    """
    symbol_data = session_data.get_symbol_data(symbol)
    if not symbol_data or not hasattr(symbol_data, 'indicators'):
        return {}
    
    if indicator_type is None:
        return symbol_data.indicators
    
    # Filter by type
    return {
        key: ind for key, ind in symbol_data.indicators.items()
        if ind.type == indicator_type
    }
