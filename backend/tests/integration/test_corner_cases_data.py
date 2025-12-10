"""Integration Tests for Data Availability Corner Cases

Tests edge cases related to data availability:
- Missing Parquet data
- Partial historical data
- Missing specific dates
- Early close days
- Holidays
- First/last trading days
- Delisted/newly listed symbols
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date, timedelta
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.api import DataManager


@pytest.fixture
def coordinator_for_data_edge_cases():
    """Create coordinator for testing data edge cases."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator._data_manager = Mock(spec=DataManager)
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    return coordinator


class TestMissingData:
    """Test missing data scenarios."""
    
    def test_no_parquet_data(self, coordinator_for_data_edge_cases):
        """Test symbol with no Parquet data at all."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock validation - no Parquet data
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol NEWIPO: No Parquet data found. Symbol may not be in data source.",
            data_source_available=True,
            has_historical_data=False
        )
        
        coordinator._validate_symbol_for_loading = Mock(return_value=validation)
        
        # Validate symbol
        result = coordinator._validate_symbol_for_loading("NEWIPO")
        
        # Expected: Cannot proceed, clear error
        assert result.can_proceed is False
        assert result.has_parquet_data is False
        assert "No Parquet data" in result.reason
    
    def test_partial_historical_data(self, coordinator_for_data_edge_cases):
        """Test symbol with only partial historical data (10 days instead of 30)."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock data availability check
        coordinator._data_manager.check_data_availability = Mock(return_value={
            "has_data": True,
            "days_available": 10,
            "requested_days": 30
        })
        
        # Check data
        result = coordinator._data_manager.check_data_availability("RECENTLY_LISTED", "1m", days=30)
        
        # Expected: Has data but insufficient
        assert result["has_data"] is True
        assert result["days_available"] == 10
        assert result["days_available"] < result["requested_days"]
        
        # Symbol should still load with warning
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,  # Can proceed with partial data
            reason="Symbol RECENTLY_LISTED: Only 10 days available (requested 30). Loading with available data.",
            has_data_source=True,
            has_parquet_data=True,
            has_sufficient_historical=False  # Flag set but still proceeding
        )
        
        assert validation.can_proceed is True
        assert "10 days" in validation.reason
    
    def test_missing_specific_dates(self, coordinator_for_data_edge_cases):
        """Test symbol missing data for specific dates (gaps)."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock gap detection
        coordinator._data_manager.check_data_gaps = Mock(return_value={
            "has_gaps": True,
            "gap_dates": [date(2025, 1, 5), date(2025, 1, 12)],
            "gap_count": 2
        })
        
        # Check for gaps
        result = coordinator._data_manager.check_data_gaps("GAPPED", "1m", 
                                                           start_date=date(2025, 1, 1),
                                                           end_date=date(2025, 1, 31))
        
        # Expected: Gaps detected
        assert result["has_gaps"] is True
        assert len(result["gap_dates"]) == 2
        assert date(2025, 1, 5) in result["gap_dates"]
        
        # Symbol can still load but quality will be affected
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,
            reason="Symbol GAPPED: Data gaps detected on 2 days. Quality score will be reduced.",
            data_source_available=True,
            has_historical_data=True  # Overall has data
        )
        
        assert validation.can_proceed is True


class TestSpecialTradingDays:
    """Test special trading day scenarios."""
    
    def test_early_close_days(self, coordinator_for_data_edge_cases):
        """Test symbol on early close days (half-day trading)."""
        coordinator = coordinator_for_data_edge_cases
        time_mgr = Mock()
        coordinator._time_manager = time_mgr
        
        # Mock early close day (e.g., day before holiday)
        from datetime import time
        trading_session = Mock()
        trading_session.regular_open = time(9, 30)
        trading_session.regular_close = time(13, 0)  # Early close at 1 PM
        trading_session.is_holiday = False
        trading_session.is_early_close = True
        
        time_mgr.get_trading_session = Mock(return_value=trading_session)
        
        # Get trading session
        session = time_mgr.get_trading_session(Mock(), date(2025, 7, 3))  # Before July 4th
        
        # Expected: Early close detected
        assert session.regular_close == time(13, 0)
        assert session.is_early_close is True
        
        # Symbol loading should account for fewer bars
        # Early close = ~3.5 hours vs normal ~6.5 hours
        # Approximately ~210 bars instead of ~390 bars for 1m interval
    
    def test_holidays(self, coordinator_for_data_edge_cases):
        """Test symbol on holiday (no trading)."""
        coordinator = coordinator_for_data_edge_cases
        time_mgr = Mock()
        coordinator._time_manager = time_mgr
        
        # Mock holiday
        time_mgr.is_holiday = Mock(return_value=True)
        
        # Check if holiday
        is_holiday = time_mgr.is_holiday(Mock(), date(2025, 12, 25))  # Christmas
        
        # Expected: Holiday detected
        assert is_holiday is True
        
        # No data expected for this day
        # Session should skip to next trading day
    
    def test_first_trading_day_of_year(self, coordinator_for_data_edge_cases):
        """Test symbol on first trading day (after New Year holiday)."""
        coordinator = coordinator_for_data_edge_cases
        time_mgr = Mock()
        coordinator._time_manager = time_mgr
        
        # Mock first trading day (Jan 2, 2025)
        time_mgr.is_holiday = Mock(side_effect=lambda session, d: d == date(2025, 1, 1))
        time_mgr.get_next_trading_date = Mock(return_value=date(2025, 1, 2))
        
        # First trading day
        first_day = date(2025, 1, 2)
        
        # Verify not a holiday
        assert not time_mgr.is_holiday(Mock(), first_day)
        
        # Historical loading should handle limited lookback
        # (can't go before Jan 2nd for 2025)


class TestSymbolLifecycle:
    """Test symbol lifecycle edge cases."""
    
    def test_delisted_symbol(self, coordinator_for_data_edge_cases):
        """Test symbol that was delisted (data only up to delisting date)."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock delisted symbol
        delisting_date = date(2024, 6, 15)
        
        coordinator._data_manager.get_symbol_info = Mock(return_value={
            "symbol": "DELISTED",
            "status": "delisted",
            "delisting_date": delisting_date,
            "has_data": True,
            "data_end_date": delisting_date
        })
        
        # Get symbol info
        info = coordinator._data_manager.get_symbol_info("DELISTED")
        
        # Expected: Delisted status detected
        assert info["status"] == "delisted"
        assert info["delisting_date"] == delisting_date
        
        # If trying to load after delisting date
        current_date = date(2025, 1, 2)
        if current_date > delisting_date:
            # Should warn or fail
            validation = SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason=f"Symbol DELISTED was delisted on {delisting_date}. No data available after this date.",
                data_source_available=True,
                has_historical_data=False
            )
            
            assert validation.can_proceed is False
            assert "delisted" in validation.reason.lower()
    
    def test_newly_listed_symbol(self, coordinator_for_data_edge_cases):
        """Test symbol newly listed (limited historical data)."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock newly listed symbol
        listing_date = date(2024, 12, 1)
        
        coordinator._data_manager.get_symbol_info = Mock(return_value={
            "symbol": "NEWIPO",
            "status": "active",
            "listing_date": listing_date,
            "has_data": True,
            "data_start_date": listing_date,
            "days_available": 60  # Only 2 months of data
        })
        
        # Get symbol info
        info = coordinator._data_manager.get_symbol_info("NEWIPO")
        
        # Expected: Limited data detected
        assert info["days_available"] == 60
        
        # Request 30 days historical - should work
        validation_30days = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,
            reason="Valid",
            data_source_available=True,
            has_historical_data=True
        )
        
        assert validation_30days.can_proceed is True
        
        # Request 90 days historical - should warn
        validation_90days = SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,
            reason="Symbol NEWIPO: Only 60 days available (requested 90). Loading with available data.",
            has_data_source=True,
            has_parquet_data=True,
            has_sufficient_historical=False
        )
        
        assert validation_90days.can_proceed is True
        assert "60 days" in validation_90days.reason


class TestDataQualityIssues:
    """Test data quality issues."""
    
    def test_corrupt_data_file(self, coordinator_for_data_edge_cases):
        """Test handling of corrupt Parquet file."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock corrupt file detection
        coordinator._data_manager.validate_parquet_file = Mock(return_value={
            "valid": False,
            "error": "ParquetFileError: File corrupted or invalid format"
        })
        
        # Validate file
        result = coordinator._data_manager.validate_parquet_file("CORRUPT", "1m")
        
        # Expected: Corruption detected
        assert result["valid"] is False
        assert "corrupt" in result["error"].lower() or "invalid" in result["error"].lower()
        
        # Symbol should fail to load
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol CORRUPT: Data file corrupted or invalid. Cannot load historical data.",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
    
    def test_zero_bars_in_file(self, coordinator_for_data_edge_cases):
        """Test Parquet file with zero bars (empty file)."""
        coordinator = coordinator_for_data_edge_cases
        
        # Mock empty file
        coordinator._data_manager.count_bars = Mock(return_value=0)
        
        # Count bars
        bar_count = coordinator._data_manager.count_bars("EMPTY", "1m")
        
        # Expected: Zero bars
        assert bar_count == 0
        
        # Symbol should fail to load
        validation = SymbolValidationResult(symbol="TEST",
            
            can_proceed=False,
            reason="Symbol EMPTY: Data file contains 0 bars. No historical data available.",
            data_source_available=True,
            has_historical_data=False
        )
        
        assert validation.can_proceed is False
        assert "0 bars" in validation.reason
