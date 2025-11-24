"""Production Configuration Validation and Health Checks

Provides validation and health check utilities for production deployment.

Used to ensure system is properly configured and operating correctly.
"""
from typing import List, Dict, Any
from datetime import datetime

from app.config import settings
from app.logger import logger


def validate_production_config() -> List[str]:
    """Validate configuration for production use.
    
    Checks all critical settings and returns list of warnings/issues.
    
    Returns:
        List of warning messages (empty if all good)
    """
    issues = []
    
    # Phase 2: Data-Upkeep Thread
    if not settings.DATA_UPKEEP_ENABLED:
        issues.append("WARNING: DATA_UPKEEP_ENABLED is False - no automatic quality management")
    
    if settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS < 30:
        issues.append("WARNING: DATA_UPKEEP_CHECK_INTERVAL_SECONDS too short (< 30s)")
    
    if settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS > 300:
        issues.append("WARNING: DATA_UPKEEP_CHECK_INTERVAL_SECONDS too long (> 5min)")
    
    # Phase 3: Historical Bars
    if not settings.HISTORICAL_BARS_ENABLED:
        issues.append("INFO: HISTORICAL_BARS_ENABLED is False - no multi-day analysis")
    
    if settings.HISTORICAL_BARS_TRAILING_DAYS < 1:
        issues.append("WARNING: HISTORICAL_BARS_TRAILING_DAYS too low (< 1)")
    
    if settings.HISTORICAL_BARS_TRAILING_DAYS > 20:
        issues.append("WARNING: HISTORICAL_BARS_TRAILING_DAYS high (> 20) - check memory usage")
    
    # Phase 4: Prefetch
    if not settings.PREFETCH_ENABLED:
        issues.append("INFO: PREFETCH_ENABLED is False - slower session startup")
    
    if settings.PREFETCH_WINDOW_MINUTES < 30:
        issues.append("WARNING: PREFETCH_WINDOW_MINUTES too short for production (< 30min)")
    
    if settings.PREFETCH_CHECK_INTERVAL_MINUTES > 10:
        issues.append("WARNING: PREFETCH_CHECK_INTERVAL_MINUTES too long (> 10min)")
    
    # Phase 5: Session Boundaries
    if not settings.SESSION_AUTO_ROLL:
        issues.append("WARNING: SESSION_AUTO_ROLL is False - manual session management required")
    
    if settings.SESSION_TIMEOUT_SECONDS < 60:
        issues.append("WARNING: SESSION_TIMEOUT_SECONDS very short (< 60s)")
    
    if settings.SESSION_TIMEOUT_SECONDS > 600:
        issues.append("WARNING: SESSION_TIMEOUT_SECONDS very long (> 10min)")
    
    # Log results
    if issues:
        logger.warning(f"Configuration validation found {len(issues)} issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("✅ Configuration validation passed - all settings optimal")
    
    return issues


def get_system_health() -> Dict[str, Any]:
    """Get complete system health status.
    
    Returns comprehensive health information for monitoring.
    
    Returns:
        Dictionary with health status for all components
    """
    health = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "healthy",  # Will be updated if issues found
        "components": {}
    }
    
    try:
        # Check session_data
        from app.managers.data_manager.session_data import get_session_data
        session_data = get_session_data()
        
        health["components"]["session_data"] = {
            "status": "healthy",
            "active_symbols": len(session_data.get_active_symbols()),
            "current_session": str(session_data.current_session_date) if session_data.current_session_date else None,
            "session_ended": session_data.session_ended
        }
    except Exception as e:
        health["components"]["session_data"] = {
            "status": "error",
            "error": str(e)
        }
        health["overall_status"] = "degraded"
    
    # Configuration status
    health["components"]["configuration"] = {
        "status": "healthy",
        "data_upkeep_enabled": settings.DATA_UPKEEP_ENABLED,
        "historical_bars_enabled": settings.HISTORICAL_BARS_ENABLED,
        "prefetch_enabled": settings.PREFETCH_ENABLED,
        "auto_roll_enabled": settings.SESSION_AUTO_ROLL
    }
    
    # Validation issues
    issues = validate_production_config()
    if issues:
        health["components"]["configuration"]["issues"] = issues
        if any("WARNING" in issue for issue in issues):
            health["overall_status"] = "degraded"
    
    return health


def get_performance_metrics() -> Dict[str, Any]:
    """Get current performance metrics.
    
    Returns:
        Dictionary with performance statistics
    """
    metrics = {
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        from app.managers.data_manager.session_data import get_session_data
        session_data = get_session_data()
        
        # Get metrics for each active symbol
        symbols = session_data.get_active_symbols()
        symbol_metrics = {}
        
        for symbol in symbols[:10]:  # Limit to first 10 to avoid overhead
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                bar_count = loop.run_until_complete(
                    session_data.get_bar_count(symbol)
                )
                
                symbol_metrics[symbol] = {
                    "bar_count": bar_count
                }
                
                loop.close()
            except Exception as e:
                symbol_metrics[symbol] = {"error": str(e)}
        
        metrics["symbols"] = symbol_metrics
        metrics["total_active_symbols"] = len(symbols)
    
    except Exception as e:
        metrics["error"] = str(e)
    
    return metrics


def get_configuration_summary() -> Dict[str, Any]:
    """Get summary of all configuration settings.
    
    Returns:
        Dictionary with all relevant settings
    """
    return {
        # Phase 2: Data-Upkeep
        "data_upkeep": {
            "enabled": settings.DATA_UPKEEP_ENABLED,
            "check_interval": settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS,
            "retry_missing": settings.DATA_UPKEEP_RETRY_MISSING_BARS,
            "max_retries": settings.DATA_UPKEEP_MAX_RETRIES,
            "derived_intervals": settings.DATA_UPKEEP_DERIVED_INTERVALS,
            "auto_compute": settings.DATA_UPKEEP_AUTO_COMPUTE_DERIVED
        },
        
        # Phase 3: Historical Bars
        "historical_bars": {
            "enabled": settings.HISTORICAL_BARS_ENABLED,
            "trailing_days": settings.HISTORICAL_BARS_TRAILING_DAYS,
            "intervals": settings.HISTORICAL_BARS_INTERVALS,
            "auto_load": settings.HISTORICAL_BARS_AUTO_LOAD
        },
        
        # Phase 4: Prefetch
        "prefetch": {
            "enabled": settings.PREFETCH_ENABLED,
            "window_minutes": settings.PREFETCH_WINDOW_MINUTES,
            "check_interval": settings.PREFETCH_CHECK_INTERVAL_MINUTES,
            "auto_activate": settings.PREFETCH_AUTO_ACTIVATE
        },
        
        # Phase 5: Session Boundaries
        "session_boundaries": {
            "auto_roll": settings.SESSION_AUTO_ROLL,
            "timeout_seconds": settings.SESSION_TIMEOUT_SECONDS,
            "check_interval": settings.SESSION_BOUNDARY_CHECK_INTERVAL,
            "post_market_delay": settings.SESSION_POST_MARKET_ROLL_DELAY
        }
    }


def print_system_status() -> None:
    """Print comprehensive system status to console."""
    print("\n" + "="*60)
    print("STREAM COORDINATOR - SYSTEM STATUS")
    print("="*60)
    
    # Health check
    health = get_system_health()
    print(f"\n📊 Overall Status: {health['overall_status'].upper()}")
    print(f"🕒 Timestamp: {health['timestamp']}")
    
    # Components
    print("\n🔧 Components:")
    for component, status in health["components"].items():
        status_icon = "✅" if status.get("status") == "healthy" else "⚠️"
        print(f"  {status_icon} {component}: {status.get('status', 'unknown')}")
    
    # Configuration
    print("\n⚙️  Configuration:")
    config = get_configuration_summary()
    for phase, settings_dict in config.items():
        print(f"  {phase}:")
        for key, value in settings_dict.items():
            print(f"    • {key}: {value}")
    
    # Performance
    print("\n📈 Performance:")
    metrics = get_performance_metrics()
    print(f"  Active symbols: {metrics.get('total_active_symbols', 'N/A')}")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    # Validate configuration
    print("Validating production configuration...\n")
    issues = validate_production_config()
    
    if not issues:
        print("✅ All configuration checks passed!")
    else:
        print(f"⚠️  Found {len(issues)} configuration issues\n")
    
    # Print system status
    print_system_status()
