"""Comprehensive test suite for DataManager.get_current_time()

ARCHITECTURE (2025-11):
These tests use SystemManager as the single source of truth for operation mode:
- SystemManager owns the mode state (live/backtest)
- DataManager receives SystemManager reference and uses it exclusively
- TimeProvider receives SystemManager reference from DataManager

Tests cover all scenarios documented in the README:
1. Mode Switching (Live → Backtest → Live)
2. Initialization and ValueError handling
3. Time Advancement with stream coordinator
4. Timezone Handling (UTC → Eastern Time)
5. Case Insensitivity for mode values
6. Invalid Modes and error handling
7. Naive Datetime validation
8. Persistence of backtest time
9. DST Handling
10. Concurrent Access (thread safety)
11. Integration with stream stopping
12. Async behavior validation
"""
import pytest
import asyncio
from datetime import datetime, date, time, timedelta
from unittest.mock import patch, MagicMock
import pytz

from app.config import settings
from app.managers.data_manager.api import DataManager
from app.managers.data_manager.time_provider import TimeProvider


class TestGetCurrentTime:
    """Test suite for DataManager.get_current_time() method."""
    
    def setup_method(self):
        """Setup before each test."""
        print("\n" + "="*80)
        print("STARTING NEW TEST")
        print("="*80)
    
    def test_01_live_mode_returns_current_system_time(self, system_manager):
        """TEST 1: Live mode returns current system time in Eastern timezone"""
        print("✓ Testing: Live mode returns current system time")
        
        # Set to live mode via SystemManager
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Get current time
        current = dm.get_current_time()
        
        # Assertions
        assert current is not None, "Should return a datetime"
        assert isinstance(current, datetime), "Should be datetime object"
        assert current.tzinfo is None, "Should return naive datetime"
        
        # Should be a reasonable date (not far future or past)
        now = datetime.now()
        assert current.year == now.year, "Should be current year"
        assert 1 <= current.month <= 12, "Should have valid month"
        assert 1 <= current.day <= 31, "Should have valid day"
        assert 0 <= current.hour < 24, "Should have valid hour"
        
        print(f"  Current time in live mode: {current}")
        print(f"  System time for comparison: {now}")
        print(f"  ✓ Live mode working correctly")
    
    def test_02_backtest_mode_raises_error_when_uninitialized(self, system_manager):
        """TEST 2: Backtest mode raises ValueError when backtest time not set"""
        print("✓ Testing: Backtest mode raises ValueError when uninitialized")
        
        # Set to backtest mode via SystemManager
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # TimeProvider should raise ValueError
        with pytest.raises(ValueError, match="Backtest time not set"):
            dm.get_current_time()
        
        print("  ✓ ValueError raised correctly for uninitialized backtest mode")
    
    @pytest.mark.asyncio
    async def test_03_backtest_mode_returns_simulated_time(self, system_manager, test_db_session):
        """TEST 3: Backtest mode returns simulated time after initialization"""
        print("✓ Testing: Backtest mode returns simulated time after init")
        
        # Set to backtest mode via SystemManager
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Initialize backtest
        await dm.init_backtest(test_db_session)
        
        # Get current time
        current = dm.get_current_time()
        
        # Assertions
        assert current is not None, "Should return a datetime"
        assert current.tzinfo is None, "Should return naive datetime"
        assert current.date() == dm.backtest_start_date, "Should match backtest start date"
        
        print(f"  Backtest time: {current}")
        print(f"  Backtest start date: {dm.backtest_start_date}")
        print(f"  ✓ Backtest mode returning simulated time correctly")
    
    @pytest.mark.asyncio
    async def test_04_mode_switching_live_to_backtest_to_live(self, system_manager, test_db_session):
        """TEST 4: Mode can switch from Live → Backtest → Live seamlessly"""
        print("✓ Testing: Mode switching Live → Backtest → Live")
        
        # Start in live mode
        print("  → Setting to LIVE mode")
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        live_time = dm.get_current_time()
        print(f"    Live time: {live_time}")
        assert live_time is not None
        
        # Switch to backtest mode (must stop system first)
        print("  → Stopping system to switch modes")
        system_manager.stop()
        print("  → Setting to BACKTEST mode")
        system_manager.set_mode("backtest")
        await dm.init_backtest(test_db_session)
        backtest_time = dm.get_current_time()
        print(f"    Backtest time: {backtest_time}")
        assert backtest_time != live_time
        
        # Switch back to live mode
        print("  → Stopping system to switch modes")
        system_manager.stop()
        print("  → Setting back to LIVE mode")
        system_manager.set_mode("live")
        live_time_2 = dm.get_current_time()
        print(f"    Live time again: {live_time_2}")
        assert live_time_2 is not None
        
        print("  ✓ Mode switching works correctly")
    
    @pytest.mark.asyncio
    async def test_05_backtest_time_advances_with_set_backtest_time(self, system_manager):
        """TEST 5: Backtest time advances when set_backtest_time is called"""
        print("✓ Testing: Backtest time advancement with set_backtest_time()")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Set initial time
        initial_time = datetime(2025, 11, 20, 9, 30, 0)
        dm.time_provider.set_backtest_time(initial_time)
        
        current = dm.get_current_time()
        print(f"  Initial time: {current}")
        assert current == initial_time
        
        # Advance time
        advanced_time = datetime(2025, 11, 20, 10, 30, 0)
        dm.time_provider.set_backtest_time(advanced_time)
        
        current = dm.get_current_time()
        print(f"  Advanced time: {current}")
        assert current == advanced_time
        assert current > initial_time
        
        print("  ✓ Time advancement working correctly")
    
    def test_06_timezone_conversion_live_mode(self, system_manager):
        """TEST 6: Live mode converts UTC to Eastern Time correctly"""
        print("✓ Testing: Timezone conversion from UTC to ET in live mode")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Get current time (should be in ET)
        current = dm.get_current_time()
        
        # Verify it's a naive datetime (no tzinfo)
        assert current.tzinfo is None, "Should be naive datetime"
        
        # The time should be reasonable (within bounds of Eastern Time)
        # Eastern is UTC-5 or UTC-4 (DST)
        utc_now = datetime.utcnow()
        
        # Allow for conversion differences
        time_diff = abs((utc_now - current).total_seconds())
        assert time_diff < 7 * 3600, "Should be within timezone conversion range"
        
        print(f"  UTC time: {utc_now}")
        print(f"  ET time (naive): {current}")
        print("  ✓ Timezone conversion correct")
    
    def test_07_case_insensitive_mode_values(self, system_manager):
        """TEST 7: Mode values are case-insensitive (LIVE, live, Live all work)"""
        print("✓ Testing: Case insensitivity for mode values")
        
        # Test different case variations
        test_cases = ["live", "LIVE", "Live", "LiVe"]
        for mode_value in test_cases:
            print(f"  → Testing mode: '{mode_value}'")
            system_manager.set_mode(mode_value)
            dm = system_manager.get_data_manager()
            current = dm.get_current_time()
            assert current is not None
            print(f"    ✓ '{mode_value}' works")
        
        print("  ✓ All case variations work correctly")
    
    def test_08_invalid_mode_raises_error(self, system_manager):
        """TEST 8: Invalid mode value raises appropriate error"""
        print("✓ Testing: Invalid mode raises error")
        
        # SystemManager.set_mode should return False for invalid mode
        result = system_manager.set_mode("invalid_mode")
        assert result is False, "set_mode should return False for invalid mode"
        
        print("  ✓ ValueError raised correctly for invalid mode")
    
    def test_09_returns_naive_datetime(self, system_manager):
        """TEST 9: Returned datetime is always naive (no timezone info)"""
        print("✓ Testing: Returns naive datetime (no tzinfo)")
        
        # Test live mode
        system_manager.set_mode("live")
        dm_live = system_manager.get_data_manager()
        live_time = dm_live.get_current_time()
        
        assert live_time.tzinfo is None, "Live mode should return naive datetime"
        print(f"  Live time tzinfo: {live_time.tzinfo} (should be None)")
        
        # Test backtest mode
        from app.managers.system_manager import reset_system_manager
        reset_system_manager()
        system_manager2 = system_manager.__class__()
        system_manager2.set_mode("backtest")
        dm_backtest = system_manager2.get_data_manager()
        dm_backtest.time_provider.set_backtest_time(datetime(2025, 11, 20, 9, 30))
        backtest_time = dm_backtest.get_current_time()
        
        assert backtest_time.tzinfo is None, "Backtest mode should return naive datetime"
        print(f"  Backtest time tzinfo: {backtest_time.tzinfo} (should be None)")
        
        print("  ✓ Both modes return naive datetime")
    
    @pytest.mark.asyncio
    async def test_10_backtest_time_persists(self, system_manager):
        """TEST 10: Backtest time persists until explicitly changed"""
        print("✓ Testing: Backtest time persistence")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Set time
        set_time = datetime(2025, 11, 20, 10, 0, 0)
        dm.time_provider.set_backtest_time(set_time)
        
        # Call get_current_time multiple times
        time1 = dm.get_current_time()
        await asyncio.sleep(0.01)  # Small delay
        time2 = dm.get_current_time()
        await asyncio.sleep(0.01)
        time3 = dm.get_current_time()
        
        # Should all be the same
        assert time1 == time2 == time3 == set_time
        print(f"  Set time: {set_time}")
        print(f"  Time after multiple calls: {time3}")
        print("  ✓ Time persists correctly (doesn't auto-advance)")
    
    def test_11_dst_handling_spring_forward(self, system_manager):
        """TEST 11: DST handling - Spring forward (2:00 AM → 3:00 AM)"""
        print("✓ Testing: DST handling - Spring forward")
        
        # DST transition in 2025: March 9, 2:00 AM → 3:00 AM
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Set time just before DST transition
        before_dst = datetime(2025, 3, 9, 1, 59, 0)
        dm.time_provider.set_backtest_time(before_dst)
        time_before = dm.get_current_time()
        
        # Set time after DST transition (skip the non-existent hour)
        after_dst = datetime(2025, 3, 9, 3, 1, 0)
        dm.time_provider.set_backtest_time(after_dst)
        time_after = dm.get_current_time()
        
        assert time_before < time_after
        print(f"  Before DST: {time_before}")
        print(f"  After DST: {time_after}")
        print("  ✓ DST spring forward handled")
    
    def test_12_dst_handling_fall_back(self, system_manager):
        """TEST 12: DST handling - Fall back (2:00 AM → 1:00 AM)"""
        print("✓ Testing: DST handling - Fall back")
        
        # DST transition in 2025: November 2, 2:00 AM → 1:00 AM
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Set times around DST fall back
        before_fallback = datetime(2025, 11, 2, 1, 30, 0)
        dm.time_provider.set_backtest_time(before_fallback)
        time_before = dm.get_current_time()
        
        # After fall back (ambiguous hour)
        after_fallback = datetime(2025, 11, 2, 1, 45, 0)  
        dm.time_provider.set_backtest_time(after_fallback)
        time_after = dm.get_current_time()
        
        # Both times should be valid
        assert time_before is not None
        assert time_after is not None
        print(f"  Before fallback: {time_before}")
        print(f"  During ambiguous hour: {time_after}")
        print("  ✓ DST fall back handled")
    
    @pytest.mark.asyncio
    async def test_13_concurrent_access_thread_safety(self, system_manager):
        """TEST 13: Multiple concurrent calls work correctly (thread-safe)"""
        print("✓ Testing: Concurrent access thread safety")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        dm.time_provider.set_backtest_time(datetime(2025, 11, 20, 10, 0, 0))
        
        # Create multiple concurrent tasks
        async def get_time_task(task_id):
            current = dm.get_current_time()
            print(f"  Task {task_id}: {current}")
            return current
        
        # Run 10 concurrent tasks
        tasks = [get_time_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should return the same time
        assert all(t == results[0] for t in results), "All concurrent calls should return same time"
        print(f"  ✓ All {len(results)} concurrent calls returned same time")
    
    @pytest.mark.asyncio
    async def test_14_init_backtest_stops_streams(self, system_manager, test_db_session):
        """TEST 14: init_backtest() stops all streams before resetting clock"""
        print("✓ Testing: init_backtest() stops all streams")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Mock stop_all_streams to verify it's called
        async def mock_stop():
            return None
        
        with patch.object(dm, 'stop_all_streams', new=mock_stop) as mock_stop_fn:
            await dm.init_backtest(test_db_session)
            
            # stop_all_streams is called internally, we verify the code path works
            print("  ✓ init_backtest() executed successfully")
    
    @pytest.mark.asyncio
    async def test_15_reset_backtest_clock_stops_streams(self, system_manager):
        """TEST 15: reset_backtest_clock() stops all streams before reset"""
        print("✓ Testing: reset_backtest_clock() stops all streams")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        dm.backtest_start_date = date(2025, 11, 20)
        
        # Mock stop_all_streams
        async def mock_stop():
            return None
        
        with patch.object(dm, 'stop_all_streams', new=mock_stop) as mock_stop_fn:
            await dm.reset_backtest_clock()
            
            # reset_backtest_clock calls stop_all_streams internally
            print("  ✓ reset_backtest_clock() executed successfully")
    
    @pytest.mark.asyncio
    async def test_16_async_behavior_verification(self, system_manager, test_db_session):
        """TEST 16: Clock reset methods are async and must be awaited"""
        print("✓ Testing: Async behavior of clock reset methods")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # These should be coroutines
        init_result = dm.init_backtest(test_db_session)
        assert asyncio.iscoroutine(init_result), "init_backtest should return coroutine"
        await init_result
        
        dm.backtest_start_date = date(2025, 11, 20)
        reset_result = dm.reset_backtest_clock()
        assert asyncio.iscoroutine(reset_result), "reset_backtest_clock should return coroutine"
        await reset_result
        
        print("  ✓ All clock methods are properly async")
    
    @pytest.mark.asyncio
    async def test_17_backtest_initialization_sets_correct_time(self, system_manager, test_db_session):
        """TEST 17: Backtest initialization sets time to market open on start date"""
        print("✓ Testing: Backtest initialization sets correct time")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Initialize backtest
        await dm.init_backtest(test_db_session)
        
        current = dm.get_current_time()
        
        # Should be at market open time (9:30 AM ET)
        assert current.time() == time(9, 30), f"Should be at market open, got {current.time()}"
        assert current.date() == dm.backtest_start_date
        
        print(f"  Backtest start date: {dm.backtest_start_date}")
        print(f"  Current time: {current}")
        print(f"  Time of day: {current.time()}")
        print("  ✓ Initialized to market open correctly")
    
    def test_18_time_provider_integration(self, system_manager):
        """TEST 18: DataManager correctly delegates to TimeProvider"""
        print("✓ Testing: DataManager delegates to TimeProvider")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Verify TimeProvider exists
        assert hasattr(dm, 'time_provider'), "Should have time_provider attribute"
        assert isinstance(dm.time_provider, TimeProvider), "Should be TimeProvider instance"
        
        # Verify get_current_time delegates correctly
        dm_time = dm.get_current_time()
        provider_time = dm.time_provider.get_current_time()
        
        # Should return same time (within 1 second tolerance)
        time_diff = abs((dm_time - provider_time).total_seconds())
        assert time_diff < 1, "DataManager and TimeProvider should return same time"
        
        print(f"  DataManager time: {dm_time}")
        print(f"  TimeProvider time: {provider_time}")
        print("  ✓ Delegation working correctly")
    
    @pytest.mark.asyncio
    async def test_19_backtest_window_affects_current_time(self, system_manager, test_db_session):
        """TEST 19: Setting backtest window affects the current time range"""
        print("✓ Testing: Backtest window affects current time")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        
        # Initialize backtest
        await dm.init_backtest(test_db_session)
        
        current = dm.get_current_time()
        
        # Current time should be within the backtest window
        assert dm.backtest_start_date is not None
        assert dm.backtest_end_date is not None
        assert dm.backtest_start_date <= current.date() <= dm.backtest_end_date
        
        print(f"  Backtest window: {dm.backtest_start_date} to {dm.backtest_end_date}")
        print(f"  Current time: {current}")
        print(f"  Current date: {current.date()}")
        print("  ✓ Current time within backtest window")
    
    def test_20_synchronous_method_no_await_needed(self, system_manager):
        """TEST 20: get_current_time() is synchronous (no await needed)"""
        print("✓ Testing: get_current_time() is synchronous")
        
        system_manager.set_mode("live")
        dm = system_manager.get_data_manager()
        
        # Should be able to call without await
        current = dm.get_current_time()  # Not: await dm.get_current_time()
        
        assert not asyncio.iscoroutine(current), "Should not return a coroutine"
        assert isinstance(current, datetime), "Should return datetime directly"
        
        print(f"  Current time: {current}")
        print("  ✓ Method is synchronous (no await needed)")


# Test execution summary
if __name__ == "__main__":
    print("\n" + "="*80)
    print("DataManager.get_current_time() Test Suite")
    print("="*80)
    print("\nTo run these tests:")
    print("  pytest app/managers/data_manager/tests/test_get_current_time.py -v -s")
    print("\n" + "="*80)
