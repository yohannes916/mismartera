"""Unit Tests for BarIntervalData

Tests the BarIntervalData structure used to store bars for each interval.
"""
import pytest
from collections import deque
from datetime import datetime
from app.managers.data_manager.session_data import BarIntervalData, BarData


class TestBarIntervalDataCreation:
    """Test creating BarIntervalData instances."""
    
    def test_create_base_interval(self):
        """Test creating base interval (not derived)."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        assert bar_data.derived is False
        assert bar_data.base is None
        assert len(bar_data.data) == 0
        assert bar_data.quality == 0.0
        assert bar_data.updated is False
    
    def test_create_derived_interval(self):
        """Test creating derived interval (from base)."""
        bar_data = BarIntervalData(
            derived=True,
            base="1m",
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        assert bar_data.derived is True
        assert bar_data.base == "1m"
    
    def test_create_with_data(self):
        """Test creating with existing bars."""
        bars = deque([
            BarData(symbol="AAPL", 
                timestamp=datetime(2025, 1, 2, 9, 30),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000
            )
        ])
        
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=bars,
            quality=1.0,
            gaps=[],
            updated=True
        )
        
        assert len(bar_data.data) == 1
        assert bar_data.quality == 1.0
        assert bar_data.updated is True


class TestBarIntervalDataOperations:
    """Test operations on BarIntervalData."""
    
    def test_add_bar_to_interval(self):
        """Test adding a bar to interval."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        # Add bar
        new_bar = BarData(symbol="AAPL", 
            timestamp=datetime(2025, 1, 2, 9, 30),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1000
        )
        bar_data.data.append(new_bar)
        bar_data.updated = True
        
        assert len(bar_data.data) == 1
        assert bar_data.data[0].close == 100.5
        assert bar_data.updated is True
    
    def test_deque_maxlen_behavior(self):
        """Test deque with maxlen maintains size."""
        # Create with maxlen
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(maxlen=3),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        # Add 5 bars (only last 3 should remain)
        for i in range(5):
            bar_data.data.append(BarData(symbol="AAPL", 
                timestamp=datetime(2025, 1, 2, 9, 30 + i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.5 + i,
                close=100.5 + i,
                volume=1000
            ))
        
        # Should only have last 3
        assert len(bar_data.data) == 3
        assert bar_data.data[0].open == 102.0  # 3rd bar
        assert bar_data.data[-1].open == 104.0  # 5th bar


class TestBarIntervalDataQuality:
    """Test quality tracking in BarIntervalData."""
    
    def test_quality_perfect(self):
        """Test quality for perfect data (no gaps)."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=1.0,
            gaps=[],
            updated=False
        )
        
        assert bar_data.quality == 1.0
        assert len(bar_data.gaps) == 0
    
    def test_quality_with_gaps(self):
        """Test quality with some gaps."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.95,
            gaps=[(datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 10, 5))],
            updated=False
        )
        
        assert bar_data.quality == 0.95
        assert len(bar_data.gaps) == 1
    
    def test_quality_zero_no_data(self):
        """Test quality is zero with no data."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        assert bar_data.quality == 0.0
        assert len(bar_data.data) == 0


class TestBarIntervalDataFlags:
    """Test flags in BarIntervalData."""
    
    def test_updated_flag_lifecycle(self):
        """Test updated flag lifecycle."""
        bar_data = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        # Initially not updated
        assert bar_data.updated is False
        
        # Add bar and mark updated
        bar_data.data.append(BarData(symbol="AAPL", 
            timestamp=datetime(2025, 1, 2, 9, 30),
            open=100.0, high=101.0, low=99.5, close=100.5, volume=1000
        ))
        bar_data.updated = True
        
        assert bar_data.updated is True
        
        # Reset flag after processing
        bar_data.updated = False
        
        assert bar_data.updated is False
    
    def test_derived_flag_immutable(self):
        """Test derived flag indicates interval type."""
        # Base interval
        base = BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False)
        assert base.derived is False
        
        # Derived interval
        derived = BarIntervalData(derived=True, base="1m", data=deque(), quality=0.0, gaps=[], updated=False)
        assert derived.derived is True


class TestDerivedIntervalRelationships:
    """Test relationships between base and derived intervals."""
    
    def test_derived_references_base(self):
        """Test derived interval references its base."""
        derived_5m = BarIntervalData(
            derived=True,
            base="1m",
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        assert derived_5m.base == "1m"
        assert derived_5m.derived is True
    
    def test_base_has_no_reference(self):
        """Test base interval has no base reference."""
        base_1m = BarIntervalData(
            derived=False,
            base=None,
            data=deque(),
            quality=0.0,
            gaps=[],
            updated=False
        )
        
        assert base_1m.base is None
        assert base_1m.derived is False
    
    def test_multiple_derived_from_same_base(self):
        """Test multiple derived intervals can share same base."""
        derived_5m = BarIntervalData(derived=True, base="1m", data=deque(), quality=0.0, gaps=[], updated=False)
        derived_15m = BarIntervalData(derived=True, base="1m", data=deque(), quality=0.0, gaps=[], updated=False)
        
        assert derived_5m.base == "1m"
        assert derived_15m.base == "1m"
        assert derived_5m.base == derived_15m.base
