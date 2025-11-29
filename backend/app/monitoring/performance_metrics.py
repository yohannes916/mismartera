"""
PerformanceMetrics - Monitoring and instrumentation for session performance.

This module provides performance tracking for critical path components:
1. Analysis Engine - Time per analysis cycle
2. Data Processor - Time per data item
3. Data Loading - Initial and subsequent load times
4. Session Lifecycle - Gap times and active session durations
5. Backtest Summary - Total time and average per trading day

Key Design Principles:
1. Running statistics: Track min/max/avg without storing all values
2. Minimal overhead: Use time.perf_counter() for high-resolution timing
3. Per-session reset: Clear metrics at session start (except backtest summary)
4. Report formatting: Human-readable output matching architecture specification

Reference: SESSION_ARCHITECTURE.md - Section 6: Performance Monitoring
"""

import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricStats:
    """Statistics for a metric using running calculations."""
    min_value: float = float('inf')
    max_value: float = 0.0
    sum_value: float = 0.0
    count: int = 0
    
    @property
    def avg_value(self) -> float:
        """Calculate average."""
        return self.sum_value / self.count if self.count > 0 else 0.0
    
    def record(self, value: float) -> None:
        """Record a new value (running statistics).
        
        Args:
            value: Value to record (typically in seconds)
        """
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.sum_value += value
        self.count += 1
    
    def reset(self) -> None:
        """Reset all statistics."""
        self.min_value = float('inf')
        self.max_value = 0.0
        self.sum_value = 0.0
        self.count = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            'min': self.min_value if self.min_value != float('inf') else 0.0,
            'max': self.max_value,
            'avg': self.avg_value,
            'count': self.count
        }


class MetricTracker:
    """Tracks min/max/avg for a single metric using running statistics.
    
    Performance: O(1) recording, no need to store all values.
    """
    
    def __init__(self, name: str):
        """Initialize metric tracker.
        
        Args:
            name: Metric name for identification
        """
        self.name = name
        self.stats = MetricStats()
    
    def record(self, value: float) -> None:
        """Record a new value.
        
        Args:
            value: Value to record (typically in seconds)
        """
        self.stats.record(value)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics.
        
        Returns:
            Dictionary with min, max, avg, count
        """
        return self.stats.to_dict()
    
    def reset(self) -> None:
        """Reset all statistics."""
        self.stats.reset()
        logger.debug(f"MetricTracker '{self.name}' reset")
    
    def __repr__(self) -> str:
        """String representation."""
        stats = self.stats.to_dict()
        return (
            f"MetricTracker(name='{self.name}', "
            f"count={stats['count']}, "
            f"avg={stats['avg']:.6f}s)"
        )


class PerformanceMetrics:
    """Central performance monitoring for session management.
    
    Architecture:
        - Tracks critical path components (analysis engine, data processor)
        - Tracks data loading times (initial vs subsequent)
        - Tracks session lifecycle (gaps, active durations)
        - Tracks backtest summary (total time, trading days)
    
    Usage:
        # Create once at system start
        metrics = PerformanceMetrics()
        
        # Record timing
        start = metrics.start_timer()
        # ... do work ...
        metrics.record_analysis_engine(start)
        
        # Get report
        report = metrics.format_report('session')  # or 'backtest'
    
    Thread-safety: Not thread-safe - should be accessed by single thread
                   (typically session_coordinator)
    """
    
    def __init__(self):
        """Initialize performance metrics."""
        # Per-session metrics (reset at session start)
        self.analysis_engine = MetricTracker('analysis_engine')
        self.data_processor = MetricTracker('data_processor')
        self.session_gap = MetricTracker('session_gap')
        self.session_duration = MetricTracker('session_duration')
        self.data_loading_subsequent = MetricTracker('data_loading_subsequent')
        
        # Initial load (single value, not reset per session)
        self.data_loading_initial: Optional[float] = None
        
        # Backtest summary (persists across sessions)
        self.backtest_start_time: Optional[float] = None
        self.backtest_end_time: Optional[float] = None
        self.backtest_trading_days: int = 0
        
        logger.info("PerformanceMetrics initialized")
    
    # =========================================================================
    # Timer Utilities
    # =========================================================================
    
    @staticmethod
    def start_timer() -> float:
        """Start a timer for measuring duration.
        
        Returns:
            Start time (use with record_* methods)
        
        Example:
            start = metrics.start_timer()
            # ... do work ...
            metrics.record_analysis_engine(start)
        """
        return time.perf_counter()
    
    @staticmethod
    def elapsed_time(start_time: float) -> float:
        """Calculate elapsed time since start.
        
        Args:
            start_time: Start time from start_timer()
        
        Returns:
            Elapsed time in seconds
        """
        return time.perf_counter() - start_time
    
    # =========================================================================
    # Recording Methods
    # =========================================================================
    
    def record_analysis_engine(self, start_time: float) -> None:
        """Record analysis engine performance.
        
        Measures: Time from notification sent to ready signal received
        Measured by: data_processor thread
        
        Args:
            start_time: Start time from start_timer()
        """
        duration = self.elapsed_time(start_time)
        self.analysis_engine.record(duration)
    
    def record_data_processor(self, start_time: float) -> None:
        """Record data processor performance.
        
        Measures: Time from data delivery to ready signal received
        Measured by: session_coordinator thread
        
        Args:
            start_time: Start time from start_timer()
        """
        duration = self.elapsed_time(start_time)
        self.data_processor.record(duration)
    
    def record_initial_load(self, duration: float) -> None:
        """Record initial data load time.
        
        Measures: Time to load ALL historical data at backtest start
        Called: Once at first session
        
        Args:
            duration: Load duration in seconds
        """
        self.data_loading_initial = duration
        logger.info(f"Initial data load: {duration:.3f}s")
    
    def record_subsequent_load(self, start_time: float) -> None:
        """Record subsequent data load time.
        
        Measures: Time to load data between sessions
        Called: Every session after first
        
        Args:
            start_time: Start time from start_timer()
        """
        duration = self.elapsed_time(start_time)
        self.data_loading_subsequent.record(duration)
    
    def record_session_gap(self, start_time: float) -> None:
        """Record session gap time.
        
        Measures: Time from session inactive to active again
        Includes: Historical update + indicators + quality + queue load
        
        Args:
            start_time: Start time from start_timer()
        """
        duration = self.elapsed_time(start_time)
        self.session_gap.record(duration)
    
    def record_session_duration(self, start_time: float) -> None:
        """Record active session duration.
        
        Measures: Market open to close time
        Expected: ~6.5 hours for regular trading day
        
        Args:
            start_time: Start time from start_timer()
        """
        duration = self.elapsed_time(start_time)
        self.session_duration.record(duration)
    
    def increment_trading_days(self) -> None:
        """Increment trading days counter."""
        self.backtest_trading_days += 1
    
    def start_backtest(self) -> None:
        """Mark backtest start time."""
        self.backtest_start_time = time.perf_counter()
        self.backtest_trading_days = 0
        logger.info("Backtest timer started")
    
    def end_backtest(self) -> None:
        """Mark backtest end time."""
        self.backtest_end_time = time.perf_counter()
        logger.info("Backtest timer stopped")
    
    # =========================================================================
    # Report Formatting
    # =========================================================================
    
    def format_report(self, report_type: str = 'session') -> str:
        """Format performance report.
        
        Args:
            report_type: 'session' or 'backtest'
        
        Returns:
            Formatted report string
        
        Format matches SESSION_ARCHITECTURE.md specification.
        """
        if report_type == 'session':
            return self._format_session_report()
        elif report_type == 'backtest':
            return self._format_backtest_report()
        else:
            raise ValueError(f"Invalid report_type '{report_type}'. Must be 'session' or 'backtest'")
    
    def _format_session_report(self) -> str:
        """Format per-session performance report."""
        lines = []
        lines.append("Performance Metrics (Session):")
        lines.append("=" * 50)
        
        # Analysis Engine
        ae_stats = self.analysis_engine.get_stats()
        if ae_stats['count'] > 0:
            lines.append("Analysis Engine:")
            lines.append(f"  - Cycles: {ae_stats['count']:,}")
            lines.append(
                f"  - Min: {ae_stats['min']*1000:.2f} ms | "
                f"Max: {ae_stats['max']*1000:.2f} ms | "
                f"Avg: {ae_stats['avg']*1000:.2f} ms"
            )
        
        # Data Processor
        dp_stats = self.data_processor.get_stats()
        if dp_stats['count'] > 0:
            lines.append("")
            lines.append("Data Processor:")
            lines.append(f"  - Items: {dp_stats['count']:,}")
            lines.append(
                f"  - Min: {dp_stats['min']*1000:.2f} ms | "
                f"Max: {dp_stats['max']*1000:.2f} ms | "
                f"Avg: {dp_stats['avg']*1000:.2f} ms"
            )
        
        # Session Gap
        gap_stats = self.session_gap.get_stats()
        if gap_stats['count'] > 0:
            lines.append("")
            lines.append("Session Gap:")
            lines.append(f"  - Sessions: {gap_stats['count']}")
            lines.append(
                f"  - Avg: {gap_stats['avg']:.2f} s | "
                f"Min: {gap_stats['min']:.2f} s | "
                f"Max: {gap_stats['max']:.2f} s"
            )
        
        # Session Duration
        dur_stats = self.session_duration.get_stats()
        if dur_stats['count'] > 0:
            lines.append("")
            lines.append("Session Duration:")
            lines.append(f"  - Sessions: {dur_stats['count']}")
            lines.append(
                f"  - Avg: {dur_stats['avg']/3600:.2f} hrs | "
                f"Min: {dur_stats['min']/3600:.2f} hrs | "
                f"Max: {dur_stats['max']/3600:.2f} hrs"
            )
        
        lines.append("=" * 50)
        return "\n".join(lines)
    
    def _format_backtest_report(self) -> str:
        """Format backtest summary report."""
        lines = []
        lines.append("Performance Metrics Summary:")
        lines.append("=" * 50)
        
        # Analysis Engine
        ae_stats = self.analysis_engine.get_stats()
        if ae_stats['count'] > 0:
            lines.append("Analysis Engine:")
            lines.append(f"  - Cycles: {ae_stats['count']:,}")
            lines.append(
                f"  - Min: {ae_stats['min']*1000:.2f} ms | "
                f"Max: {ae_stats['max']*1000:.2f} ms | "
                f"Avg: {ae_stats['avg']*1000:.2f} ms"
            )
        
        # Data Processor
        dp_stats = self.data_processor.get_stats()
        if dp_stats['count'] > 0:
            lines.append("")
            lines.append("Data Processor:")
            lines.append(f"  - Items: {dp_stats['count']:,}")
            lines.append(
                f"  - Min: {dp_stats['min']*1000:.2f} ms | "
                f"Max: {dp_stats['max']*1000:.2f} ms | "
                f"Avg: {dp_stats['avg']*1000:.2f} ms"
            )
        
        # Data Loading
        lines.append("")
        lines.append("Data Loading (All Symbols):")
        if self.data_loading_initial is not None:
            lines.append(f"  - Initial Load: {self.data_loading_initial:.2f} s")
        
        sub_stats = self.data_loading_subsequent.get_stats()
        if sub_stats['count'] > 0:
            lines.append(
                f"  - Subsequent Load: "
                f"Avg: {sub_stats['avg']:.2f} s | "
                f"Min: {sub_stats['min']:.2f} s | "
                f"Max: {sub_stats['max']:.2f} s"
            )
        
        # Session Lifecycle
        gap_stats = self.session_gap.get_stats()
        dur_stats = self.session_duration.get_stats()
        if gap_stats['count'] > 0 or dur_stats['count'] > 0:
            lines.append("")
            lines.append("Session Lifecycle:")
            lines.append(f"  - Sessions: {self.backtest_trading_days}")
            
            if gap_stats['count'] > 0:
                lines.append(
                    f"  - Avg Gap: {gap_stats['avg']:.2f} s | "
                    f"Min: {gap_stats['min']:.2f} s | "
                    f"Max: {gap_stats['max']:.2f} s"
                )
            
            if dur_stats['count'] > 0:
                lines.append(
                    f"  - Avg Duration: {dur_stats['avg']/3600:.2f} hrs | "
                    f"Min: {dur_stats['min']/3600:.2f} hrs | "
                    f"Max: {dur_stats['max']/3600:.2f} hrs"
                )
        
        # Backtest Summary
        if self.backtest_start_time is not None and self.backtest_end_time is not None:
            total_time = self.backtest_end_time - self.backtest_start_time
            avg_per_day = total_time / self.backtest_trading_days if self.backtest_trading_days > 0 else 0.0
            
            lines.append("")
            lines.append("Backtest Summary:")
            lines.append(f"  - Total Time: {total_time:.2f} s")
            lines.append(f"  - Trading Days: {self.backtest_trading_days}")
            lines.append(f"  - Avg per Day: {avg_per_day:.2f} s")
        
        lines.append("=" * 50)
        return "\n".join(lines)
    
    # =========================================================================
    # Reset Operations
    # =========================================================================
    
    def reset_session_metrics(self) -> None:
        """Reset per-session metrics.
        
        Called at session start. Does NOT reset backtest summary.
        """
        self.analysis_engine.reset()
        self.data_processor.reset()
        # Note: session_gap and session_duration are NOT reset (persist across sessions)
        # Note: data_loading_subsequent is NOT reset (persist across sessions)
        logger.debug("Session metrics reset")
    
    def reset_all(self) -> None:
        """Reset all metrics (for new backtest)."""
        self.analysis_engine.reset()
        self.data_processor.reset()
        self.session_gap.reset()
        self.session_duration.reset()
        self.data_loading_subsequent.reset()
        self.data_loading_initial = None
        self.backtest_start_time = None
        self.backtest_end_time = None
        self.backtest_trading_days = 0
        logger.info("All metrics reset")
    
    # =========================================================================
    # Summary Access
    # =========================================================================
    
    def get_backtest_summary(self) -> Dict[str, Any]:
        """Get backtest summary statistics.
        
        Returns:
            Dictionary with summary stats
        """
        total_time = None
        avg_per_day = None
        
        if self.backtest_start_time is not None and self.backtest_end_time is not None:
            total_time = self.backtest_end_time - self.backtest_start_time
            avg_per_day = total_time / self.backtest_trading_days if self.backtest_trading_days > 0 else None
        
        return {
            'total_time': total_time,
            'trading_days': self.backtest_trading_days,
            'avg_per_day': avg_per_day,
            'initial_load': self.data_loading_initial,
            'subsequent_load': self.data_loading_subsequent.get_stats(),
            'analysis_engine': self.analysis_engine.get_stats(),
            'data_processor': self.data_processor.get_stats(),
            'session_gap': self.session_gap.get_stats(),
            'session_duration': self.session_duration.get_stats(),
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"PerformanceMetrics("
            f"trading_days={self.backtest_trading_days}, "
            f"analysis_cycles={self.analysis_engine.stats.count}, "
            f"data_items={self.data_processor.stats.count}"
            f")"
        )
