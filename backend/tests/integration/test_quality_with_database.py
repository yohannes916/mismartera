"""Integration Tests for Quality Calculation with Test Database

These tests use the test database with synthetic data to verify quality calculations
in a more realistic environment than mocked unit tests.

Benefits over unit tests:
- Real database queries
- Actual TimeManager behavior
- Tests SQL logic and database constraints
- Verifies data flow through components
"""
import pytest
from datetime import date, time

from app.threads.quality.quality_helpers import (
    calculate_quality_for_historical_date,
    calculate_quality_for_current_session,
    get_regular_trading_hours
)
from tests.fixtures.test_symbols import get_test_symbol, TEST_SYMBOLS


@pytest.mark.integration
class TestQualityWithTestDatabase:
    """Integration tests using test database."""
    
    def test_database_loaded_correctly(self, test_db_stats):
        """Verify test database has expected data."""
        assert test_db_stats["trading_sessions"] > 0, "No trading sessions loaded"
        assert test_db_stats["regular_days"] >= 2, "Need at least 2 regular days"
        assert test_db_stats["early_close_days"] >= 1, "Need at least 1 early close"
        assert test_db_stats["holidays"] >= 1, "Need at least 1 holiday"
        
        print(f"\n📊 Test Database Stats: {test_db_stats}")
    
    def test_perfect_quality_regular_day(self, test_db, test_time_manager_with_db):
        """Test quality calculation with perfect data (SYMBOL_X)."""
        symbol_x = get_test_symbol("SYMBOL_X")
        test_date = date(2025, 1, 2)
        
        # SYMBOL_X has all 390 bars for this date
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_x.symbol,
            "1m",
            test_date,
            actual_bars=390
        )
        
        assert quality == 100.0, "Perfect data should have 100% quality"
    
    def test_quality_with_small_gaps(self, test_db, test_time_manager_with_db):
        """Test quality calculation with missing bars (SYMBOL_Y)."""
        symbol_y = get_test_symbol("SYMBOL_Y")
        test_date = date(2025, 1, 2)
        
        # SYMBOL_Y has 3 bars missing on this date (387/390)
        actual_bars = symbol_y.get_actual_bars_for_date(test_date)
        
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_y.symbol,
            "1m",
            test_date,
            actual_bars=actual_bars
        )
        
        # 387/390 = 99.23%
        assert quality == pytest.approx(99.23, rel=0.01)
    
    def test_quality_on_early_close_day(self, test_db, test_time_manager_with_db):
        """Test quality calculation on early close day (SYMBOL_Z)."""
        symbol_z = get_test_symbol("SYMBOL_Z")
        test_date = date(2024, 11, 28)  # Thanksgiving
        
        # SYMBOL_Z has all 210 bars for half-day
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_z.symbol,
            "1m",
            test_date,
            actual_bars=210
        )
        
        assert quality == 100.0, "All bars present for early close should be 100%"
    
    def test_quality_returns_none_on_holiday(self, test_db, test_time_manager_with_db):
        """Test quality returns None on holiday (SYMBOL_W)."""
        symbol_w = get_test_symbol("SYMBOL_W")
        test_date = date(2024, 12, 25)  # Christmas
        
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_w.symbol,
            "1m",
            test_date,
            actual_bars=0
        )
        
        assert quality is None, "Holiday should return None"
    
    def test_quality_with_large_gap(self, test_db, test_time_manager_with_db):
        """Test quality calculation with large gap (SYMBOL_V)."""
        symbol_v = get_test_symbol("SYMBOL_V")
        test_date = date(2025, 1, 2)
        
        # SYMBOL_V has 120 bars missing (10:00-11:59)
        actual_bars = symbol_v.get_actual_bars_for_date(test_date)
        
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_v.symbol,
            "1m",
            test_date,
            actual_bars=actual_bars
        )
        
        # 270/390 = 69.23%
        assert quality == pytest.approx(69.23, rel=0.01)
    
    def test_get_trading_hours_from_database(self, test_db, test_time_manager_with_db):
        """Test that trading hours are retrieved from database."""
        test_date = date(2025, 1, 2)
        
        hours = get_regular_trading_hours(
            test_time_manager_with_db,
            test_db,
            test_date
        )
        
        assert hours is not None, "Should find trading hours"
        
        open_dt, close_dt = hours
        assert open_dt.time() == time(9, 30), "Market opens at 9:30 AM"
        assert close_dt.time() == time(16, 0), "Market closes at 4:00 PM"
    
    def test_early_close_hours_from_database(self, test_db, test_time_manager_with_db):
        """Test early close hours are correct in database."""
        test_date = date(2024, 11, 28)  # Thanksgiving
        
        hours = get_regular_trading_hours(
            test_time_manager_with_db,
            test_db,
            test_date
        )
        
        assert hours is not None, "Should find early close hours"
        
        open_dt, close_dt = hours
        assert open_dt.time() == time(9, 30), "Market opens at 9:30 AM"
        assert close_dt.time() == time(13, 0), "Early close at 1:00 PM"
    
    def test_five_minute_bars_quality(self, test_db, test_time_manager_with_db):
        """Test quality calculation for 5-minute bars."""
        symbol_x = get_test_symbol("SYMBOL_X")
        test_date = date(2025, 1, 2)
        
        # 390 minutes / 5 = 78 expected 5-minute bars
        quality = calculate_quality_for_historical_date(
            test_time_manager_with_db,
            test_db,
            symbol_x.symbol,
            "5m",
            test_date,
            actual_bars=78
        )
        
        assert quality == 100.0, "All 5m bars present should be 100%"
    
    def test_consistency_across_multiple_dates(self, test_db, test_time_manager_with_db):
        """Test quality calculation consistency across multiple dates."""
        symbol_x = get_test_symbol("SYMBOL_X")
        
        # Test both dates for SYMBOL_X
        for test_date in symbol_x.trading_days:
            quality = calculate_quality_for_historical_date(
                test_time_manager_with_db,
                test_db,
                symbol_x.symbol,
                "1m",
                test_date,
                actual_bars=390
            )
            
            assert quality == 100.0, f"Quality should be 100% for {test_date}"


@pytest.mark.integration
class TestBarDataGeneration:
    """Test synthetic bar data generation utilities."""
    
    def test_generate_perfect_bars(self, bar_data_generator):
        """Test generating bars with no gaps."""
        bars = bar_data_generator(
            symbol="TEST",
            target_date=date(2025, 1, 2),
            start_time=time(9, 30),
            end_time=time(16, 0),
            interval_minutes=1,
            missing_times=None
        )
        
        assert len(bars) == 390, "Should generate 390 1-minute bars"
        assert all(bar.symbol == "TEST" for bar in bars), "All bars should have correct symbol"
    
    def test_generate_bars_with_gaps(self, bar_data_generator):
        """Test generating bars with specified gaps."""
        bars = bar_data_generator(
            symbol="TEST",
            target_date=date(2025, 1, 2),
            start_time=time(9, 30),
            end_time=time(16, 0),
            interval_minutes=1,
            missing_times=["09:35", "09:36", "10:15"]
        )
        
        assert len(bars) == 387, "Should generate 387 bars (390 - 3 missing)"
    
    def test_gap_analyzer(self, bar_data_generator, gap_analyzer):
        """Test gap analysis utility."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        bars = bar_data_generator(
            symbol="TEST",
            target_date=date(2025, 1, 2),
            start_time=time(9, 30),
            end_time=time(16, 0),
            interval_minutes=1,
            missing_times=["09:35", "09:36"]
        )
        
        tz = ZoneInfo("America/New_York")
        analysis = gap_analyzer(
            bars,
            expected_start=datetime(2025, 1, 2, 9, 30, tzinfo=tz),
            expected_end=datetime(2025, 1, 2, 16, 0, tzinfo=tz),
            interval_minutes=1
        )
        
        assert analysis["total_expected"] == 390
        assert analysis["total_actual"] == 388
        assert analysis["missing_count"] == 2
        assert analysis["quality_percent"] == pytest.approx(99.49, rel=0.01)
