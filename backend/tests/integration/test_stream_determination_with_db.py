"""Integration Tests for Stream Determination with Test Database

Tests stream determination logic with controlled database scenarios using
the test database infrastructure.
"""

import pytest
from datetime import date, datetime, time

from app.threads.quality.stream_determination import (
    AvailabilityInfo,
    determine_stream_interval,
    determine_historical_loading,
    can_fill_gap
)

from app.threads.quality.gap_filler import (
    check_interval_completeness,
    aggregate_bars_to_interval,
    fill_1m_from_1s,
    fill_1d_from_1m
)

from app.models.trading import BarData
from tests.fixtures.stream_test_data import (
    SCENARIOS,
    get_scenario,
    create_mock_availability
)


# =============================================================================
# Test Stream Determination with DB Scenarios
# =============================================================================

@pytest.mark.integration
@pytest.mark.db
class TestStreamDeterminationWithDB:
    """Test stream decisions with real DB availability scenarios."""
    
    def test_scenario_perfect_1s_data(self):
        """Scenario: Symbol has complete 1s data."""
        scenario = get_scenario("perfect_1s")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1s", "1m", "5m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1s"
        assert set(decision.generate_intervals) == {"1m", "5m"}
        assert decision.error is None
    
    def test_scenario_perfect_1m_data(self):
        """Scenario: Symbol has complete 1m data."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1m", "5m", "15m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert set(decision.generate_intervals) == {"5m", "15m"}
        assert decision.error is None
    
    def test_scenario_only_1d_data(self):
        """Scenario: Symbol only has daily data."""
        scenario = get_scenario("only_1d")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1d", "5d"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1d"
        assert decision.generate_intervals == ["5d"]
        assert decision.error is None
    
    def test_scenario_1s_and_1m_both_available(self):
        """Scenario: Both 1s and 1m available, should stream 1s (smallest)."""
        scenario = get_scenario("1s_and_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1s", "1m", "5m"],
            availability=availability,
            mode="backtest"
        )
        
        # Should stream smallest (1s)
        assert decision.stream_interval == "1s"
        # 1m and 5m should be generated
        assert set(decision.generate_intervals) == {"1m", "5m"}
        assert decision.error is None
    
    def test_scenario_all_intervals_available(self):
        """Scenario: All intervals available, should stream 1s."""
        scenario = get_scenario("all_intervals")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1s", "1m", "5m", "1d"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1s"
        assert set(decision.generate_intervals) == {"1m", "5m", "1d"}
        assert decision.error is None
    
    def test_scenario_no_base_interval_error(self):
        """Scenario: No base interval available (error)."""
        scenario = get_scenario("no_base")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["5m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval is None
        assert decision.error is not None
        assert "No base interval" in decision.error
    
    def test_scenario_quotes_backtest_mode(self):
        """Scenario: Quotes in backtest mode (should be generated)."""
        scenario = get_scenario("with_quotes")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1m", "quotes"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.stream_quotes == False
        assert decision.generate_quotes == True  # Generated in backtest
        assert decision.error is None
    
    def test_scenario_quotes_live_mode(self):
        """Scenario: Quotes in live mode (should be streamed)."""
        scenario = get_scenario("with_quotes")
        availability = create_mock_availability(scenario)
        
        decision = determine_stream_interval(
            symbol=scenario.symbol,
            requested_intervals=["1m", "quotes"],
            availability=availability,
            mode="live"
        )
        
        assert decision.stream_interval == "1m"
        assert decision.stream_quotes == True  # Streamed in live
        assert decision.generate_quotes == False
        assert decision.error is None


# =============================================================================
# Test Historical Loading with DB Scenarios
# =============================================================================

@pytest.mark.integration
@pytest.mark.db
class TestHistoricalLoadingWithDB:
    """Test historical loading decisions with various DB states."""
    
    def test_load_1m_from_db_when_available(self):
        """Load 1m from DB when available."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="1m",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"
        assert decision.generate_from is None
        assert decision.needs_gap_fill == False
        assert decision.error is None
    
    def test_generate_5m_from_1m_historical(self):
        """Generate 5m from 1m for historical data."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"  # Load 1m source
        assert decision.generate_from == "1m"  # Generate 5m from it
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_5m_from_1s_when_no_1m(self):
        """Generate 5m from 1s when 1m not available (fallback)."""
        scenario = get_scenario("perfect_1s")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.load_from_db == "1s"  # Fallback to 1s
        assert decision.generate_from == "1s"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_generate_1d_from_1m_historical(self):
        """Generate 1d from 1m for historical data."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="1d",
            availability=availability
        )
        
        assert decision.load_from_db == "1m"
        assert decision.generate_from == "1m"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_fallback_chain_for_5d(self):
        """Test fallback chain: 5d → 1d (not avail) → 1m."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="5d",
            availability=availability
        )
        
        # 1d not available, should fallback to 1m
        assert decision.load_from_db == "1m"
        assert decision.generate_from == "1m"
        assert decision.needs_gap_fill == True
        assert decision.error is None
    
    def test_error_when_no_source_for_5s(self):
        """Error when requesting 5s but no 1s available."""
        scenario = get_scenario("perfect_1m")
        availability = create_mock_availability(scenario)
        
        decision = determine_historical_loading(
            symbol=scenario.symbol,
            requested_interval="5s",  # Needs 1s
            availability=availability
        )
        
        # 5s can ONLY be generated from 1s, and 1s not available
        assert decision.load_from_db is None
        assert decision.generate_from is None
        assert decision.error is not None


# =============================================================================
# Test Gap Filling with Controlled Data
# =============================================================================

@pytest.mark.integration
@pytest.mark.db
class TestGapFillingWithDB:
    """Test gap filling with controlled gap scenarios."""
    
    def test_fill_1m_gap_with_complete_1s(self):
        """Fill 1m gap when complete 1s data available."""
        # Create 60 1s bars (complete minute)
        bars_1s = []
        base_time = datetime(2025, 1, 2, 9, 35, 0)
        
        for i in range(60):
            bar = BarData(
                symbol="TEST",
                timestamp=base_time.replace(second=i),
                interval="1s",
                open=100.0 + i * 0.01,
                high=100.1 + i * 0.01,
                low=99.9 + i * 0.01,
                close=100.0 + i * 0.01,
                volume=1000
            )
            bars_1s.append(bar)
        
        # Attempt gap fill
        result = fill_1m_from_1s(
            symbol="TEST",
            target_timestamp=base_time,
            bars_1s=bars_1s
        )
        
        assert result.success == True
        assert result.filled_bar is not None
        assert result.quality == 100.0
        assert result.source_interval == "1s"
        assert result.bars_used == 60
    
    def test_cannot_fill_1m_gap_with_partial_1s(self):
        """Cannot fill 1m gap when 1s data incomplete."""
        # Create only 50 1s bars (incomplete)
        bars_1s = []
        base_time = datetime(2025, 1, 2, 9, 35, 0)
        
        for i in range(50):  # Missing 10 bars
            bar = BarData(
                symbol="TEST",
                timestamp=base_time.replace(second=i),
                interval="1s",
                open=100.0,
                high=100.1,
                low=99.9,
                close=100.0,
                volume=1000
            )
            bars_1s.append(bar)
        
        result = fill_1m_from_1s(
            symbol="TEST",
            target_timestamp=base_time,
            bars_1s=bars_1s
        )
        
        assert result.success == False
        assert result.filled_bar is None
        assert result.quality < 100.0  # Incomplete
        assert "Incomplete" in result.error
    
    def test_fill_1d_gap_with_complete_1m(self):
        """Fill 1d gap when complete 1m data available."""
        # Create 390 1m bars (complete trading day)
        bars_1m = []
        base_date = date(2025, 1, 2)
        start_time = time(9, 30)
        
        # Generate 390 1m bars from 9:30 AM to 4:00 PM
        for i in range(390):
            hour = 9 + (30 + i) // 60
            minute = (30 + i) % 60
            
            bar = BarData(
                symbol="TEST",
                timestamp=datetime.combine(base_date, time(hour, minute)),
                interval="1m",
                open=100.0 + i * 0.01,
                high=100.1 + i * 0.01,
                low=99.9 + i * 0.01,
                close=100.0 + i * 0.01,
                volume=1000
            )
            bars_1m.append(bar)
        
        result = fill_1d_from_1m(
            symbol="TEST",
            target_date=base_date,
            bars_1m=bars_1m
        )
        
        assert result.success == True
        assert result.filled_bar is not None
        assert result.quality == 100.0
        assert result.source_interval == "1m"
        assert result.bars_used == 390
    
    def test_cannot_fill_1d_gap_with_partial_1m(self):
        """Cannot fill 1d gap when 1m data incomplete."""
        # Create only 382 1m bars (incomplete day)
        bars_1m = []
        base_date = date(2025, 1, 2)
        
        for i in range(382):  # Missing 8 bars
            hour = 9 + (30 + i) // 60
            minute = (30 + i) % 60
            
            bar = BarData(
                symbol="TEST",
                timestamp=datetime.combine(base_date, time(hour, minute)),
                interval="1m",
                open=100.0,
                high=100.1,
                low=99.9,
                close=100.0,
                volume=1000
            )
            bars_1m.append(bar)
        
        result = fill_1d_from_1m(
            symbol="TEST",
            target_date=base_date,
            bars_1m=bars_1m
        )
        
        assert result.success == False
        assert result.filled_bar is None
        assert result.quality < 100.0  # 97.9%
        assert "Incomplete" in result.error


# =============================================================================
# Test Completeness Enforcement
# =============================================================================

@pytest.mark.integration
@pytest.mark.db
class TestCompletenessEnforcement:
    """Test that 100% completeness is enforced."""
    
    def test_aggregate_skips_with_incomplete_data(self):
        """Aggregation skips when data incomplete (require_complete=True)."""
        # Create 4 out of 5 bars needed for 5m
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30, 0)
        
        for i in range(4):  # Only 4 bars
            bar = BarData(
                symbol="TEST",
                timestamp=base_time.replace(minute=30+i),
                interval="1m",
                open=100.0,
                high=100.1,
                low=99.9,
                close=100.0,
                volume=1000
            )
            bars.append(bar)
        
        result = aggregate_bars_to_interval(
            symbol="TEST",
            target_interval="5m",
            source_interval="1m",
            source_bars=bars,
            require_complete=True
        )
        
        # Should return None (skipped due to incomplete)
        assert result is None
    
    def test_aggregate_succeeds_with_complete_data(self):
        """Aggregation succeeds when data complete."""
        # Create 5 out of 5 bars needed for 5m
        bars = []
        base_time = datetime(2025, 1, 2, 9, 30, 0)
        
        for i in range(5):  # All 5 bars
            bar = BarData(
                symbol="TEST",
                timestamp=base_time.replace(minute=30+i),
                interval="1m",
                open=100.0 + i,
                high=100.5 + i,
                low=99.5 + i,
                close=100.0 + i,
                volume=1000
            )
            bars.append(bar)
        
        result = aggregate_bars_to_interval(
            symbol="TEST",
            target_interval="5m",
            source_interval="1m",
            source_bars=bars,
            require_complete=True
        )
        
        # Should return aggregated bar
        assert result is not None
        assert result.interval == "5m"
        assert result.open == 100.0  # First bar's open
        assert result.close == 104.0  # Last bar's close
        assert result.high == 104.5  # Max of all highs
        assert result.low == 99.5  # Min of all lows
        assert result.volume == 5000  # Sum of volumes
    
    def test_completeness_check_calculations(self):
        """Test completeness percentage calculations."""
        # 5m from 1m: need 5 bars
        bars_complete = [None] * 5
        is_complete, quality, expected = check_interval_completeness(
            "5m", "1m", bars_complete
        )
        assert is_complete == True
        assert quality == 100.0
        assert expected == 5
        
        # 5m from 1m: only 4 bars (80%)
        bars_incomplete = [None] * 4
        is_complete, quality, expected = check_interval_completeness(
            "5m", "1m", bars_incomplete
        )
        assert is_complete == False
        assert quality == 80.0
        assert expected == 5
