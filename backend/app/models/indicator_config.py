"""Indicator Configuration Models for Session Config.

These dataclasses define the structure for indicator configurations
in session config files.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class SessionIndicatorConfig:
    """Configuration for a session (real-time) indicator.
    
    Session indicators are calculated on bars as they arrive.
    
    Attributes:
        name: Indicator name (e.g., "sma", "rsi", "vwap")
        period: Lookback period (0 if not applicable, e.g., VWAP)
        interval: Which bar interval to compute on (e.g., "5m", "1d")
        type: Indicator type (trend, momentum, volatility, volume, support_resistance)
        params: Additional parameters (e.g., {"num_std": 2.0} for Bollinger Bands)
    
    Examples:
        {"name": "sma", "period": 20, "interval": "5m", "type": "trend"}
        {"name": "vwap", "period": 0, "interval": "1m", "type": "trend"}
        {"name": "bbands", "period": 20, "interval": "5m", "type": "volatility", 
         "params": {"num_std": 2.0}}
    """
    name: str
    period: int
    interval: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate session indicator configuration."""
        # Validate name
        if not self.name or not self.name.strip():
            raise ValueError("Indicator name cannot be empty")
        
        # Validate period
        if self.period < 0:
            raise ValueError(f"Indicator period must be >= 0 (got {self.period})")
        
        # Validate interval using requirement analyzer
        from app.threads.quality.requirement_analyzer import parse_interval
        try:
            parse_interval(self.interval)
        except ValueError as e:
            raise ValueError(
                f"Invalid indicator interval '{self.interval}': {e}"
            )
        
        # Validate type
        valid_types = ["trend", "momentum", "volatility", "volume", "support_resistance"]
        if self.type not in valid_types:
            raise ValueError(
                f"Invalid indicator type '{self.type}'. "
                f"Must be one of: {valid_types}"
            )
        
        # Validate params is a dict
        if not isinstance(self.params, dict):
            raise ValueError("Indicator params must be a dictionary")


@dataclass
class HistoricalIndicatorConfig:
    """Configuration for a historical (context) indicator.
    
    Historical indicators are pre-computed for context, typically on daily/weekly bars.
    
    Attributes:
        name: Indicator name (e.g., "avg_volume", "atr_daily", "high_low")
        period: Lookback period
        unit: Unit for period ("days", "weeks", or "bars")
        interval: Bar interval (typically "1d" for historical)
        type: Indicator type (typically "historical")
        params: Additional parameters
    
    Examples:
        {"name": "avg_volume", "period": 5, "unit": "days", "interval": "1d", "type": "historical"}
        {"name": "high_low", "period": 20, "unit": "days", "interval": "1d", "type": "historical"}
        {"name": "high_low", "period": 4, "unit": "weeks", "interval": "1w", "type": "historical"}
    """
    name: str
    period: int
    unit: str
    interval: str = "1d"
    type: str = "historical"
    params: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate historical indicator configuration."""
        # Validate name
        if not self.name or not self.name.strip():
            raise ValueError("Indicator name cannot be empty")
        
        # Validate period
        if self.period <= 0:
            raise ValueError(f"Indicator period must be > 0 (got {self.period})")
        
        # Validate unit
        valid_units = ["days", "weeks", "bars"]
        if self.unit not in valid_units:
            raise ValueError(
                f"Invalid unit '{self.unit}'. "
                f"Must be one of: {valid_units}"
            )
        
        # Validate interval
        from app.threads.quality.requirement_analyzer import parse_interval
        try:
            parse_interval(self.interval)
        except ValueError as e:
            raise ValueError(
                f"Invalid indicator interval '{self.interval}': {e}"
            )
        
        # Validate type
        if self.type != "historical":
            raise ValueError(
                f"Historical indicator type must be 'historical' (got '{self.type}')"
            )
        
        # Validate params is a dict
        if not isinstance(self.params, dict):
            raise ValueError("Indicator params must be a dictionary")


@dataclass
class IndicatorsConfig:
    """Configuration for all indicators (session and historical).
    
    Attributes:
        session: List of session (real-time) indicator configurations
        historical: List of historical (context) indicator configurations
    """
    session: List[SessionIndicatorConfig] = field(default_factory=list)
    historical: List[HistoricalIndicatorConfig] = field(default_factory=list)
    
    def validate(self) -> None:
        """Validate indicators configuration."""
        # Validate all session indicators
        for i, indicator in enumerate(self.session):
            try:
                indicator.validate()
            except ValueError as e:
                raise ValueError(f"Session indicator {i} ({indicator.name}): {e}")
        
        # Validate all historical indicators
        for i, indicator in enumerate(self.historical):
            try:
                indicator.validate()
            except ValueError as e:
                raise ValueError(f"Historical indicator {i} ({indicator.name}): {e}")
        
        # Check for duplicate indicator keys (would cause conflicts in SessionData)
        session_keys = set()
        for indicator in self.session:
            key = self._make_key(indicator)
            if key in session_keys:
                raise ValueError(
                    f"Duplicate session indicator: {key} "
                    f"({indicator.name}({indicator.period}) on {indicator.interval})"
                )
            session_keys.add(key)
        
        historical_keys = set()
        for indicator in self.historical:
            key = self._make_key(indicator)
            if key in historical_keys:
                raise ValueError(
                    f"Duplicate historical indicator: {key} "
                    f"({indicator.name}({indicator.period}) on {indicator.interval})"
                )
            historical_keys.add(key)
    
    @staticmethod
    def _make_key(indicator) -> str:
        """Generate indicator key (same as IndicatorConfig.make_key)."""
        if indicator.period > 0:
            return f"{indicator.name}_{indicator.period}_{indicator.interval}"
        else:
            return f"{indicator.name}_{indicator.interval}"
