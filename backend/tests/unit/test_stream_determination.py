"""Unit Tests for Stream Determination Logic

Tests the stream determination and gap filling logic including:
- Interval parsing
- Stream decisions (current day)
- Historical loading decisions
- Completeness checking
- Gap filling eligibility
- Quote handling
"""

import pytest
from datetime import datetime, date, time
from unittest.mock import Mock

from app.threads.quality.stream_determination import (
    IntervalType,
    IntervalInfo,
    StreamDecision,
    HistoricalDecision,
    AvailabilityInfo,
    parse_interval,
    determine_stream_interval,
    determine_historical_loading,
    get_generation_source_priority,
    can_fill_gap
)

from app.threads.quality.gap_filler import (
    GapFillResult,
    calculate_expected_bar_count,
    check_interval_completeness,
    aggregate_bars_to_interval
)

from app.models.trading import BarData


# =============================================================================
# Test Interval Parsing
# =============================================================================

class TestParseInterval:
    """Test interval string parsing."""
    
    def test_parse_1s(self):
        """Parse 1s interval."""
        info = parse_interval("1s")
        assert info.interval == "1s"
        assert info.type == IntervalType.SECOND
        assert info.seconds == 1
        assert info.can_be_stored == True  # DB supports 1s
        assert info.base_interval is None  # 1s is a base interval
    
    def test_parse_1m(self):
        """Parse 1m interval."""
        info = parse_interval("1m")
        assert info.interval == "1m"
        assert info.type == IntervalType.MINUTE
        assert info.seconds == 60
        assert info.can_be_stored == True  # DB supports 1m
        assert info.base_interval is None  # 1m is a base interval
    
    def test_parse_1d(self):
        """Parse 1d interval."""
        info = parse_interval("1d")
        assert info.interval == "1d"
        assert info.type == IntervalType.DAY
        assert info.seconds == 86400
        assert info.can_be_stored == True  # DB supports 1d
        assert info.base_interval is None  # 1d is a base interval
    
    def test_parse_5m(self):
        """Parse 5m interval (derived)."""
        info = parse_interval("5m")
        assert info.interval == "5m"
        assert info.type == IntervalType.MINUTE
        assert info.seconds == 300
        assert info.can_be_stored == False  # DB does NOT support 5m
        assert info.base_interval == "1m"  # Prefer 1m source
    
    def test_parse_5s(self):
        """Parse 5s interval (derived)."""
        info = parse_interval("5s")
        assert info.interval == "5s"
        assert info.type == IntervalType.SECOND
        assert info.seconds == 5
        assert info.can_be_stored == False  # DB does NOT support 5s
        assert info.base_interval == "1s"  # Only 1s source
    
    def test_parse_quotes(self):
        """Parse quotes."""
        info = parse_interval("quotes")
        assert info.interval == "quotes"
        assert info.type == IntervalType.QUOTE
        assert info.can_be_stored == True  # DB supports quotes
        assert info.base_interval is None
    
    def test_parse_ticks(self):
        """Parse ticks."""
        info = parse_interval("ticks")
        assert info.interval == "ticks"
        assert info.type == IntervalType.TICK
        assert info.can_be_stored == False  # DB does NOT support ticks
        assert info.base_interval is None
    
    def test_parse_invalid_format(self):
        """Invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("invalid")
    
    def test_parse_invalid_unit(self):
        """Invalid unit raises ValueError."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("5x")


# =============================================================================
# Test Stream Decisions
# =============================================================================

class TestStreamDecision:
    """Test current day stream determination."""
    
    def test_stream_smallest_1s_when_available(self):
        """Stream 1s when available (smallest)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=True,
            has_1d=True,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1s", "1m", "5m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1s"  # Smallest
        assert decision.generate_intervals == ["1m", "5m"]  # All others
        assert decision.error is None
    
    def test_stream_1m_when_no_1s(self):
        """Stream 1m when 1s not available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=True,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "5m", "15m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.generate_intervals == ["5m", "15m"]
        assert decision.error is None
    
    def test_stream_1d_when_only_daily(self):
        """Stream 1d when only daily data available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=False,
            has_1d=True,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1d", "5d"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1d"
        assert decision.generate_intervals == ["5d"]
        assert decision.error is None
    
    def test_generate_all_others(self):
        """All intervals except smallest are generated."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=True,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1s", "1m", "5m", "10m", "15m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1s"
        assert set(decision.generate_intervals) == {"1m", "5m", "10m", "15m"}
        assert decision.error is None
    
    def test_error_when_no_base_interval(self):
        """Error when no base interval available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["5m", "15m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval is None
        assert decision.error is not None
        assert "No base interval" in decision.error
    
    def test_quotes_streamed_in_live_mode(self):
        """Quotes streamed in live mode."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=True
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "quotes"],
            availability=availability,
            mode="live"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.stream_quotes == True  # Stream in live
        assert decision.generate_quotes == False
        assert decision.error is None
    
    def test_quotes_generated_in_backtest_mode(self):
        """Quotes generated in backtest mode."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=True
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "quotes"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.stream_quotes == False
        assert decision.generate_quotes == True  # Generate in backtest
        assert decision.error is None
    
    def test_ignore_ticks(self):
        """Ticks are ignored (logged warning, not error)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "ticks"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.error is None  # No error, just warning logged


# =============================================================================
# Test Historical Decisions
# =============================================================================

class TestHistoricalDecision:
    """Test historical data loading determination."""
    
    def test_load_1s_from_db_when_available(self):
        """Load 1s from DB when available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="1s",
            availability=availability
        )
        
        assert decision.load_from_db == "1s"
        assert decision.generate_from is None
        assert decision.needs_gap_fill == False
        assert decision.error is None
    
    def test_load_1m_from_db_when_available(self):
        """Load 1m from DB when available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="1m",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"
        assert decision.generate_from is None
        assert decision.needs_gap_fill == False
        assert decision.error is None
    
    def test_generate_5s_from_1s(self):
        """Generate 5s from 1s (only source)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5s",
            availability=availability
        )
        
        assert decision.load_from_db == "1s"
        assert decision.generate_from == "1s"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5m_from_1m(self):
        """Generate 5m from 1m (preferred source)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"
        assert decision.generate_from == "1m"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5m_from_1s_when_no_1m(self):
        """Generate 5m from 1s when 1m not available (fallback)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.load_from_db == "1s"  # Fallback to 1s
        assert decision.generate_from == "1s"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5d_from_1d(self):
        """Generate 5d from 1d (preferred source)."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=False,
            has_1d=True,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5d",
            availability=availability
        )
        
        assert decision.load_from_db == "1d"
        assert decision.generate_from == "1d"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5d_from_1m_when_no_1d(self):
        """Generate 5d from 1m when 1d not available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=True,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5d",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"  # Fallback to 1m
        assert decision.generate_from == "1m"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5d_from_1s_when_no_1d_or_1m(self):
        """Generate 5d from 1s when neither 1d nor 1m available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=True,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5d",
            availability=availability
        )
        
        assert decision.load_from_db == "1s"  # Final fallback to 1s
        assert decision.generate_from == "1s"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_error_when_no_source_available(self):
        """Error when no source interval available."""
        availability = AvailabilityInfo(
            symbol="AAPL",
            has_1s=False,
            has_1m=False,
            has_1d=False,
            has_quotes=False
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.load_from_db is None
        assert decision.generate_from is None
        assert decision.error is not None
        assert "no source interval available" in decision.error


# =============================================================================
# Test Generation Priority
# =============================================================================

class TestGenerationPriority:
    """Test source interval priority lists."""
    
    def test_5s_priority(self):
        """5s: only from 1s."""
        priority = get_generation_source_priority("5s")
        assert priority == ["1s"]
    
    def test_5m_priority(self):
        """5m: prefer 1m, fallback 1s."""
        priority = get_generation_source_priority("5m")
        assert priority == ["1m", "1s"]
    
    def test_15m_priority(self):
        """15m: prefer 1m, fallback 1s."""
        priority = get_generation_source_priority("15m")
        assert priority == ["1m", "1s"]
    
    def test_1h_priority(self):
        """1h: prefer 1m, fallback 1s."""
        priority = get_generation_source_priority("1h")
        assert priority == ["1m", "1s"]
    
    def test_5d_priority(self):
        """5d: prefer 1d, fallback 1m, fallback 1s."""
        priority = get_generation_source_priority("5d")
        assert priority == ["1d", "1m", "1s"]


# =============================================================================
# Test Gap Filling Eligibility
# =============================================================================

class TestGapFilling:
    """Test gap filling eligibility checks."""
    
    def test_can_fill_1m_from_1s_with_100_percent(self):
        """Can fill 1m from 1s with 100% quality."""
        can_fill, reason = can_fill_gap("1m", "1s", 100.0)
        assert can_fill == True
        assert reason is None
    
    def test_cannot_fill_1m_from_1s_with_low_quality(self):
        """Cannot fill 1m from 1s with <100% quality."""
        can_fill, reason = can_fill_gap("1m", "1s", 99.0)
        assert can_fill == False
        assert "quality" in reason.lower()
    
    def test_cannot_fill_1m_from_1d(self):
        """Cannot fill 1m from 1d (source larger than target)."""
        can_fill, reason = can_fill_gap("1m", "1d", 100.0)
        assert can_fill == False
        assert "not smaller" in reason.lower()
    
    def test_can_fill_1d_from_1m_with_100_percent(self):
        """Can fill 1d from 1m with 100% quality."""
        can_fill, reason = can_fill_gap("1d", "1m", 100.0)
        assert can_fill == True
        assert reason is None
    
    def test_cannot_fill_5m_from_1d(self):
        """Cannot fill 5m from 1d (wrong source type)."""
        can_fill, reason = can_fill_gap("5m", "1d", 100.0)
        assert can_fill == False
        # 1d not in priority list for 5m


# =============================================================================
# Test Completeness Checking
# =============================================================================

class TestCompletenessCheck:
    """Test interval completeness calculations."""
    
    def test_5m_from_1m_complete(self):
        """5m from 5 1m bars = 100% complete."""
        bars = [Mock() for _ in range(5)]
        is_complete, quality, expected = check_interval_completeness("5m", "1m", bars)
        assert is_complete == True
        assert quality == 100.0
        assert expected == 5
    
    def test_5m_from_1m_incomplete(self):
        """5m from 4 1m bars = 80% incomplete."""
        bars = [Mock() for _ in range(4)]
        is_complete, quality, expected = check_interval_completeness("5m", "1m", bars)
        assert is_complete == False
        assert quality == 80.0
        assert expected == 5
    
    def test_15m_from_1m_complete(self):
        """15m from 15 1m bars = 100% complete."""
        bars = [Mock() for _ in range(15)]
        is_complete, quality, expected = check_interval_completeness("15m", "1m", bars)
        assert is_complete == True
        assert quality == 100.0
        assert expected == 15
    
    def test_1d_from_1m_complete(self):
        """1d from 390 1m bars = 100% complete."""
        bars = [Mock() for _ in range(390)]
        is_complete, quality, expected = check_interval_completeness("1d", "1m", bars)
        assert is_complete == True
        assert quality == 100.0
        assert expected == 390
    
    def test_1d_from_1m_incomplete(self):
        """1d from 382 1m bars = 97.9% incomplete."""
        bars = [Mock() for _ in range(382)]
        is_complete, quality, expected = check_interval_completeness("1d", "1m", bars)
        assert is_complete == False
        assert abs(quality - 97.9487) < 0.01  # Close to 98%
        assert expected == 390
    
    def test_expected_bar_count_5m_from_1m(self):
        """Expected bars: 5m from 1m = 5."""
        count = calculate_expected_bar_count("5m", "1m")
        assert count == 5
    
    def test_expected_bar_count_1m_from_1s(self):
        """Expected bars: 1m from 1s = 60."""
        count = calculate_expected_bar_count("1m", "1s")
        assert count == 60
    
    def test_expected_bar_count_1d_from_1m(self):
        """Expected bars: 1d from 1m = 390."""
        count = calculate_expected_bar_count("1d", "1m")
        assert count == 390
