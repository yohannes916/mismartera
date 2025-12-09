"""Aggregation Mode Detection

Automatically determines the appropriate aggregation mode based on
source and target intervals.
"""
from app.managers.data_manager.bar_aggregation.modes import AggregationMode
from app.threads.quality.requirement_analyzer import parse_interval, IntervalType
from app.logger import logger


def detect_aggregation_mode(source_interval: str, target_interval: str) -> AggregationMode:
    """Auto-detect which aggregation mode to use.
    
    Rules:
    - tick → any = TIME_WINDOW (round timestamps to windows)
    - any → daily/weekly = CALENDAR (respect trading calendar)
    - same_unit → same_unit_multiple = FIXED_CHUNK (e.g., 1m→5m, 1s→60s)
    
    Args:
        source_interval: Source interval ("tick", "1s", "1m", "5m", "1d")
        target_interval: Target interval ("1s", "1m", "5m", "1d", "1w")
    
    Returns:
        AggregationMode enum
    
    Raises:
        ValueError: If conversion is invalid or unsupported
    
    Examples:
        >>> detect_aggregation_mode("tick", "1s")
        AggregationMode.TIME_WINDOW
        
        >>> detect_aggregation_mode("1m", "5m")
        AggregationMode.FIXED_CHUNK
        
        >>> detect_aggregation_mode("1m", "1d")
        AggregationMode.CALENDAR
        
        >>> detect_aggregation_mode("1d", "1w")
        AggregationMode.CALENDAR
    """
    # Special case: ticks always use TIME_WINDOW
    if source_interval.lower() in ["tick", "ticks"]:
        logger.debug(f"Mode: TIME_WINDOW (source is ticks)")
        return AggregationMode.TIME_WINDOW
    
    # Parse intervals (parse_interval will reject hourly formats like "1h")
    try:
        source_info = parse_interval(source_interval)
        target_info = parse_interval(target_interval)
    except ValueError as e:
        raise ValueError(
            f"Invalid interval format: {e}\n"
            f"Supported: seconds (1s, 5s), minutes (1m, 5m, 60m), "
            f"days (1d), weeks (1w). NO hourly (use 60m instead of 1h)."
        )
    
    # Validate: source must be smaller than target
    if source_info.seconds >= target_info.seconds:
        raise ValueError(
            f"Cannot aggregate {source_interval} to {target_interval}: "
            f"Target interval must be larger than source. "
            f"(Source: {source_info.seconds}s, Target: {target_info.seconds}s)"
        )
    
    # Rule 1: Target is daily or weekly → CALENDAR mode
    if target_info.type in [IntervalType.DAY, IntervalType.WEEK]:
        logger.debug(
            f"Mode: CALENDAR ({source_interval} → {target_interval}, "
            f"target is {target_info.type.value})"
        )
        return AggregationMode.CALENDAR
    
    # Rule 2: Same unit type → FIXED_CHUNK mode
    # (1s→5s, 1m→5m, 5m→15m, etc.)
    if source_info.type == target_info.type:
        # Validate target is a multiple of source
        if target_info.seconds % source_info.seconds != 0:
            raise ValueError(
                f"Target interval ({target_interval}) must be an exact multiple "
                f"of source interval ({source_interval}). "
                f"Example: 1m→5m (5x), 1s→30s (30x)"
            )
        
        logger.debug(
            f"Mode: FIXED_CHUNK ({source_interval} → {target_interval}, "
            f"same unit type, {target_info.seconds // source_info.seconds}x multiple)"
        )
        return AggregationMode.FIXED_CHUNK
    
    # Rule 3: Different unit types (e.g., seconds→minutes, minutes→days)
    # Use FIXED_CHUNK if target is exact multiple of source
    if target_info.seconds % source_info.seconds == 0:
        chunk_size = target_info.seconds // source_info.seconds
        logger.debug(
            f"Mode: FIXED_CHUNK ({source_interval} → {target_interval}, "
            f"cross-unit, {chunk_size}x multiple)"
        )
        return AggregationMode.FIXED_CHUNK
    
    # Unsupported conversion
    raise ValueError(
        f"Unsupported aggregation: {source_interval} → {target_interval}. "
        f"Target must be an exact multiple of source, or target must be daily/weekly. "
        f"Examples: 1s→1m (60x), 1m→5m (5x), 1m→1d (calendar), 1d→1w (calendar)"
    )


def validate_aggregation_params(
    source_interval: str,
    target_interval: str,
    available_intervals: list[str] = None
) -> None:
    """Validate aggregation parameters before execution.
    
    Args:
        source_interval: Source interval
        target_interval: Target interval
        available_intervals: List of intervals available in storage (optional)
    
    Raises:
        ValueError: If parameters are invalid
    """
    # Detect mode (this validates format and compatibility)
    mode = detect_aggregation_mode(source_interval, target_interval)
    
    # Check if source interval exists in storage
    if available_intervals is not None:
        if source_interval not in available_intervals:
            raise ValueError(
                f"Source interval '{source_interval}' not found in storage. "
                f"Available intervals: {', '.join(sorted(available_intervals))}"
            )
    
    logger.info(
        f"Validation passed: {source_interval} → {target_interval} "
        f"using {mode.value} mode"
    )


def get_supported_targets(source_interval: str) -> list[str]:
    """Get list of valid target intervals for a given source.
    
    Args:
        source_interval: Source interval
    
    Returns:
        List of valid target intervals
    
    Examples:
        >>> get_supported_targets("1s")
        ['1m', '5m', '15m', '30m', '60m', '1d']
        
        >>> get_supported_targets("1m")
        ['5m', '15m', '30m', '60m', '1d']
        
        >>> get_supported_targets("1d")
        ['1w']
    """
    # Special case: ticks
    if source_interval.lower() in ["tick", "ticks"]:
        return ["1s", "1m", "5m", "15m", "30m", "60m", "1d"]
    
    try:
        source_info = parse_interval(source_interval)
    except ValueError:
        return []
    
    targets = []
    
    # Common intraday targets
    common_targets = {
        "1s": ["1m", "5m", "15m", "30m", "60m", "1d"],
        "1m": ["5m", "15m", "30m", "60m", "1d"],
        "5m": ["15m", "30m", "60m", "1d"],
        "15m": ["30m", "60m", "1d"],
        "30m": ["60m", "1d"],
        "60m": ["1d"],
        "1d": ["1w"],
    }
    
    if source_interval in common_targets:
        return common_targets[source_interval]
    
    # For custom intervals, calculate valid targets
    if source_info.type == IntervalType.SECOND:
        # Can aggregate to minutes and daily
        targets = ["1m", "5m", "15m", "30m", "60m", "1d"]
    elif source_info.type == IntervalType.MINUTE:
        # Can aggregate to larger minutes and daily
        targets = ["5m", "15m", "30m", "60m", "1d"]
    elif source_info.type == IntervalType.DAY:
        # Can only aggregate to weekly
        targets = ["1w"]
    elif source_info.type == IntervalType.WEEK:
        # No aggregation from weekly (yet)
        targets = []
    
    # Filter to only targets larger than source
    valid_targets = []
    for target in targets:
        try:
            target_info = parse_interval(target)
            if target_info.seconds > source_info.seconds:
                valid_targets.append(target)
        except ValueError:
            continue
    
    return valid_targets
