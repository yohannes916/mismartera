"""Integration tests for stream determination with Parquet data.

Tests the new unified stream determination logic using real Parquet files
instead of mocks.

NOTE: These tests are temporarily disabled as stream determination logic
was removed during restoration to working baseline. Will be re-enabled
when feature is re-implemented.
"""

import pytest
from datetime import date, datetime, time as dt_time

from app.threads.quality.stream_determination import (
    check_db_availability,
    determine_stream_interval,
    determine_historical_loading,
    can_fill_gap
)
from app.threads.quality.gap_filler import (
    check_interval_completeness,
    aggregate_bars_to_interval
)

# Skip entire module until stream determination is re-implemented
pytestmark = pytest.mark.skip(reason="Stream determination temporarily disabled - baseline restoration")

# =============================================================================
# Stream Determination Tests
# =============================================================================

@pytest.mark.integration
class TestStreamDeterminationWithParquet:
    """Test stream determination using real Parquet data."""
    
    def test_perfect_1s_detection(self, perfect_1s_data):
        """Test detection of perfect 1s data from Parquet."""
        # Access: Use production path (check_db_availability reads Parquet)
        availability = check_db_availability(
            session=None,  # Not used for Parquet
            symbol="AAPL",
            date_range=(date(2025, 1, 2), date(2025, 1, 2))
        )
        
        # Verify: Data discovered correctly
        assert availability.symbol == "AAPL"
        assert availability.has_1s == True
        assert availability.has_1m == False
        assert availability.has_1d == False
        assert availability.has_quotes == False
    
    def test_perfect_1m_detection(self, perfect_1m_data):
        """Test detection of perfect 1m data from Parquet."""
        availability = check_db_availability(
            session=None,
            symbol="AAPL",
            date_range=(date(2025, 1, 2), date(2025, 1, 2))
        )
        
        assert availability.has_1s == False
        assert availability.has_1m == True
        assert availability.has_1d == False
    
    def test_multi_symbol_detection(self, multi_symbol_data):
        """Test detection across multiple symbols with different intervals."""
        date_range = (date(2025, 1, 2), date(2025, 1, 2))
        
        # AAPL: Full data (1s + 1m + 1d + quotes)
        avail_aapl = check_db_availability(None, "AAPL", date_range)
        assert avail_aapl.has_1s == True
        assert avail_aapl.has_1m == True
        assert avail_aapl.has_1d == True
        assert avail_aapl.has_quotes == True
        
        # RIVN: Partial data (1m + 1d)
        avail_rivn = check_db_availability(None, "RIVN", date_range)
        assert avail_rivn.has_1s == False
        assert avail_rivn.has_1m == True
        assert avail_rivn.has_1d == True
        assert avail_rivn.has_quotes == False
        
        # TSLA: Daily only
        avail_tsla = check_db_availability(None, "TSLA", date_range)
        assert avail_tsla.has_1s == False
        assert avail_tsla.has_1m == False
        assert avail_tsla.has_1d == True
        assert avail_tsla.has_quotes == False
    
    def test_date_range_filtering(self, date_range_data):
        """Test that date range filtering works correctly."""
        # Within range - should find data
        avail_in_range = check_db_availability(
            None, "AAPL",
            (date(2025, 1, 2), date(2025, 1, 6))
        )
        assert avail_in_range.has_1m == True
        assert avail_in_range.has_1d == True
        
        # Outside range - should not find data
        avail_outside = check_db_availability(
            None, "AAPL",
            (date(2025, 2, 1), date(2025, 2, 5))  # No data here
        )
        assert avail_outside.has_1m == False
        assert avail_outside.has_1d == False
    
    def test_stream_decision_with_1s(self, perfect_1s_data):
        """Test stream decision with 1s data available."""
        # Get availability from Parquet
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        # Determine stream interval
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1s", "1m", "5m", "10m"],
            availability=availability,
            mode="backtest"
        )
        
        # Should stream 1s (smallest), generate others
        assert decision.stream_interval == "1s"
        assert set(decision.generate_intervals) == {"1m", "5m", "10m"}
        assert decision.stream_quotes == False  # No quotes in Parquet
        assert decision.generate_quotes == False  # Backtest mode, but no quote data
        assert decision.error is None
    
    def test_stream_decision_with_1m(self, perfect_1m_data):
        """Test stream decision with 1m data available."""
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "5m", "15m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval == "1m"
        assert set(decision.generate_intervals) == {"5m", "15m"}
        assert decision.error is None
    
    def test_stream_decision_multi_interval(self, multi_symbol_data):
        """Test stream decision when multiple base intervals available."""
        # AAPL has 1s + 1m + 1d
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1s", "1m", "5m", "1d"],
            availability=availability,
            mode="backtest"
        )
        
        # Should stream 1s (smallest), generate 1m, 5m, 1d
        assert decision.stream_interval == "1s"
        assert "1m" in decision.generate_intervals
        assert "5m" in decision.generate_intervals
        assert "1d" in decision.generate_intervals
    
    def test_quotes_with_parquet_data(self, multi_symbol_data):
        """Test quote handling when quotes exist in Parquet."""
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        # Request quotes in backtest mode
        decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "quotes"],
            availability=availability,
            mode="backtest"
        )
        
        # Backtest: quotes should be GENERATED, not streamed
        assert decision.stream_quotes == False
        assert decision.generate_quotes == True
    
    def test_no_data_error(self, isolated_parquet_storage):
        """Test error when no data exists for symbol."""
        # Don't create any data - just check empty storage
        availability = check_db_availability(
            None, "NONEXISTENT", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        assert availability.has_1s == False
        assert availability.has_1m == False
        assert availability.has_1d == False
        
        # Try to determine stream - should error
        decision = determine_stream_interval(
            symbol="NONEXISTENT",
            requested_intervals=["1m", "5m"],
            availability=availability,
            mode="backtest"
        )
        
        assert decision.stream_interval is None
        assert decision.error is not None
        assert "No base interval" in decision.error


# =============================================================================
# Historical Loading Tests
# =============================================================================

@pytest.mark.integration
class TestHistoricalLoadingWithParquet:
    """Test historical loading decisions using real Parquet data."""
    
    def test_load_1m_from_parquet(self, perfect_1m_data):
        """Test historical loading when 1m exists in Parquet."""
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="1m",
            availability=availability
        )
        
        assert decision.action == "load"
        assert decision.source_interval == "1m"
        assert decision.needs_gap_fill == False
    
    def test_generate_5m_from_1m(self, perfect_1m_data):
        """Test historical generation when source exists."""
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="5m",
            availability=availability
        )
        
        assert decision.action == "generate"
        assert decision.source_interval == "1m"
        assert decision.needs_gap_fill == True
    
    def test_generate_1m_from_1s(self, perfect_1s_data):
        """Test generation from 1s when 1m not available."""
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        
        decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="1m",
            availability=availability
        )
        
        assert decision.action == "generate"
        assert decision.source_interval == "1s"
        assert decision.needs_gap_fill == True
    
    def test_multi_symbol_historical(self, multi_symbol_data):
        """Test historical loading across multiple symbols."""
        date_range = (date(2025, 1, 2), date(2025, 1, 2))
        
        # AAPL: Has 1s, can generate 1m
        avail_aapl = check_db_availability(None, "AAPL", date_range)
        decision_aapl = determine_historical_loading("AAPL", "1m", avail_aapl)
        assert decision_aapl.action == "generate"  # Generate from 1s
        assert decision_aapl.source_interval == "1s"
        
        # RIVN: Has 1m, can load directly
        avail_rivn = check_db_availability(None, "RIVN", date_range)
        decision_rivn = determine_historical_loading("RIVN", "1m", avail_rivn)
        assert decision_rivn.action == "load"
        assert decision_rivn.source_interval == "1m"
        
        # TSLA: Only 1d, cannot provide 1m
        avail_tsla = check_db_availability(None, "TSLA", date_range)
        decision_tsla = determine_historical_loading("TSLA", "1m", avail_tsla)
        assert decision_tsla.action == "error"


# =============================================================================
# Gap Filling Tests
# =============================================================================

@pytest.mark.integration
class TestGapFillingCapability:
    """Test gap filling capability checks."""
    
    def test_can_fill_1m_from_1s(self, perfect_1s_data):
        """Test that 1m can be filled from complete 1s data."""
        can_fill, reason = can_fill_gap(
            target_interval="1m",
            source_interval="1s",
            source_quality=100.0
        )
        
        assert can_fill == True
        assert reason is None
    
    def test_cannot_fill_with_incomplete_source(self):
        """Test that gaps cannot be filled with incomplete source."""
        can_fill, reason = can_fill_gap(
            target_interval="1m",
            source_interval="1s",
            source_quality=95.0  # Incomplete
        )
        
        assert can_fill == False
        assert "100% completeness required" in reason
    
    def test_cannot_fill_1m_from_1d(self):
        """Test that smaller interval cannot be filled from larger."""
        can_fill, reason = can_fill_gap(
            target_interval="1m",
            source_interval="1d",
            source_quality=100.0
        )
        
        assert can_fill == False
        assert "Source interval must be smaller" in reason


# =============================================================================
# End-to-End Flow Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.e2e
class TestE2EStreamDetermination:
    """End-to-end tests of full stream determination flow."""
    
    def test_e2e_backtest_with_1m_data(self, perfect_1m_data):
        """E2E: Backtest session with 1m data available."""
        # Step 1: Check availability (reads Parquet)
        availability = check_db_availability(
            None, "AAPL", (date(2025, 1, 2), date(2025, 1, 2))
        )
        assert availability.has_1m == True
        
        # Step 2: Determine what to stream for current day
        stream_decision = determine_stream_interval(
            symbol="AAPL",
            requested_intervals=["1m", "5m", "10m"],
            availability=availability,
            mode="backtest"
        )
        assert stream_decision.stream_interval == "1m"
        assert "5m" in stream_decision.generate_intervals
        assert "10m" in stream_decision.generate_intervals
        
        # Step 3: Determine historical loading strategy
        hist_decision = determine_historical_loading(
            symbol="AAPL",
            requested_interval="1m",
            availability=availability
        )
        assert hist_decision.action == "load"
        assert hist_decision.source_interval == "1m"
    
    def test_e2e_multi_symbol_backtest(self, multi_symbol_data):
        """E2E: Backtest with multiple symbols."""
        date_range = (date(2025, 1, 2), date(2025, 1, 2))
        symbols = ["AAPL", "RIVN", "TSLA"]
        requested = ["1m", "5m"]
        
        results = {}
        for symbol in symbols:
            # Check availability
            avail = check_db_availability(None, symbol, date_range)
            
            # Determine stream
            decision = determine_stream_interval(
                symbol, requested, avail, mode="backtest"
            )
            
            results[symbol] = {
                'availability': avail,
                'decision': decision
            }
        
        # Verify AAPL (has 1s, streams 1s)
        assert results['AAPL']['availability'].has_1s == True
        assert results['AAPL']['decision'].stream_interval == "1s"
        
        # Verify RIVN (has 1m, streams 1m)
        assert results['RIVN']['availability'].has_1m == True
        assert results['RIVN']['decision'].stream_interval == "1m"
        
        # Verify TSLA (only 1d, cannot stream 1m - error)
        assert results['TSLA']['availability'].has_1d == True
        assert results['TSLA']['decision'].error is not None
