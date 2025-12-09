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
    """
    
    def __init__(self, session_data):
        """Initialize indicator manager.
        
        Args:
            session_data: SessionData instance
        """
        self.session_data = session_data
        
        # State storage for stateful indicators (EMA, OBV, VWAP, etc.)
        # Structure: {symbol: {interval: {indicator_key: last_result}}}
        self._indicator_state: Dict[str, Dict[str, Dict[str, IndicatorResult]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        
        # Registered indicators per symbol
        # Structure: {symbol: {interval: [IndicatorConfig, ...]}}
        self._registered_indicators: Dict[str, Dict[str, List[IndicatorConfig]]] = defaultdict(
            lambda: defaultdict(list)
        )
    
    def register_symbol_indicators(
        self,
        symbol: str,
        indicators: List[IndicatorConfig],
        historical_bars: Optional[Dict[str, List[BarData]]] = None
    ):
        """Register indicators for a symbol.
        
        This works for:
        - Pre-session: Register all symbols at start
        - Mid-session: Register new symbol dynamically
        
        Args:
            symbol: Stock symbol
            indicators: List of indicator configurations
            historical_bars: Historical bars for warmup (optional)
        """
        logger.info(f"{symbol}: Registering {len(indicators)} indicators")
        
        # Group indicators by interval
        by_interval = defaultdict(list)
        for config in indicators:
            by_interval[config.interval].append(config)
            self._registered_indicators[symbol][config.interval].append(config)
        
        # If historical bars provided, calculate initial values (warmup)
        if historical_bars:
            for interval, ind_configs in by_interval.items():
                if interval in historical_bars:
                    bars = historical_bars[interval]
                    logger.debug(
                        f"{symbol}: Calculating {len(ind_configs)} indicators "
                        f"on {interval} ({len(bars)} bars)"
                    )
                    
                    for config in ind_configs:
                        self._calculate_and_store(symbol, config, bars)
        
        logger.info(f"{symbol}: Indicator registration complete")
    
    def update_indicators(
        self,
        symbol: str,
        interval: str,
        bars: List[BarData]
    ):
        """Update indicators when new bar arrives.
        
        Called by:
        - DataProcessor (on new base interval bar)
        - Session Coordinator (on derived bar generation)
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "5m")
            bars: All bars for this interval (enough for warmup)
        """
        # Get registered indicators for this symbol/interval
        indicators = self._registered_indicators.get(symbol, {}).get(interval, [])
        
        if not indicators:
            return  # No indicators registered for this interval
        
        logger.debug(
            f"{symbol}: Updating {len(indicators)} indicators on {interval}"
        )
        
        for config in indicators:
            self._calculate_and_store(symbol, config, bars)
    
    def _calculate_and_store(
        self,
        symbol: str,
        config: IndicatorConfig,
        bars: List[BarData]
    ):
        """Calculate indicator and store in SessionData.
        
        Args:
            symbol: Stock symbol
            config: Indicator configuration
            bars: Historical bars
        """
        # Get previous result (for stateful indicators)
        indicator_key = config.make_key()
        previous_result = self._indicator_state[symbol][config.interval].get(indicator_key)
        
        # Calculate indicator
        result = calculate_indicator(
            bars=bars,
            config=config,
            symbol=symbol,
            previous_result=previous_result
        )
        
        # Store result for next iteration (stateful indicators)
        self._indicator_state[symbol][config.interval][indicator_key] = result
        
        # Store in SessionData for AnalysisEngine access
        self._store_in_session_data(symbol, config, result)
    
    def _store_in_session_data(
        self,
        symbol: str,
        config: IndicatorConfig,
        result: IndicatorResult
    ):
        """Store indicator result in SessionData.
        
        Args:
            symbol: Stock symbol
            config: Indicator configuration
            result: Indicator calculation result
        """
        symbol_data = self.session_data.get_symbol_data(symbol)
        if not symbol_data:
            logger.error(f"{symbol}: Symbol data not found, cannot store indicator")
            return
        
        # Create indicator data object
        indicator_key = config.make_key()
        indicator_data = IndicatorData(
            name=config.name,
            type=config.type.value,
            interval=config.interval,
            current_value=result.value,
            last_updated=result.timestamp,
            valid=result.valid
        )
        
        # Store in SessionData
        if not hasattr(symbol_data, 'indicators'):
            symbol_data.indicators = {}
        
        symbol_data.indicators[indicator_key] = indicator_data
        
        if result.valid:
            logger.debug(
                f"{symbol}: {indicator_key} = "
                f"{result.value if not isinstance(result.value, dict) else 'dict'}"
            )
    
    def get_indicator_configs(
        self,
        symbol: str,
        interval: Optional[str] = None
    ) -> List[IndicatorConfig]:
        """Get registered indicator configs for a symbol.
        
        Args:
            symbol: Stock symbol
            interval: Filter by interval (None = all)
            
        Returns:
            List of indicator configurations
        """
        if interval:
            return self._registered_indicators.get(symbol, {}).get(interval, [])
        else:
            # All intervals
            all_configs = []
            for interval_configs in self._registered_indicators.get(symbol, {}).values():
                all_configs.extend(interval_configs)
            return all_configs
    
    def remove_symbol(self, symbol: str):
        """Remove symbol and all its indicators.
        
        Args:
            symbol: Stock symbol to remove
        """
        if symbol in self._indicator_state:
            del self._indicator_state[symbol]
        
        if symbol in self._registered_indicators:
            del self._registered_indicators[symbol]
        
        logger.info(f"{symbol}: Removed from indicator manager")
    
    def get_indicator_count(self, symbol: str) -> int:
        """Get total number of indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Total indicator count
        """
        return sum(
            len(configs) 
            for configs in self._registered_indicators.get(symbol, {}).values()
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
    symbol_data = session_data.get_symbol_data(symbol)
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
