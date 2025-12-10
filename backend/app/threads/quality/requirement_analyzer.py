"""Session Requirement Analyzer

Analyzes session configuration to determine minimum base interval needed.

Key Principle:
    Figure out what we NEED first (from config + implicit requirements),
    THEN check if database has it. No fallbacks, no magic - just validation.

Requirements Covered:
    1-6: Core requirement analysis
    9-12: Base interval selection rules  
    75-77: Configuration validation
"""

from typing import List, Optional, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import re

from app.logger import logger

if TYPE_CHECKING:
    from app.indicators import IndicatorConfig


# =============================================================================
# Enumerations
# =============================================================================

class IntervalType(Enum):
    """Interval type classification.
    
    NOTE: Hourly intervals are NOT supported.
    Use minutes instead (e.g., 60m, 120m, 240m for 1h, 2h, 4h).
    """
    SECOND = "second"      # 1s, 5s, 10s, etc.
    MINUTE = "minute"      # 1m, 5m, 15m, 60m, etc.
    DAY = "day"            # 1d, 5d, etc.
    WEEK = "week"          # 1w, 2w, etc.
    QUOTE = "quote"        # quotes


class RequirementSource(Enum):
    """Source of interval requirement."""
    EXPLICIT = "explicit"                # From session_config.streams
    IMPLICIT_DERIVATION = "implicit_derivation"  # Needed to generate requested interval
    IMPLICIT_INDICATOR = "implicit_indicator"    # Needed by indicator


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class IntervalInfo:
    """Parsed information about an interval."""
    interval: str
    type: IntervalType
    seconds: int           # Duration in seconds
    is_base: bool          # True if can be streamed (1s, 1m, 1d)
    
    def __post_init__(self):
        """Validate interval info."""
        # Quotes have 0 seconds (not applicable), which is valid
        if self.type != IntervalType.QUOTE and self.seconds <= 0:
            raise ValueError(f"Invalid interval duration: {self.seconds}")


@dataclass
class IntervalRequirement:
    """A single interval requirement with its source and reasoning."""
    interval: str
    source: RequirementSource
    reason: str
    
    def __repr__(self) -> str:
        return f"{self.interval} ({self.source.value}): {self.reason}"


@dataclass
class SessionRequirements:
    """Complete analysis of session interval requirements."""
    explicit_intervals: List[str]
    implicit_intervals: List[IntervalRequirement]
    required_base_interval: str
    derivable_intervals: List[str]
    all_requirements: List[IntervalRequirement] = field(default_factory=list)
    
    def __post_init__(self):
        """Combine all requirements."""
        # Add explicit intervals to all_requirements
        for interval in self.explicit_intervals:
            self.all_requirements.append(
                IntervalRequirement(
                    interval=interval,
                    source=RequirementSource.EXPLICIT,
                    reason=f"Explicitly requested in session config"
                )
            )
        
        # Add implicit requirements
        self.all_requirements.extend(self.implicit_intervals)


@dataclass
class IndicatorRequirements:
    """Bar requirements for a single indicator.
    
    Attributes:
        indicator_key: Unique indicator key (e.g., "sma_20_1d")
        required_intervals: List of intervals needed (e.g., ["1m", "1d"])
        historical_bars: Number of bars needed for warmup
        historical_days: Estimated calendar days to cover historical_bars
        reason: Human-readable explanation
    """
    indicator_key: str
    required_intervals: List[str]
    historical_bars: int
    historical_days: int
    reason: str


# =============================================================================
# Interval Parsing
# =============================================================================

def parse_interval(interval: str) -> IntervalInfo:
    """Parse interval string into structured info.
    
    Args:
        interval: Interval string (e.g., "1s", "5m", "1d", "quotes")
    
    Returns:
        IntervalInfo with type, seconds, and base status
        
    Raises:
        ValueError: If interval format is invalid (Req 65, 75)
        
    Examples:
        >>> parse_interval("5s")
        IntervalInfo(interval='5s', type=SECOND, seconds=5, is_base=False)
        
        >>> parse_interval("1m")
        IntervalInfo(interval='1m', type=MINUTE, seconds=60, is_base=True)
    """
    if not interval:
        raise ValueError("Interval cannot be empty")
    
    # Special case: quotes
    if interval.lower() == "quotes":
        return IntervalInfo(
            interval="quotes",
            type=IntervalType.QUOTE,
            seconds=0,  # Not applicable for quotes
            is_base=False  # Quotes are not bar intervals
        )
    
    # Parse bar interval: <number><unit>
    # Normalize to lowercase for parsing
    interval_lower = interval.lower()
    match = re.match(r'^(\d+)([smdw])$', interval_lower)
    if not match:
        raise ValueError(
            f"Invalid interval format: '{interval}'. "
            f"Expected format: <number><unit> (e.g., '1s', '5m', '1d', '1w') or 'quotes'. "
            f"NOTE: Hourly intervals not supported - use minutes (60m, 120m, etc.)"
        )
    
    value = int(match.group(1))
    unit = match.group(2)
    
    # Use normalized lowercase version
    interval = interval_lower
    
    # Determine type and seconds
    if unit == 's':
        interval_type = IntervalType.SECOND
        seconds = value
        is_base = (value == 1)  # Only 1s is base
    elif unit == 'm':
        interval_type = IntervalType.MINUTE
        seconds = value * 60
        is_base = (value == 1)  # Only 1m is base
    elif unit == 'd':
        interval_type = IntervalType.DAY
        seconds = value * 86400
        is_base = (value == 1)  # Only 1d is base
    elif unit == 'w':
        interval_type = IntervalType.WEEK
        seconds = value * 604800  # 7 days
        is_base = (value == 1)  # Only 1w is base
    else:
        raise ValueError(f"Invalid unit: {unit}. Supported: s, m, d, w (no hourly!)")
    
    return IntervalInfo(
        interval=interval,
        type=interval_type,
        seconds=seconds,
        is_base=is_base
    )


# =============================================================================
# Base Interval Determination
# =============================================================================

def determine_required_base(interval: str) -> str:
    """Determine which base interval is required to generate this interval.
    
    Args:
        interval: Target interval (e.g., "5s", "5m", "1d")
        
    Returns:
        Required base interval ("1s", "1m", or "1d")
        
    Rules (Req 9-11):
        - Sub-second (5s, 10s, etc.) → requires 1s (only valid source)
        - Minute (5m, 15m, 60m, etc.) → requires 1m (preferred, not 1s)
        - Day (5d, 10d, etc.) → requires 1d (aggregation from 1d)
        - Week (2w, 4w, etc.) → requires 1w (aggregation from 1w)
        
    Examples:
        >>> determine_required_base("5s")
        "1s"
        
        >>> determine_required_base("5m")
        "1m"
        
        >>> determine_required_base("1d")
        "1d"
    """
    info = parse_interval(interval)
    
    # If it's already a base interval, return it
    if info.is_base:
        return interval
    
    # Quotes don't have a base interval
    if info.type == IntervalType.QUOTE:
        return None
    
    # Rule 1 (Req 9): Sub-second intervals require 1s
    if info.type == IntervalType.SECOND:
        return "1s"
    
    # Rule 2 (Req 10): Minute intervals require 1m
    if info.type == IntervalType.MINUTE:
        return "1m"
    
    # Rule 3 (Req 11): Multi-day intervals require 1d (for aggregation)
    if info.type == IntervalType.DAY:
        return "1d"
    
    # Rule 4: Multi-week intervals require 1w (aggregate weekly bars)
    if info.type == IntervalType.WEEK:
        return "1w"
    
    raise ValueError(f"Cannot determine base interval for: {interval}")


def select_smallest_base(bases: List[str]) -> str:
    """Select the smallest base interval from a list.
    
    Args:
        bases: List of base intervals (e.g., ["1s", "1m", "1d"])
        
    Returns:
        Smallest base interval
        
    Rule (Req 12):
        Priority: 1s < 1m < 1d < 1w
        
    Examples:
        >>> select_smallest_base(["1m", "1s", "1m"])
        "1s"
        
        >>> select_smallest_base(["1m", "1d"])
        "1m"
        
        >>> select_smallest_base(["1d", "1w"])
        "1d"
    """
    if not bases:
        raise ValueError("Cannot select base from empty list")
    
    # Priority order (smallest first)
    priority = {"1s": 1, "1m": 2, "1d": 3, "1w": 4}
    
    # Filter out None values and get unique bases
    valid_bases = [b for b in bases if b is not None]
    unique_bases = list(set(valid_bases))
    
    if not unique_bases:
        raise ValueError("No valid base intervals found")
    
    # Sort by priority and return smallest
    smallest = min(unique_bases, key=lambda b: priority.get(b, 999))
    return smallest


# =============================================================================
# Main Analysis Function
# =============================================================================

def analyze_session_requirements(
    streams: List[str],
    indicator_requirements: Optional[List[str]] = None
) -> SessionRequirements:
    """Analyze session configuration to determine interval requirements.
    
    This is the main entry point for requirement analysis.
    
    Args:
        streams: Explicit intervals from session_config.streams
        indicator_requirements: Intervals required by indicators
        
    Returns:
        SessionRequirements with complete analysis
        
    Raises:
        ValueError: If configuration is invalid
        
    Requirements Covered:
        1: Analyze explicit intervals from config
        2: Detect implicit intervals for derivation
        3: Detect implicit intervals from indicators  
        4: Calculate minimum base interval needed
        5: Validate all intervals are derivable
        6: Provide clear reasoning
        
    Examples:
        >>> reqs = analyze_session_requirements(["5s", "5m"])
        >>> reqs.required_base_interval
        "1s"
        >>> reqs.explicit_intervals
        ["5s", "5m"]
    """
    if not streams:
        raise ValueError("Streams list cannot be empty")
    
    indicator_requirements = indicator_requirements or []
    
    # Step 1: Parse and validate all explicit intervals (Req 1)
    explicit_intervals = []
    for stream in streams:
        try:
            parse_interval(stream)  # Validate format
            explicit_intervals.append(stream)
        except ValueError as e:
            raise ValueError(f"Invalid stream '{stream}': {e}")
    
    # Step 2: Determine implicit requirements from derivation (Req 2)
    implicit_requirements = []
    required_bases = []
    
    for interval in explicit_intervals:
        if interval == "quotes":
            continue  # Quotes don't need a base interval
            
        base_needed = determine_required_base(interval)
        if base_needed and base_needed not in explicit_intervals:
            # This is an implicit requirement
            implicit_requirements.append(
                IntervalRequirement(
                    interval=base_needed,
                    source=RequirementSource.IMPLICIT_DERIVATION,
                    reason=f"Required to generate {interval}"
                )
            )
        
        if base_needed:
            required_bases.append(base_needed)
    
    # Step 3: Add indicator requirements (Req 3)
    for interval in indicator_requirements:
        try:
            parse_interval(interval)  # Validate format
        except ValueError as e:
            raise ValueError(f"Invalid indicator requirement '{interval}': {e}")
        
        if interval not in explicit_intervals:
            implicit_requirements.append(
                IntervalRequirement(
                    interval=interval,
                    source=RequirementSource.IMPLICIT_INDICATOR,
                    reason=f"Required by indicator"
                )
            )
            
            # Also add its base requirement
            base_needed = determine_required_base(interval)
            if base_needed:
                required_bases.append(base_needed)
    
    # Step 4: Select minimum base interval (Req 4, 12)
    if not required_bases:
        # No bar intervals requested (maybe just quotes?)
        raise ValueError("No bar intervals requested")
    
    required_base_interval = select_smallest_base(required_bases)
    
    # Step 5: Determine which intervals can be derived from base (Req 5)
    # Only include intervals that need to be GENERATED (not the base itself)
    all_requested = set(explicit_intervals + [r.interval for r in implicit_requirements])
    all_requested.discard("quotes")  # Remove quotes from bar intervals
    all_requested.discard(required_base_interval)  # Remove base interval itself
    
    derivable_intervals = list(all_requested)
    
    # Sort for consistent output
    derivable_intervals.sort()
    
    # Remove duplicate implicit requirements
    unique_implicit = []
    seen_intervals = set()
    for req in implicit_requirements:
        if req.interval not in seen_intervals:
            unique_implicit.append(req)
            seen_intervals.add(req.interval)
    
    return SessionRequirements(
        explicit_intervals=explicit_intervals,
        implicit_intervals=unique_implicit,
        required_base_interval=required_base_interval,
        derivable_intervals=derivable_intervals
    )


# =============================================================================
# Validation Functions
# =============================================================================

def validate_configuration(streams: List[str], mode: str) -> None:
    """Validate session configuration.
    
    Args:
        streams: Intervals from session config
        mode: Session mode ("backtest" or "live")
        
    Raises:
        ValueError: If configuration is invalid
        
    Requirements:
        76: No ticks supported
        77: Quote validation based on mode
    """
    for stream in streams:
        # Req 76: Ticks not supported
        if stream.lower() in ["ticks", "tick"]:
            raise ValueError(
                "Ticks are not supported. "
                "Use 'quotes' for quote data or bar intervals (1s, 1m, etc.)"
            )
        
        # Validate format
        try:
            parse_interval(stream)
        except ValueError as e:
            raise ValueError(f"Invalid stream configuration: {e}")


# =============================================================================
# Indicator Auto-Provisioning
# =============================================================================

def analyze_indicator_requirements(
    indicator_config: "IndicatorConfig",
    system_manager,  # SystemManager singleton
    warmup_multiplier: float = 2.0,
    from_date = None,  # Reference date (defaults to current)
    exchange: str = "NYSE"
) -> IndicatorRequirements:
    """Analyze bar requirements for an indicator (auto-provisioning).
    
    Determines what intervals and historical data are needed to compute
    an indicator. Used by scanners to automatically provision required bars.
    
    **USES TIMEMANAGER**: All calendar calculations use TimeManager APIs
    (accessed via SystemManager) to account for holidays, weekends, early
    closes, and exchange-specific market hours.
    
    Args:
        indicator_config: Indicator configuration
        system_manager: SystemManager singleton (provides TimeManager access)
        warmup_multiplier: Extra buffer for warmup (default 2.0)
            - 2.0 means request 2x the warmup bars
            - Accounts for holidays, gaps, data quality issues
        from_date: Reference date to calculate back from (defaults to current)
        exchange: Exchange identifier (default: "NYSE")
    
    Returns:
        IndicatorRequirements with intervals and historical needs
        
    Examples:
        >>> config = IndicatorConfig(name="sma", period=20, interval="1d")
        >>> reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
        >>> reqs.required_intervals
        ["1d"]  # Only needs daily bars (1d is a base interval)
        >>> reqs.historical_bars
        40  # 20 * 2.0
        
        >>> config = IndicatorConfig(name="sma", period=20, interval="5m")
        >>> reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
        >>> reqs.required_intervals
        ["1m", "5m"]  # Needs 1m base + 5m derived
        >>> reqs.historical_bars
        40
        
    Algorithm:
        1. Parse indicator's interval
        2. Determine if it needs a base interval (e.g., 5m needs 1m)
        3. Calculate bars needed: indicator.warmup_bars() * warmup_multiplier
        4. Estimate calendar days to cover those bars
        5. Return requirements
    """
    from app.indicators import IndicatorConfig  # Import here to avoid circular dependency
    from datetime import date, datetime, timedelta
    
    interval = indicator_config.interval
    indicator_key = indicator_config.make_key()
    
    # Get TimeManager from SystemManager
    time_manager = system_manager.get_time_manager()
    
    # Get reference date (current date if not specified)
    if from_date is None:
        current_time = time_manager.get_current_time()
        from_date = current_time.date()
    
    # Parse the indicator's interval
    interval_info = parse_interval(interval)
    
    # Determine required intervals
    required_intervals = [interval]  # Always need the indicator's interval
    
    # Check if we need a base interval too
    if not interval_info.is_base:
        base_interval = determine_required_base(interval)
        if base_interval and base_interval not in required_intervals:
            required_intervals.insert(0, base_interval)  # Base comes first
    
    # Calculate bars needed
    warmup_bars = indicator_config.warmup_bars()
    historical_bars_needed = int(warmup_bars * warmup_multiplier)
    
    # Use TimeManager to calculate calendar days needed
    # This accounts for actual holidays, weekends, early closes
    historical_days = _estimate_calendar_days_via_timemanager(
        time_manager=time_manager,
        interval_info=interval_info,
        bars_needed=historical_bars_needed,
        from_date=from_date,
        exchange=exchange
    )
    
    # Generate reason
    reason = (
        f"{indicator_config.name.upper()}({indicator_config.period}) on {interval} "
        f"needs {warmup_bars} bars for warmup, "
        f"requesting {historical_bars_needed} bars ({warmup_multiplier}x buffer) "
        f"= ~{historical_days} calendar days"
    )
    
    return IndicatorRequirements(
        indicator_key=indicator_key,
        required_intervals=required_intervals,
        historical_bars=historical_bars_needed,
        historical_days=historical_days,
        reason=reason
    )


def _estimate_calendar_days_via_timemanager(
    time_manager,
    interval_info: IntervalInfo,
    bars_needed: int,
    from_date,
    exchange: str
) -> int:
    """Calculate calendar days needed to get N bars using TimeManager.
    
    **USES TIMEMANAGER**: All date calculations use TimeManager APIs to
    account for actual holidays, weekends, early closes, and market hours.
    
    This is the CORRECT way to estimate - no hardcoded assumptions!
    
    Creates its own database session as needed for TimeManager queries.
    
    Args:
        time_manager: TimeManager instance
        interval_info: Parsed interval information
        bars_needed: Number of bars needed
        from_date: Reference date to calculate back from
        exchange: Exchange identifier
        
    Returns:
        Calendar days needed (exact, not estimated)
        
    Algorithm:
        1. For daily/weekly: Walk back N trading days/weeks using TimeManager
        2. For intraday: Calculate trading days needed, then walk back
        3. Return actual calendar days between start and end dates
    """
    from datetime import datetime, timedelta
    from app.models.database import SessionLocal
    
    # Create database session for TimeManager queries
    with SessionLocal() as session:
        # For daily intervals: Walk back N trading days
        if interval_info.type == IntervalType.DAY:
            # How many trading days do we need?
            trading_days_needed = bars_needed * (interval_info.seconds // 86400)
            
            # Walk back using TimeManager (accounts for holidays/weekends)
            start_date = time_manager.get_previous_trading_date(
                session=session,
                from_date=from_date,
                n=int(trading_days_needed),
                exchange=exchange
            )
            
            if start_date is None:
                # Fallback if we can't walk back (shouldn't happen)
                logger.warning(f"Could not walk back {trading_days_needed} trading days from {from_date}")
                return int(trading_days_needed * 1.5)  # Conservative estimate
            
            # Calculate actual calendar days
            calendar_days = (from_date - start_date).days
            return max(1, calendar_days)
        
        # For weekly intervals: Walk back N trading weeks
        elif interval_info.type == IntervalType.WEEK:
            # How many trading weeks do we need?
            trading_weeks_needed = bars_needed * (interval_info.seconds // 604800)
            trading_days_needed = int(trading_weeks_needed * 5)  # ~5 trading days per week
            
            # Walk back using TimeManager
            start_date = time_manager.get_previous_trading_date(
                session=session,
                from_date=from_date,
                n=trading_days_needed,
                exchange=exchange
            )
            
            if start_date is None:
                logger.warning(f"Could not walk back {trading_days_needed} trading days from {from_date}")
                return int(trading_weeks_needed * 7)
            
            calendar_days = (from_date - start_date).days
            return max(7, calendar_days)
        
        # For intraday intervals: Calculate trading days needed based on market hours
        elif interval_info.type in [IntervalType.SECOND, IntervalType.MINUTE]:
            # Get trading session to know actual market hours
            trading_session = time_manager.get_trading_session(
                session=session,
                date=from_date,
                exchange=exchange
            )
            
            if trading_session and trading_session.is_trading_day:
                # Calculate seconds per trading day
                open_time = trading_session.regular_open
                close_time = trading_session.regular_close
                hours = (datetime.combine(from_date, close_time) - 
                        datetime.combine(from_date, open_time)).seconds
                seconds_per_trading_day = hours
                
                # How many bars fit in one trading day?
                bars_per_day = seconds_per_trading_day / interval_info.seconds
                
                # How many trading days?
                trading_days_needed = bars_needed / bars_per_day
                
                # Round up and add buffer
                trading_days_needed = int(trading_days_needed) + 1
            else:
                # Fallback: assume 6.5 hour trading day = 390 minutes
                trading_day_seconds = 390 * 60
                bars_per_day = trading_day_seconds / interval_info.seconds
                trading_days_needed = int(bars_needed / bars_per_day) + 1
            
            # Walk back using TimeManager
            start_date = time_manager.get_previous_trading_date(
                session=session,
                from_date=from_date,
                n=trading_days_needed,
                exchange=exchange
            )
            
            if start_date is None:
                logger.warning(f"Could not walk back {trading_days_needed} trading days from {from_date}")
                return max(1, int(trading_days_needed * 1.5))
            
            calendar_days = (from_date - start_date).days
            return max(1, calendar_days)
            
        else:
            # Fallback for unknown types
            logger.warning(f"Unknown interval type: {interval_info.type}")
            return max(1, bars_needed)
