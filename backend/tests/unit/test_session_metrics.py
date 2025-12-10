"""Unit Tests for SessionMetrics

Tests the SessionMetrics dataclass - volume, high, low, last_update only.
"""
import pytest
from datetime import datetime
from app.managers.data_manager.session_data import SessionMetrics


class TestSessionMetricsBasics:
    """Test SessionMetrics basic creation and updates."""
    
    def test_create_empty(self):
        """Test creating empty metrics."""
        m = SessionMetrics()
        assert m.volume == 0
        assert m.high is None
        assert m.low is None
    
    def test_with_values(self):
        """Test creating with values."""
        m = SessionMetrics(volume=1000, high=105.0, low=95.0)
        assert m.volume == 1000
        assert m.high == 105.0
        assert m.low == 95.0
    
    def test_volume_accumulates(self):
        """Test volume accumulation."""
        m = SessionMetrics()
        m.volume += 500
        m.volume += 300
        assert m.volume == 800
    
    def test_high_low_relationship(self):
        """Test high >= low."""
        m = SessionMetrics(high=105.0, low=95.0)
        assert m.high >= m.low
