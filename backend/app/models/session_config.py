"""Session Configuration Model

Defines the structure for session configuration files matching SESSION_ARCHITECTURE.md.

This is a REWRITE for the new session architecture (Phase 2).
Old version backed up to: _old_session_config.py.bak

Key Changes:
1. New structure: symbols, streams, historical, gap_filler
2. Added: historical.enable_quality (default: true)
3. Added: gap_filler.enable_session_quality (default: true)
4. Removed: quality_update_frequency (quality is always event-driven)
5. Added: backtest_config.prefetch_days
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime

# Logging
from app.logger import logger

# Indicator configurations
from app.models.indicator_config import (
    SessionIndicatorConfig,
    HistoricalIndicatorConfig,
    IndicatorsConfig
)


# =============================================================================
# Backtest Configuration
# =============================================================================

@dataclass
class BacktestConfig:
    """Backtest configuration.
    
    Attributes:
        start_date: Start date for backtest window (YYYY-MM-DD)
        end_date: End date for backtest window (YYYY-MM-DD)
        speed_multiplier: Speed multiplier (0=max, >0=realtime multiplier)
    """
    start_date: str
    end_date: str
    speed_multiplier: float = 0.0
    
    def validate(self) -> None:
        """Validate backtest configuration."""
        from datetime import datetime
        
        if not self.start_date:
            raise ValueError("start_date is required")
        
        if not self.end_date:
            raise ValueError("end_date is required")
        
        # Validate date format
        try:
            datetime.strptime(self.start_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid start_date format: {self.start_date}. Expected YYYY-MM-DD")
        
        try:
            datetime.strptime(self.end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid end_date format: {self.end_date}. Expected YYYY-MM-DD")
        
        # Validate date range
        start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        
        if start > end:
            raise ValueError(f"start_date ({self.start_date}) must be <= end_date ({self.end_date})")
        
        # Validate speed_multiplier
        if self.speed_multiplier < 0:
            raise ValueError("speed_multiplier must be >= 0 (0 = max speed)")


# =============================================================================
# Session Data Configuration
# =============================================================================

@dataclass
class HistoricalDataConfig:
    """Historical data configuration for a trailing window.
    
    Attributes:
        trailing_days: Number of trading days to maintain
        intervals: Bar intervals to load (e.g., ["1m", "5m"])
        apply_to: Symbols to apply to ("all" or list of symbols)
    """
    trailing_days: int
    intervals: List[str]
    apply_to: Union[str, List[str]] = "all"
    
    def validate(self, available_symbols: List[str]) -> None:
        """Validate historical data configuration.
        
        Args:
            available_symbols: Available symbols from session config
        """
        # Validate trailing_days
        if self.trailing_days <= 0:
            raise ValueError("trailing_days must be > 0")
        
        # Validate intervals
        if not self.intervals:
            raise ValueError("intervals cannot be empty")
        
        # Use requirement analyzer for validation (supports s, m, d, w)
        from app.threads.quality.requirement_analyzer import parse_interval
        
        for interval in self.intervals:
            try:
                parse_interval(interval)
            except ValueError as e:
                raise ValueError(
                    f"Invalid interval '{interval}': {e}. "
                    f"Supported: seconds (1s, 5s), minutes (1m, 5m, 15m), "
                    f"days (1d), weeks (1w). NO hourly support."
                )
        
        # Validate apply_to
        if isinstance(self.apply_to, str):
            if self.apply_to != "all":
                raise ValueError(
                    f"Invalid apply_to value: '{self.apply_to}'. "
                    "Must be 'all' or a list of symbols"
                )
        elif isinstance(self.apply_to, list):
            if not self.apply_to:
                raise ValueError("apply_to list cannot be empty")
            for symbol in self.apply_to:
                if symbol not in available_symbols:
                    raise ValueError(
                        f"Symbol '{symbol}' in apply_to not found in "
                        f"session_data_config.symbols"
                    )
        else:
            raise ValueError(
                "apply_to must be 'all' or a list of symbols"
            )


@dataclass
class HistoricalConfig:
    """Historical data and indicators configuration.
    
    Attributes:
        enable_quality: Calculate quality for historical bars (default: true)
        data: List of historical data configurations
        indicators: DEPRECATED - use IndicatorsConfig in SessionDataConfig instead
    """
    enable_quality: bool = True
    data: List[HistoricalDataConfig] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)  # DEPRECATED
    
    def validate(self, available_symbols: List[str]) -> None:
        """Validate historical configuration.
        
        Args:
            available_symbols: Available symbols from session config
        """
        # Validate each data config
        for data_config in self.data:
            data_config.validate(available_symbols)
        
        # Warn if using old indicators format
        if self.indicators:
            logger.warning(
                "historical.indicators is DEPRECATED. "
                "Use session_data_config.indicators instead with new format. "
                "See docs/INDICATOR_REFERENCE.md"
            )


@dataclass
class GapFillerConfig:
    """Gap filler configuration (DataQualityManager).
    
    CRITICAL: Gap filling only occurs in LIVE mode.
    
    Attributes:
        enable_session_quality: Calculate quality for session bars (default: true)
        max_retries: Max retry attempts for gap filling - LIVE mode only (default: 5)
        retry_interval_seconds: Seconds between retry attempts - LIVE mode only (default: 60)
    """
    enable_session_quality: bool = True
    max_retries: int = 5
    retry_interval_seconds: int = 60
    
    def validate(self) -> None:
        """Validate gap filler configuration."""
        # Validate max_retries
        if not (1 <= self.max_retries <= 20):
            raise ValueError("max_retries must be between 1 and 20")
        
        # Validate retry_interval_seconds
        if self.retry_interval_seconds < 1:
            raise ValueError("retry_interval_seconds must be >= 1")


@dataclass
class StreamingConfig:
    """Streaming configuration for session coordinator.
    
    Controls automatic session state management based on data lag.
    
    Attributes:
        catchup_threshold_seconds: Lag threshold for session deactivation (default: 60)
                                   If streaming data is more than this many seconds behind
                                   current time, session is auto-deactivated to prevent
                                   notifying analysis engine of old data.
        catchup_check_interval: Check lag every N bars (default: 10)
                               Lower = more responsive, higher = less overhead
    """
    catchup_threshold_seconds: int = 60
    catchup_check_interval: int = 10
    
    def validate(self) -> None:
        """Validate streaming configuration."""
        if self.catchup_threshold_seconds < 1:
            raise ValueError("catchup_threshold_seconds must be >= 1")
        
        if not (1 <= self.catchup_check_interval <= 100):
            raise ValueError("catchup_check_interval must be between 1 and 100")


@dataclass
class SessionDataConfig:
    """Session data configuration.
    
    Attributes:
        symbols: List of symbols to trade/analyze
        streams: Requested data streams (coordinator determines streamed vs generated)
        streaming: Streaming behavior configuration
        historical: Historical data and indicators configuration
        gap_filler: Gap filler configuration (DataQualityManager)
        indicators: Indicator configurations (session and historical) - NEW!
    """
    symbols: List[str]
    streams: List[str]
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    historical: HistoricalConfig = field(default_factory=HistoricalConfig)
    gap_filler: GapFillerConfig = field(default_factory=GapFillerConfig)
    indicators: IndicatorsConfig = field(default_factory=IndicatorsConfig)
    
    def validate(self) -> None:
        """Validate session data configuration."""
        # Validate symbols
        if not self.symbols:
            raise ValueError("symbols list cannot be empty")
        
        for symbol in self.symbols:
            if not symbol or not symbol.strip():
                raise ValueError("Symbol cannot be empty or whitespace")
        
        # Check for duplicates
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("Duplicate symbols found in symbols list")
        
        # Validate streams
        if not self.streams:
            raise ValueError("streams list cannot be empty")
        
        # Use requirement analyzer for validation (supports s, m, d, w, quotes)
        from app.threads.quality.requirement_analyzer import parse_interval
        
        for stream in self.streams:
            # Allow "ticks" and "quotes" special cases
            if stream.lower() in ["ticks", "tick"]:
                raise ValueError(
                    "Ticks are not supported. "
                    "Use 'quotes' for quote data or bar intervals (1s, 1m, etc.)"
                )
            
            try:
                parse_interval(stream)
            except ValueError as e:
                raise ValueError(
                    f"Invalid stream '{stream}': {e}. "
                    f"Supported: seconds (1s, 5s), minutes (1m, 5m, 15m), "
                    f"days (1d), weeks (1w), or 'quotes'. NO hourly support."
                )
        
        # Validate sub-configs
        self.streaming.validate()
        self.historical.validate(self.symbols)
        self.gap_filler.validate()
        self.indicators.validate()


# =============================================================================
# Trading Configuration
# =============================================================================

@dataclass
class TradingConfig:
    """Trading configuration and risk parameters.
    
    Attributes:
        max_buying_power: Maximum total buying power (USD)
        max_per_trade: Maximum per trade (USD)
        max_per_symbol: Maximum per symbol (USD)
        max_open_positions: Maximum concurrent positions
    """
    max_buying_power: float
    max_per_trade: float
    max_per_symbol: float
    max_open_positions: int
    
    def validate(self) -> None:
        """Validate trading configuration."""
        if self.max_buying_power <= 0:
            raise ValueError("max_buying_power must be > 0")
        
        if self.max_per_trade <= 0:
            raise ValueError("max_per_trade must be > 0")
        
        if self.max_per_symbol <= 0:
            raise ValueError("max_per_symbol must be > 0")
        
        if self.max_per_trade > self.max_buying_power:
            raise ValueError(
                "max_per_trade cannot exceed max_buying_power"
            )
        
        if self.max_per_symbol > self.max_buying_power:
            raise ValueError(
                "max_per_symbol cannot exceed max_buying_power"
            )
        
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be > 0")


# =============================================================================
# API Configuration
# =============================================================================

@dataclass
class APIConfig:
    """API configuration for data and trading providers.
    
    Attributes:
        data_api: Data provider (e.g., "alpaca", "schwab")
        trade_api: Trading API provider (e.g., "alpaca", "schwab")
        account_id: Optional account identifier
    """
    data_api: str
    trade_api: str
    account_id: Optional[str] = None
    
    def validate(self) -> None:
        """Validate API configuration."""
        valid_data_apis = ["alpaca", "schwab"]
        if self.data_api not in valid_data_apis:
            raise ValueError(
                f"Invalid data_api: {self.data_api}. "
                f"Must be one of {valid_data_apis}"
            )
        
        valid_trade_apis = ["alpaca", "schwab"]
        if self.trade_api not in valid_trade_apis:
            raise ValueError(
                f"Invalid trade_api: {self.trade_api}. "
                f"Must be one of {valid_trade_apis}"
            )


# =============================================================================
# Root Session Configuration
# =============================================================================

@dataclass
class SessionConfig:
    """Complete session configuration.
    
    Root configuration object loaded from JSON files matching
    SESSION_ARCHITECTURE.md specification.
    
    Attributes:
        session_name: Descriptive name for this session
        exchange_group: Exchange group (e.g., "US_EQUITY", "LSE", "TSE")
        asset_class: Asset class (e.g., "EQUITY", "OPTION", "FUTURES")
        mode: Operation mode ("live" or "backtest")
        backtest_config: Backtest window configuration (required for backtest mode)
        session_data_config: Session data configuration
        trading_config: Trading parameters and risk limits
        api_config: API provider configuration
        metadata: Optional additional metadata
    """
    session_name: str
    exchange_group: str
    asset_class: str
    mode: str
    backtest_config: Optional[BacktestConfig]
    session_data_config: SessionDataConfig
    trading_config: TradingConfig
    api_config: APIConfig
    metadata: Optional[Dict[str, Any]] = None
    
    def validate(self) -> None:
        """Validate entire session configuration."""
        # Validate session_name
        if not self.session_name or not self.session_name.strip():
            raise ValueError("session_name cannot be empty")
        
        # Validate mode
        valid_modes = ["live", "backtest"]
        if self.mode not in valid_modes:
            raise ValueError(
                f"Invalid mode: {self.mode}. Must be one of {valid_modes}"
            )
        
        # Backtest mode requires backtest_config
        if self.mode == "backtest" and not self.backtest_config:
            raise ValueError(
                "backtest_config is required when mode is 'backtest'"
            )
        
        # Validate each component
        if self.backtest_config:
            self.backtest_config.validate()
        
        self.session_data_config.validate()
        self.trading_config.validate()
        self.api_config.validate()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SessionConfig:
        """Create SessionConfig from dictionary (loaded from JSON).
        
        Args:
            data: Dictionary representation of config
            
        Returns:
            SessionConfig instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Extract required root fields
        session_name = data.get("session_name")
        if not session_name:
            raise ValueError("Missing required field: session_name")
        
        exchange_group = data.get("exchange_group", "US_EQUITY")
        asset_class = data.get("asset_class", "EQUITY")
        
        mode = data.get("mode")
        if not mode:
            raise ValueError("Missing required field: mode")
        
        # Parse backtest config (required for backtest mode)
        backtest_config = None
        backtest_data = data.get("backtest_config")
        if backtest_data:
            backtest_config = BacktestConfig(
                start_date=backtest_data.get("start_date"),
                end_date=backtest_data.get("end_date"),
                speed_multiplier=backtest_data.get("speed_multiplier", 0.0)
            )
        
        # Parse session_data_config (required)
        sd_data = data.get("session_data_config")
        if not sd_data:
            raise ValueError("Missing required field: session_data_config")
        
        # Parse symbols
        symbols = sd_data.get("symbols")
        if not symbols:
            raise ValueError(
                "Missing required field: session_data_config.symbols"
            )
        
        # Parse streams
        streams = sd_data.get("streams")
        if not streams:
            raise ValueError(
                "Missing required field: session_data_config.streams"
            )
        
        # Parse historical config
        hist_data = sd_data.get("historical", {})
        
        # Parse historical.data
        historical_data_configs = []
        for hd in hist_data.get("data", []):
            historical_data_configs.append(
                HistoricalDataConfig(
                    trailing_days=hd.get("trailing_days"),
                    intervals=hd.get("intervals"),
                    apply_to=hd.get("apply_to", "all")
                )
            )
        
        # Parse historical.indicators
        indicators = hist_data.get("indicators", {})
        
        historical = HistoricalConfig(
            enable_quality=hist_data.get("enable_quality", True),
            data=historical_data_configs,
            indicators=indicators
        )
        
        # Parse streaming config
        stream_data = sd_data.get("streaming", {})
        streaming = StreamingConfig(
            catchup_threshold_seconds=stream_data.get("catchup_threshold_seconds", 60),
            catchup_check_interval=stream_data.get("catchup_check_interval", 10)
        )
        
        # Parse gap_filler config
        gf_data = sd_data.get("gap_filler", {})
        gap_filler = GapFillerConfig(
            max_retries=gf_data.get("max_retries", 5),
            retry_interval_seconds=gf_data.get("retry_interval_seconds", 60),
            enable_session_quality=gf_data.get("enable_session_quality", True)
        )
        
        session_data_config = SessionDataConfig(
            symbols=symbols,
            streams=streams,
            streaming=streaming,
            historical=historical,
            gap_filler=gap_filler
        )
        
        # Parse trading config (required)
        trading_data = data.get("trading_config")
        if not trading_data:
            raise ValueError("Missing required field: trading_config")
        
        trading_config = TradingConfig(
            max_buying_power=trading_data.get("max_buying_power"),
            max_per_trade=trading_data.get("max_per_trade"),
            max_per_symbol=trading_data.get("max_per_symbol"),
            max_open_positions=trading_data.get("max_open_positions")
        )
        
        # Parse API config (required)
        api_data = data.get("api_config")
        if not api_data:
            raise ValueError("Missing required field: api_config")
        
        api_config = APIConfig(
            data_api=api_data.get("data_api"),
            trade_api=api_data.get("trade_api"),
            account_id=api_data.get("account_id")
        )
        
        # Create and validate config
        config = cls(
            session_name=session_name,
            exchange_group=exchange_group,
            asset_class=asset_class,
            mode=mode,
            backtest_config=backtest_config,
            session_data_config=session_data_config,
            trading_config=trading_config,
            api_config=api_config,
            metadata=data.get("metadata")
        )
        
        config.validate()
        logger.info(f"Loaded and validated session config: {session_name}")
        return config
    
    @classmethod
    def from_file(cls, file_path: str) -> SessionConfig:
        """Load SessionConfig from JSON file.
        
        Args:
            file_path: Path to JSON configuration file
            
        Returns:
            SessionConfig instance
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid or config is invalid
        """
        import json
        from pathlib import Path
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}") from e
        
        return cls.from_dict(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        result = {
            "session_name": self.session_name,
            "exchange_group": self.exchange_group,
            "asset_class": self.asset_class,
            "mode": self.mode,
        }
        
        if self.backtest_config:
            result["backtest_config"] = {
                "start_date": self.backtest_config.start_date,
                "end_date": self.backtest_config.end_date,
                "speed_multiplier": self.backtest_config.speed_multiplier
            }
        
        result["session_data_config"] = {
            "symbols": self.session_data_config.symbols,
            "streams": self.session_data_config.streams,
            "streaming": {
                "catchup_threshold_seconds": self.session_data_config.streaming.catchup_threshold_seconds,
                "catchup_check_interval": self.session_data_config.streaming.catchup_check_interval
            },
            "historical": {
                "enable_quality": self.session_data_config.historical.enable_quality,
                "data": [
                    {
                        "trailing_days": hd.trailing_days,
                        "intervals": hd.intervals,
                        "apply_to": hd.apply_to
                    }
                    for hd in self.session_data_config.historical.data
                ],
                "indicators": self.session_data_config.historical.indicators
            },
            "gap_filler": {
                "max_retries": self.session_data_config.gap_filler.max_retries,
                "retry_interval_seconds": self.session_data_config.gap_filler.retry_interval_seconds,
                "enable_session_quality": self.session_data_config.gap_filler.enable_session_quality
            }
        }
        
        result["trading_config"] = {
            "max_buying_power": self.trading_config.max_buying_power,
            "max_per_trade": self.trading_config.max_per_trade,
            "max_per_symbol": self.trading_config.max_per_symbol,
            "max_open_positions": self.trading_config.max_open_positions
        }
        
        result["api_config"] = {
            "data_api": self.api_config.data_api,
            "trade_api": self.api_config.trade_api
        }
        if self.api_config.account_id:
            result["api_config"]["account_id"] = self.api_config.account_id
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result
