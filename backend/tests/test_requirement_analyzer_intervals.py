"""Tests for requirement_analyzer interval support.

Tests that all intervals (s/m/d/w) are supported and hourly is rejected.
"""
import pytest

from app.threads.quality.requirement_analyzer import (
    analyze_session_requirements,
    parse_interval,
    IntervalType,
)


class TestIntervalParsing:
    """Test interval parsing and validation."""
    
    def test_parse_seconds(self):
        """Test parsing second intervals."""
        info = parse_interval("1s")
        assert info.interval == "1s"
        assert info.type == IntervalType.SECOND
        assert info.seconds == 1
        
        info = parse_interval("5s")
        assert info.seconds == 5
        
        info = parse_interval("10s")
        assert info.seconds == 10
        
        info = parse_interval("30s")
        assert info.seconds == 30
    
    def test_parse_minutes(self):
        """Test parsing minute intervals."""
        info = parse_interval("1m")
        assert info.interval == "1m"
        assert info.type == IntervalType.MINUTE
        assert info.seconds == 60
        
        info = parse_interval("5m")
        assert info.seconds == 300
        
        info = parse_interval("15m")
        assert info.seconds == 900
        
        info = parse_interval("30m")
        assert info.seconds == 1800
        
        info = parse_interval("60m")
        assert info.seconds == 3600
    
    def test_parse_days(self):
        """Test parsing day intervals."""
        info = parse_interval("1d")
        assert info.interval == "1d"
        assert info.type == IntervalType.DAY
        assert info.seconds == 86400
        
        info = parse_interval("5d")
        assert info.seconds == 86400 * 5
        
        info = parse_interval("10d")
        assert info.seconds == 86400 * 10
    
    def test_parse_weeks(self):
        """Test parsing week intervals."""
        info = parse_interval("1w")
        assert info.interval == "1w"
        assert info.type == IntervalType.WEEK
        assert info.seconds == 604800
        
        info = parse_interval("2w")
        assert info.seconds == 604800 * 2
        
        info = parse_interval("4w")
        assert info.seconds == 604800 * 4
        
        info = parse_interval("52w")
        assert info.seconds == 604800 * 52
    
    def test_reject_hourly(self):
        """Test that hourly intervals are rejected."""
        with pytest.raises(ValueError, match="Hourly intervals.*not supported"):
            parse_interval("1h")
        
        with pytest.raises(ValueError, match="Hourly intervals.*not supported"):
            parse_interval("2h")
        
        with pytest.raises(ValueError, match="Hourly intervals.*not supported"):
            parse_interval("4h")
    
    def test_invalid_format(self):
        """Test invalid interval formats."""
        with pytest.raises(ValueError):
            parse_interval("invalid")
        
        with pytest.raises(ValueError):
            parse_interval("5x")
        
        with pytest.raises(ValueError):
            parse_interval("m5")


class TestBaseIntervalPriority:
    """Test base interval priority ordering."""
    
    def test_priority_order(self):
        """Test base interval priority: 1s < 1m < 1d < 1w (by seconds)."""
        # Priority is determined by seconds (smaller = higher priority)
        assert parse_interval("1s").seconds < parse_interval("1m").seconds
        assert parse_interval("1m").seconds < parse_interval("1d").seconds
        assert parse_interval("1d").seconds < parse_interval("1w").seconds
    
    def test_same_unit_priority(self):
        """Test priority within same unit."""
        # Seconds
        assert parse_interval("1s").seconds < parse_interval("5s").seconds
        
        # Minutes
        assert parse_interval("1m").seconds < parse_interval("5m").seconds
        
        # Days
        assert parse_interval("1d").seconds < parse_interval("5d").seconds
        
        # Weeks
        assert parse_interval("1w").seconds < parse_interval("4w").seconds


class TestRequirementAnalyzer:
    """Test requirement analyzer with all interval types."""
    
    def test_seconds_only(self):
        """Test with only second intervals."""
        result = analyze_session_requirements(["1s", "5s", "10s"])
        
        assert result.required_base_interval == "1s"
        assert "5s" in result.derivable_intervals
        assert "10s" in result.derivable_intervals
    
    def test_minutes_only(self):
        """Test with only minute intervals."""
        result = analyze_session_requirements(["1m", "5m", "15m"])
        
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals
        assert "15m" in result.derivable_intervals
    
    def test_days_only(self):
        """Test with only day intervals."""
        result = analyze_session_requirements(["1d", "5d"])
        
        assert result.required_base_interval == "1d"
        assert "5d" in result.derivable_intervals
    
    def test_weeks_only(self):
        """Test with only week intervals."""
        result = analyze_session_requirements(["1w", "4w"])
        
        assert result.required_base_interval == "1w"
        assert "4w" in result.derivable_intervals
    
    def test_mixed_seconds_minutes(self):
        """Test with mixed second and minute intervals."""
        result = analyze_session_requirements(["1s", "5s", "1m", "5m"])
        
        # Should use 1s as base (lowest priority)
        assert result.required_base_interval == "1s"
        assert "5s" in result.derivable_intervals
        assert "1m" in result.derivable_intervals
        assert "5m" in result.derivable_intervals
    
    def test_mixed_minutes_days(self):
        """Test with mixed minute and day intervals."""
        result = analyze_session_requirements(["1m", "5m", "1d"])
        
        # Should use 1m as base
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals
        assert "1d" in result.derivable_intervals
    
    def test_mixed_days_weeks(self):
        """Test with mixed day and week intervals."""
        result = analyze_session_requirements(["1d", "1w", "4w"])
        
        # Should use 1d as base
        assert result.required_base_interval == "1d"
        assert "1w" in result.derivable_intervals
        assert "4w" in result.derivable_intervals
    
    def test_all_units_mixed(self):
        """Test with all unit types mixed."""
        result = analyze_session_requirements(["1s", "1m", "5m", "1d", "1w"])
        
        # Should use 1s as base (lowest priority)
        assert result.required_base_interval == "1s"
        assert "1m" in result.derivable_intervals
        assert "5m" in result.derivable_intervals
        assert "1d" in result.derivable_intervals
        assert "1w" in result.derivable_intervals
    
    def test_52_week_high_low(self):
        """Test 52-week interval support."""
        result = analyze_session_requirements(["1d", "1w", "52w"])
        
        assert result.required_base_interval == "1d"
        assert "1w" in result.derivable_intervals
        # 52w might not be derivable depending on implementation
        # but should not error
    
    def test_reject_hourly_in_list(self):
        """Test that hourly intervals in list are rejected."""
        with pytest.raises(ValueError, match="Hourly intervals.*not supported"):
            analyze_session_requirements(["1m", "1h", "5m"])
    
    def test_empty_list(self):
        """Test with empty stream list."""
        # Empty streams list should raise an error (changed behavior - now validates)
        with pytest.raises(ValueError, match="Streams list cannot be empty"):
            analyze_session_requirements([])
    
    def test_duplicate_intervals(self):
        """Test with duplicate intervals."""
        result = analyze_session_requirements(["1m", "5m", "1m", "5m"])
        
        assert result.required_base_interval == "1m"
        assert "5m" in result.derivable_intervals


class TestIntervalAggregation:
    """Test interval aggregation chains."""
    
    def test_minute_chain(self):
        """Test minute aggregation chain: 1m -> 5m -> 15m -> 30m."""
        result = analyze_session_requirements(["1m", "5m", "15m", "30m"])
        
        assert result.required_base_interval == "1m"
        # All should be derivable from 1m
        assert "5m" in result.derivable_intervals
        assert "15m" in result.derivable_intervals
        assert "30m" in result.derivable_intervals
    
    def test_day_to_week(self):
        """Test day to week aggregation: 1d -> 1w."""
        result = analyze_session_requirements(["1d", "1w"])
        
        assert result.required_base_interval == "1d"
        assert "1w" in result.derivable_intervals
    
    def test_second_to_minute_to_day(self):
        """Test full chain: 1s -> 1m -> 1d."""
        result = analyze_session_requirements(["1s", "1m", "1d"])
        
        assert result.required_base_interval == "1s"
        assert "1m" in result.derivable_intervals
        assert "1d" in result.derivable_intervals


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_base_interval(self):
        """Test with only base interval."""
        for interval in ["1s", "1m", "1d", "1w"]:
            result = analyze_session_requirements([interval])
            assert result.required_base_interval == interval
    
    def test_large_periods(self):
        """Test with large period values."""
        result = analyze_session_requirements(["1m", "240m", "1d"])
        
        assert result.required_base_interval == "1m"
        assert "240m" in result.derivable_intervals
    
    def test_case_sensitivity(self):
        """Test case handling."""
        # Should work with both cases
        result1 = analyze_session_requirements(["1M", "5M"])
        result2 = analyze_session_requirements(["1m", "5m"])
        
        assert result1.required_base_interval == result2.required_base_interval


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
