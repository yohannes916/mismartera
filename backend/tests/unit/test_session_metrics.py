"""Unit Tests for SessionMetrics

Tests the SessionMetrics dataclass that tracks basic OHLCV aggregations.
Note: SessionMetrics only has volume, high, low, and last_update.
"""
import pytest
from datetime import datetime
from app.managers.data_manager.session_data import SessionMetrics


class TestSessionMetricsCreation:
    """Test creating SessionMetrics instances."""
    
    def test_create_empty_metrics(self):
        """Test creating empty session metrics."""
        metrics = SessionMetrics()
        
        assert metrics.volume == 0
        assert metrics.high is None
        assert metrics.low is None
        assert metrics.last_update is None
    
    def test_create_with_values(self):
        """Test creating metrics with initial values."""
        now = datetime.now()
        metrics = SessionMetrics(
            volume=10000,
            high=105.0,
            low=95.0,
            last_update=now
        )
        
        assert metrics.volume == 10000
        assert metrics.high == 105.0
        assert metrics.low == 95.0
        assert metrics.last_update == now


class TestSessionMetricsUpdates:
    """Test updating session metrics."""
    
    def test_update_volume(self):
        """Test updating volume."""
        metrics = SessionMetrics(volume=5000)
        
        # Accumulate more volume
        metrics.volume += 3000
        assert metrics.volume == 8000
    
    def test_update_high(self):
        """Test updating high."""
        metrics = SessionMetrics(high=100.0)
        
        # New higher high
        metrics.high = max(metrics.high, 110.0)
        assert metrics.high == 110.0
    
    def test_update_low(self):
        """Test updating low."""
        metrics = SessionMetrics(low=100.0)
        
        # New lower low  
        metrics.low = min(metrics.low, 90.0)
        assert metrics.low == 90.0
    
    def test_update_last_update_timestamp(self):
        """Test updating last_update timestamp."""
        time1 = datetime(2025, 1, 2, 9, 30)
        metrics = SessionMetrics(last_update=time1)
        
        # Update to later time
        time2 = datetime(2025, 1, 2, 10, 0)
        metrics.last_update = time2
        
        assert metrics.last_update == time2
        assert metrics.last_update > time1


class TestSessionMetricsReset:
    """Test resetting session metrics."""
    
    def test_reset_to_empty(self):
        """Test resetting metrics to empty state."""
        metrics = SessionMetrics(
            volume=10000,
            high=105.0,
            low=95.0
        )
        
        assert metrics.volume == 10000
        
        # Reset by creating new instance
        metrics = SessionMetrics()
        
        assert metrics.volume == 0
        assert metrics.high is None
        assert metrics.low is None


class TestSessionMetricsPriceRelationships:
    """Test price relationship invariants."""
    
    def test_high_greater_than_low(self):
        """Test high is greater than or equal to low."""
        metrics = SessionMetrics(
            high=105.0,
            low=95.0
        )
        
        assert metrics.high >= metrics.low
    
    def test_single_price_level(self):
        """Test when high equals low."""
        metrics = SessionMetrics(
            high=100.0,
            low=100.0
        )
        
        assert metrics.high == metrics.low
    
    def test_high_low_none_initially(self):
        """Test high and low start as None."""
        metrics = SessionMetrics()
        
        assert metrics.high is None
        assert metrics.low is None


class TestSessionMetricsVolumeAccumulation:
    """Test volume accumulation patterns."""
    
    def test_volume_accumulates(self):
        """Test volume accumulates over time."""
        metrics = SessionMetrics()
        
        # Start at zero
        assert metrics.volume == 0
        
        # Add volume from bars
        metrics.volume += 1000
        metrics.volume += 2000
        metrics.volume += 3000
        
        assert metrics.volume == 6000
    
    def test_volume_never_negative(self):
        """Test volume should not be negative."""
        metrics = SessionMetrics(volume=5000)
        
        # Volume should always be >= 0
        assert metrics.volume >= 0
