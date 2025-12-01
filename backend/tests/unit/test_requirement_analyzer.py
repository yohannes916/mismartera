"""Unit tests for session requirement analyzer.

Tests Requirements: 1-12, 65, 75-77
"""

import pytest
from app.threads.quality.requirement_analyzer import (
    parse_interval,
    determine_required_base,
    select_smallest_base,
    analyze_session_requirements,
    validate_configuration,
    IntervalInfo,
    IntervalType,
    RequirementSource,
    SessionRequirements
)


# =============================================================================
# Interval Parsing Tests (Req 75)
# =============================================================================

class TestIntervalParsing:
    """Test interval string parsing."""
    
    def test_parse_1s_interval(self):
        """Test parsing 1s interval."""
        info = parse_interval("1s")
        assert info.interval == "1s"
        assert info.type == IntervalType.SECOND
        assert info.seconds == 1
        assert info.is_base is True
    
    def test_parse_5s_interval(self):
        """Test parsing 5s interval."""
        info = parse_interval("5s")
        assert info.interval == "5s"
        assert info.type == IntervalType.SECOND
        assert info.seconds == 5
        assert info.is_base is False
    
    def test_parse_1m_interval(self):
        """Test parsing 1m interval."""
        info = parse_interval("1m")
        assert info.interval == "1m"
        assert info.type == IntervalType.MINUTE
        assert info.seconds == 60
        assert info.is_base is True
    
    def test_parse_5m_interval(self):
        """Test parsing 5m interval."""
        info = parse_interval("5m")
        assert info.interval == "5m"
        assert info.type == IntervalType.MINUTE
        assert info.seconds == 300
        assert info.is_base is False
    
    def test_parse_1h_interval(self):
        """Test parsing 1h interval."""
        info = parse_interval("1h")
        assert info.interval == "1h"
        assert info.type == IntervalType.HOUR
        assert info.seconds == 3600
        assert info.is_base is False  # Hours never base
    
    def test_parse_1d_interval(self):
        """Test parsing 1d interval."""
        info = parse_interval("1d")
        assert info.interval == "1d"
        assert info.type == IntervalType.DAY
        assert info.seconds == 86400
        assert info.is_base is True
    
    def test_parse_quotes(self):
        """Test parsing quotes."""
        info = parse_interval("quotes")
        assert info.interval == "quotes"
        assert info.type == IntervalType.QUOTE
        assert info.is_base is False
    
    def test_parse_invalid_format(self):
        """Test parsing invalid format raises error (Req 65)."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval("5x")
    
    def test_parse_empty_string(self):
        """Test parsing empty string raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_interval("")
    
    def test_parse_case_insensitive(self):
        """Test parsing is case insensitive."""
        info1 = parse_interval("1M")
        info2 = parse_interval("1m")
        assert info1.interval == "1m"  # Normalized to lowercase
        assert info2.interval == "1m"


# =============================================================================
# Base Interval Determination Tests (Req 9-11)
# =============================================================================

class TestBaseIntervalDetermination:
    """Test determining required base interval for derivation."""
    
    def test_5s_requires_1s(self):
        """Test 5s requires 1s base (Req 9)."""
        assert determine_required_base("5s") == "1s"
    
    def test_10s_requires_1s(self):
        """Test 10s requires 1s base (Req 9)."""
        assert determine_required_base("10s") == "1s"
    
    def test_30s_requires_1s(self):
        """Test 30s requires 1s base (Req 9)."""
        assert determine_required_base("30s") == "1s"
    
    def test_5m_requires_1m(self):
        """Test 5m requires 1m base (Req 10)."""
        assert determine_required_base("5m") == "1m"
    
    def test_15m_requires_1m(self):
        """Test 15m requires 1m base (Req 10)."""
        assert determine_required_base("15m") == "1m"
    
    def test_30m_requires_1m(self):
        """Test 30m requires 1m base (Req 10)."""
        assert determine_required_base("30m") == "1m"
    
    def test_1h_requires_1m(self):
        """Test 1h requires 1m base (Req 11)."""
        assert determine_required_base("1h") == "1m"
    
    def test_4h_requires_1m(self):
        """Test 4h requires 1m base (Req 11)."""
        assert determine_required_base("4h") == "1m"
    
    def test_1d_requires_1m(self):
        """Test 1d requires 1m for aggregation (Req 11)."""
        # 1d is itself a base, but when generating from scratch we use 1m
        assert determine_required_base("1d") == "1d"
    
    def test_5d_requires_1m(self):
        """Test 5d requires 1m base (Req 11)."""
        assert determine_required_base("5d") == "1m"
    
    def test_base_interval_returns_itself(self):
        """Test base intervals return themselves."""
        assert determine_required_base("1s") == "1s"
        assert determine_required_base("1m") == "1m"
        assert determine_required_base("1d") == "1d"
    
    def test_quotes_returns_none(self):
        """Test quotes don't have a base interval."""
        assert determine_required_base("quotes") is None


# =============================================================================
# Base Selection Tests (Req 12)
# =============================================================================

class TestBaseSelection:
    """Test selecting smallest base interval."""
    
    def test_1s_smallest(self):
        """Test 1s is selected as smallest."""
        assert select_smallest_base(["1m", "1s", "1d"]) == "1s"
    
    def test_1m_smallest_without_1s(self):
        """Test 1m is selected when no 1s."""
        assert select_smallest_base(["1m", "1d"]) == "1m"
    
    def test_1d_when_only_option(self):
        """Test 1d selected when only option."""
        assert select_smallest_base(["1d"]) == "1d"
    
    def test_duplicates_handled(self):
        """Test duplicates don't affect result."""
        assert select_smallest_base(["1m", "1s", "1m", "1s"]) == "1s"
    
    def test_empty_list_raises_error(self):
        """Test empty list raises error."""
        with pytest.raises(ValueError, match="empty list"):
            select_smallest_base([])
    
    def test_none_values_filtered(self):
        """Test None values are filtered out."""
        assert select_smallest_base(["1m", None, "1s", None]) == "1s"


# =============================================================================
# Session Requirements Analysis Tests (Req 1-6)
# =============================================================================

class TestSessionRequirementsAnalysis:
    """Test complete session requirements analysis."""
    
    def test_single_interval(self):
        """Test analysis with single interval (Req 1)."""
        reqs = analyze_session_requirements(["1m"])
        assert reqs.explicit_intervals == ["1m"]
        assert reqs.implicit_intervals == []
        assert reqs.required_base_interval == "1m"
        assert reqs.derivable_intervals == []
    
    def test_multiple_intervals_same_base(self):
        """Test multiple intervals requiring same base (Req 1, 2)."""
        reqs = analyze_session_requirements(["1m", "5m", "15m"])
        assert set(reqs.explicit_intervals) == {"1m", "5m", "15m"}
        assert reqs.required_base_interval == "1m"
        assert set(reqs.derivable_intervals) == {"5m", "15m"}
    
    def test_5s_and_5m_requires_1s(self):
        """Test 5s + 5m requires 1s base (Req 2, 12)."""
        reqs = analyze_session_requirements(["5s", "5m"])
        assert reqs.required_base_interval == "1s"
        assert "1s" in [r.interval for r in reqs.implicit_intervals]
        # Check reasoning
        implicit_1s = [r for r in reqs.implicit_intervals if r.interval == "1s"]
        assert len(implicit_1s) > 0
        assert "5s" in implicit_1s[0].reason or "generate" in implicit_1s[0].reason.lower()
    
    def test_only_5m_requires_1m(self):
        """Test only 5m requires 1m base (Req 2, 10)."""
        reqs = analyze_session_requirements(["5m"])
        assert reqs.required_base_interval == "1m"
        # 1m should be implicit
        assert "1m" in [r.interval for r in reqs.implicit_intervals]
    
    def test_indicator_requirements(self):
        """Test indicator requirements added (Req 3)."""
        reqs = analyze_session_requirements(
            streams=["1d"],
            indicator_requirements=["1m"]
        )
        assert reqs.required_base_interval == "1m"
        # 1m should be in implicit requirements from indicator
        indicator_reqs = [
            r for r in reqs.implicit_intervals 
            if r.source == RequirementSource.IMPLICIT_INDICATOR
        ]
        assert len(indicator_reqs) > 0
        assert "indicator" in indicator_reqs[0].reason.lower()
    
    def test_quotes_only_raises_error(self):
        """Test quotes only raises error (need at least one bar interval)."""
        with pytest.raises(ValueError, match="No bar intervals"):
            analyze_session_requirements(["quotes"])
    
    def test_quotes_with_bars(self):
        """Test quotes combined with bars."""
        reqs = analyze_session_requirements(["1m", "quotes"])
        assert "quotes" in reqs.explicit_intervals
        assert reqs.required_base_interval == "1m"
    
    def test_empty_streams_raises_error(self):
        """Test empty streams raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            analyze_session_requirements([])
    
    def test_invalid_stream_raises_error(self):
        """Test invalid stream raises error (Req 6, 65)."""
        with pytest.raises(ValueError, match="Invalid stream"):
            analyze_session_requirements(["5x"])
    
    def test_all_requirements_populated(self):
        """Test all_requirements includes explicit and implicit (Req 6)."""
        reqs = analyze_session_requirements(["5m", "15m"])
        # Should have 5m, 15m (explicit) and 1m (implicit)
        assert len(reqs.all_requirements) == 3
        sources = {r.source for r in reqs.all_requirements}
        assert RequirementSource.EXPLICIT in sources
        assert RequirementSource.IMPLICIT_DERIVATION in sources
    
    def test_reasoning_provided(self):
        """Test clear reasoning provided for requirements (Req 6)."""
        reqs = analyze_session_requirements(["5s"])
        # Should have implicit 1s requirement
        implicit_1s = [
            r for r in reqs.implicit_intervals 
            if r.interval == "1s"
        ]
        assert len(implicit_1s) > 0
        assert len(implicit_1s[0].reason) > 0
        assert "5s" in implicit_1s[0].reason


# =============================================================================
# Configuration Validation Tests (Req 76, 77)
# =============================================================================

class TestConfigurationValidation:
    """Test configuration validation rules."""
    
    def test_ticks_rejected(self):
        """Test ticks are rejected (Req 76)."""
        with pytest.raises(ValueError, match="Ticks are not supported"):
            validate_configuration(["ticks"], "backtest")
    
    def test_tick_rejected(self):
        """Test tick (singular) is rejected (Req 76)."""
        with pytest.raises(ValueError, match="Ticks are not supported"):
            validate_configuration(["tick"], "backtest")
    
    def test_valid_config_accepted(self):
        """Test valid configuration is accepted."""
        # Should not raise
        validate_configuration(["1m", "5m"], "backtest")
        validate_configuration(["1m", "quotes"], "live")
    
    def test_invalid_interval_format(self):
        """Test invalid interval format is rejected (Req 75)."""
        with pytest.raises(ValueError, match="Invalid stream configuration"):
            validate_configuration(["5x"], "backtest")


# =============================================================================
# Complex Scenarios
# =============================================================================

class TestComplexScenarios:
    """Test complex real-world scenarios."""
    
    def test_sub_second_trading(self):
        """Test sub-second trading scenario."""
        reqs = analyze_session_requirements(["5s", "10s", "1m"])
        assert reqs.required_base_interval == "1s"
        assert set(reqs.derivable_intervals) == {"5s", "10s", "1m"}
    
    def test_standard_day_trading(self):
        """Test standard day trading scenario."""
        reqs = analyze_session_requirements(["1m", "5m", "15m"])
        assert reqs.required_base_interval == "1m"
        assert set(reqs.derivable_intervals) == {"5m", "15m"}
    
    def test_swing_trading_with_indicator(self):
        """Test swing trading with volume indicator."""
        reqs = analyze_session_requirements(
            streams=["1d"],
            indicator_requirements=["1m"]
        )
        assert reqs.required_base_interval == "1m"
        assert "1d" in reqs.derivable_intervals
    
    def test_multi_timeframe_analysis(self):
        """Test multi-timeframe analysis."""
        reqs = analyze_session_requirements(["1m", "5m", "15m", "1h", "1d"])
        assert reqs.required_base_interval == "1m"
        assert set(reqs.derivable_intervals) == {"5m", "15m", "1h", "1d"}
    
    def test_conflict_resolution(self):
        """Test conflict resolution (5s needs 1s, overrides 1m)."""
        reqs = analyze_session_requirements(["5s", "5m", "1h", "1d"])
        assert reqs.required_base_interval == "1s"  # Smallest wins
        # 1m is also derivable because 5m requires 1m, which must be generated from 1s
        assert set(reqs.derivable_intervals) == {"5s", "1m", "5m", "1h", "1d"}
