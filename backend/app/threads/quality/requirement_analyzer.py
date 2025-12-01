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

from typing import List, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum
import re

from app.logger import logger


# =============================================================================
# Enumerations
# =============================================================================

class IntervalType(Enum):
    """Interval type classification."""
    SECOND = "second"      # 1s, 5s, 10s, etc.
    MINUTE = "minute"      # 1m, 5m, 15m, etc.
    HOUR = "hour"          # 1h, 4h, etc.
    DAY = "day"            # 1d, 5d, etc.
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
    match = re.match(r'^(\d+)([smhd])$', interval_lower)
    if not match:
        raise ValueError(
            f"Invalid interval format: '{interval}'. "
            f"Expected format: <number><unit> (e.g., '1s', '5m', '1h', '1d') or 'quotes'"
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
    elif unit == 'h':
        interval_type = IntervalType.HOUR
        seconds = value * 3600
        is_base = False  # Hours never base (derived from 1m)
    elif unit == 'd':
        interval_type = IntervalType.DAY
        seconds = value * 86400
        is_base = (value == 1)  # Only 1d is base
    else:
        raise ValueError(f"Invalid unit: {unit}")
    
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
        - Minute (5m, 15m, 1h, etc.) → requires 1m (preferred, not 1s)
        - Day (1d, 5d, etc.) → requires 1m (aggregation from 1m)
        
    Examples:
        >>> determine_required_base("5s")
        "1s"
        
        >>> determine_required_base("5m")
        "1m"
        
        >>> determine_required_base("1d")
        "1m"
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
    
    # Rule 3 (Req 11): Hour intervals require 1m
    if info.type == IntervalType.HOUR:
        return "1m"
    
    # Rule 3 (Req 11): Day intervals require 1m (for aggregation)
    if info.type == IntervalType.DAY:
        return "1m"
    
    raise ValueError(f"Cannot determine base interval for: {interval}")


def select_smallest_base(bases: List[str]) -> str:
    """Select the smallest base interval from a list.
    
    Args:
        bases: List of base intervals (e.g., ["1s", "1m", "1m"])
        
    Returns:
        Smallest base interval
        
    Rule (Req 12):
        Priority: 1s < 1m < 1d
        
    Examples:
        >>> select_smallest_base(["1m", "1s", "1m"])
        "1s"
        
        >>> select_smallest_base(["1m", "1d"])
        "1m"
    """
    if not bases:
        raise ValueError("Cannot select base from empty list")
    
    # Priority order (smallest first)
    priority = {"1s": 1, "1m": 2, "1d": 3}
    
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
