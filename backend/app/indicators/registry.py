"""Indicator registry and calculation dispatcher."""

import logging
from typing import Callable, Dict, List, Optional

from .base import BarData, IndicatorConfig, IndicatorResult

logger = logging.getLogger(__name__)

# Type for indicator calculator functions
IndicatorCalculator = Callable[
    [List[BarData], IndicatorConfig, Optional[IndicatorResult]],
    IndicatorResult
]


class IndicatorRegistry:
    """Central registry of all indicator calculators.
    
    This provides a single source of truth for all indicators.
    """
    
    def __init__(self):
        self._calculators: Dict[str, IndicatorCalculator] = {}
        self._metadata: Dict[str, Dict[str, str]] = {}
    
    def register(
        self,
        name: str,
        calculator: IndicatorCalculator,
        description: str = ""
    ):
        """Register an indicator calculator.
        
        Args:
            name: Indicator name (e.g., "sma", "rsi")
            calculator: Function that calculates the indicator
            description: Brief description
        """
        if name in self._calculators:
            logger.warning(f"Overwriting existing indicator: {name}")
        
        self._calculators[name] = calculator
        self._metadata[name] = {"description": description}
        logger.debug(f"Registered indicator: {name}")
    
    def get(self, name: str) -> Optional[IndicatorCalculator]:
        """Get calculator for an indicator.
        
        Args:
            name: Indicator name
            
        Returns:
            Calculator function or None if not found
        """
        return self._calculators.get(name)
    
    def list_all(self) -> List[str]:
        """List all registered indicators."""
        return sorted(self._calculators.keys())
    
    def is_registered(self, name: str) -> bool:
        """Check if indicator is registered."""
        return name in self._calculators
    
    def get_metadata(self, name: str) -> Optional[Dict[str, str]]:
        """Get metadata for an indicator."""
        return self._metadata.get(name)


# Global registry instance
INDICATOR_REGISTRY = IndicatorRegistry()


def indicator(name: str, description: str = ""):
    """Decorator to register an indicator calculator.
    
    Usage:
        @indicator("sma", "Simple Moving Average")
        def calculate_sma(bars, config, previous):
            ...
    """
    def decorator(func: IndicatorCalculator):
        INDICATOR_REGISTRY.register(name, func, description)
        return func
    return decorator


def calculate_indicator(
    bars: List[BarData],
    config: IndicatorConfig,
    symbol: str,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Calculate indicator value.
    
    This is the main entry point for indicator calculation.
    Unified interface that works for:
    - Pre-session initialization
    - Mid-session symbol insertion
    - Real-time updates
    - ANY interval (1s, 1m, 5m, 1d, 1w, etc.)
    
    Args:
        bars: Historical bars (includes enough for warmup)
        config: Indicator configuration
        symbol: Symbol being processed (for logging)
        previous_result: Previous result (for stateful indicators like EMA, OBV)
    
    Returns:
        IndicatorResult with value and validity
    
    Raises:
        ValueError: If indicator not registered or invalid config
    """
    # Validate we have bars
    if not bars:
        return IndicatorResult(
            timestamp=None,
            value=None,
            valid=False
        )
    
    # Check if enough bars for warmup
    warmup_needed = config.warmup_bars()
    if len(bars) < warmup_needed:
        logger.debug(
            f"{symbol} {config.name}: Warmup incomplete "
            f"({len(bars)}/{warmup_needed} bars)"
        )
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Get calculator from registry
    calculator = INDICATOR_REGISTRY.get(config.name)
    if not calculator:
        raise ValueError(
            f"Unknown indicator: {config.name}. "
            f"Registered indicators: {INDICATOR_REGISTRY.list_all()}"
        )
    
    # Calculate indicator
    try:
        result = calculator(bars, config, previous_result)
        
        if result.valid:
            logger.debug(
                f"{symbol} {config.name}: "
                f"Calculated value at {result.timestamp}"
            )
        
        return result
        
    except Exception as e:
        logger.error(
            f"{symbol} {config.name}: Calculation failed: {e}",
            exc_info=True
        )
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )


def list_indicators() -> List[str]:
    """List all registered indicators.
    
    Returns:
        Sorted list of indicator names
    """
    return INDICATOR_REGISTRY.list_all()
