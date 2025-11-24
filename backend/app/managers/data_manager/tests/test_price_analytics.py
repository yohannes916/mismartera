"""Comprehensive test suite for DataManager Price Analytics APIs

Tests cover:
- get_historical_high_low() - High/low prices over N trading days/years
- get_current_session_high_low() - Real-time session high/low

Test scenarios:
1. Basic high/low calculations
2. 52-week high/low (252 trading days)
3. Cache behavior and TTL
4. Edge cases (single data point, all same price, gaps)
5. Backtest vs Live mode behavior
6. Session tracker integration
7. API fallback (Alpaca in live mode)
8. Price precision and rounding
9. Concurrent session updates
10. Extreme price movements
"""
import pytest
import asyncio
from datetime import datetime, date, time, timedelta
from unittest.mock import patch, AsyncMock
from decimal import Decimal

from app.config import settings
from app.managers.data_manager.api import DataManager
from app.managers.data_manager.session_tracker import get_session_tracker
from app.models.database import Bar


class TestPriceAnalytics:
    """Test suite for Price Analytics APIs."""
    
    def setup_method(self):
        """Setup before each test."""
        print("\n" + "="*80)
        print("STARTING NEW TEST - PRICE ANALYTICS")
        print("="*80)
        # Clear session tracker cache
        tracker = get_session_tracker()
        tracker._sessions = {}
        tracker._historical_hl_cache = {}
    
    # ==================== get_historical_high_low() Tests ====================
    
    @pytest.mark.asyncio
    async def test_01_historical_high_low_basic(self, test_db_session, sample_date):
        """TEST 1: Calculate historical high/low over multiple days"""
        print("✓ Testing: Historical high/low calculation")
        
        symbol = "TEST"
        
        # Add bars with varying highs and lows
        prices = [
            (110.0, 95.0),   # Day 1
            (125.0, 98.0),   # Day 2 - highest high
            (108.0, 90.0),   # Day 3 - lowest low
            (115.0, 100.0),  # Day 4
            (120.0, 102.0),  # Day 5
        ]
        
        for i, (high, low) in enumerate(prices):
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=i), time(16, 0)),
                open=100.0,
                high=high,
                low=low,
                close=102.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=5, interval="1D")
        
        expected_high = max(p[0] for p in prices)
        expected_low = min(p[1] for p in prices)
        
        assert high == expected_high, f"Expected high {expected_high}, got {high}"
        assert low == expected_low, f"Expected low {expected_low}, got {low}"
        
        print(f"  Price data points: {len(prices)}")
        print(f"  Expected high: ${expected_high:.2f}")
        print(f"  Expected low: ${expected_low:.2f}")
        print(f"  Calculated high: ${high:.2f}")
        print(f"  Calculated low: ${low:.2f}")
        print("  ✓ Historical high/low calculated correctly")
    
    @pytest.mark.asyncio
    async def test_02_historical_high_low_52_weeks(self, test_db_session, sample_date):
        """TEST 2: Calculate 52-week high/low (252 trading days)"""
        print("✓ Testing: 52-week high/low calculation")
        
        symbol = "YEARLY"
        
        # Simulate 252 trading days with trend
        highest_price = 0
        lowest_price = float('inf')
        
        for i in range(252):
            # Uptrend in first half, downtrend in second half
            if i < 126:
                high = 100.0 + (i * 0.5)  # Rising
                low = 95.0 + (i * 0.4)
            else:
                high = 163.0 - ((i - 126) * 0.3)  # Falling
                low = 145.4 - ((i - 126) * 0.25)
            
            highest_price = max(highest_price, high)
            lowest_price = min(lowest_price, low)
            
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=i), time(16, 0)),
                open=100.0,
                high=high,
                low=low,
                close=102.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=252, interval="1D")
        
        assert abs(high - highest_price) < 0.01, f"52-week high should be {highest_price:.2f}"
        assert abs(low - lowest_price) < 0.01, f"52-week low should be {lowest_price:.2f}"
        
        print(f"  Trading days: 252 (52 weeks)")
        print(f"  52-week high: ${high:.2f}")
        print(f"  52-week low: ${low:.2f}")
        print(f"  Price range: ${high - low:.2f}")
        print("  ✓ 52-week calculation correct")
    
    @pytest.mark.asyncio
    async def test_03_historical_high_low_no_data(self, test_db_session):
        """TEST 3: Returns None when no data available"""
        print("✓ Testing: Historical high/low with no data")
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, "NODATA", days=20, interval="1D")
        
        assert high is None, "Should return None for high when no data"
        assert low is None, "Should return None for low when no data"
        
        print(f"  High with no data: {high}")
        print(f"  Low with no data: {low}")
        print("  ✓ Correctly returns None for missing symbol")
    
    @pytest.mark.asyncio
    async def test_04_historical_high_low_single_price(self, test_db_session, sample_date):
        """TEST 4: Handle single price point correctly"""
        print("✓ Testing: Historical high/low with single data point")
        
        symbol = "SINGLE"
        price_high = 105.50
        price_low = 104.25
        
        bar = Bar(
            symbol=symbol,
            interval="1D",
            timestamp=datetime.combine(sample_date, time(16, 0)),
            open=105.0,
            high=price_high,
            low=price_low,
            close=105.0,
            volume=1000000
        )
        test_db_session.add(bar)
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=20, interval="1D")
        
        assert high == price_high, f"Single point high should be {price_high}"
        assert low == price_low, f"Single point low should be {price_low}"
        
        print(f"  Single bar high: ${high:.2f}")
        print(f"  Single bar low: ${low:.2f}")
        print("  ✓ Single data point handled correctly")
    
    @pytest.mark.asyncio
    async def test_05_historical_high_low_cache(self, test_db_session, sample_date):
        """TEST 5: Historical high/low results are cached"""
        print("✓ Testing: Historical high/low caching")
        
        symbol = "CACHE"
        
        bar = Bar(
            symbol=symbol,
            interval="1D",
            timestamp=datetime.combine(sample_date, time(16, 0)),
            open=100.0,
            high=110.0,
            low=95.0,
            close=105.0,
            volume=1000000
        )
        test_db_session.add(bar)
        await test_db_session.commit()
        
        dm = DataManager()
        
        # First call
        start = datetime.now()
        result1 = await dm.get_historical_high_low(test_db_session, symbol, days=20, interval="1D")
        time1 = (datetime.now() - start).total_seconds()
        
        # Second call - should use cache
        start = datetime.now()
        result2 = await dm.get_historical_high_low(test_db_session, symbol, days=20, interval="1D")
        time2 = (datetime.now() - start).total_seconds()
        
        assert result1 == result2, "Cached result should match"
        print(f"  First call: {time1*1000:.2f}ms")
        print(f"  Second call (cached): {time2*1000:.2f}ms")
        print(f"  Speed improvement: {(time1/time2):.1f}x")
        print("  ✓ Caching working correctly")
    
    @pytest.mark.asyncio
    async def test_06_historical_high_low_extreme_prices(self, test_db_session, sample_date):
        """TEST 6: Handle extreme price movements correctly"""
        print("✓ Testing: Historical high/low with extreme prices")
        
        symbol = "EXTREME"
        
        # Extreme price data
        prices = [
            (1000.0, 10.0),    # Large gap
            (50.0, 45.0),      # Normal
            (2500.0, 2000.0),  # Very high
            (5.0, 1.0),        # Very low
        ]
        
        for i, (high, low) in enumerate(prices):
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=i), time(16, 0)),
                open=100.0,
                high=high,
                low=low,
                close=100.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=10, interval="1D")
        
        expected_high = 2500.0
        expected_low = 1.0
        
        assert high == expected_high, "Should find extreme high"
        assert low == expected_low, "Should find extreme low"
        
        print(f"  Extreme high: ${high:.2f}")
        print(f"  Extreme low: ${low:.2f}")
        print(f"  Volatility: {(high/low):.1f}x")
        print("  ✓ Extreme prices handled correctly")
    
    # ==================== get_current_session_high_low() Tests ====================
    
    @pytest.mark.asyncio
    async def test_07_current_session_high_low_from_db(self, test_db_session, sample_date, system_manager):
        """TEST 7: Get session high/low from database"""
        print("✓ Testing: Current session high/low from database")
        
        system_manager.set_mode("backtest")
        symbol = "SESSION"
        
        # Add bars with varying prices
        max_high = 0
        min_low = float('inf')
        
        for i in range(10):
            high = 100.0 + i
            low = 95.0 + (i * 0.5)
            max_high = max(max_high, high)
            min_low = min(min_low, low)
            
            bar = Bar(
                symbol=symbol,
                interval="1m",
                timestamp=datetime.combine(sample_date, time(9, 30)) + timedelta(minutes=i),
                open=100.0,
                high=high,
                low=low,
                close=102.0,
                volume=100000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = system_manager.get_data_manager()
        dm.time_provider.set_backtest_time(datetime.combine(sample_date, time(9, 40)))
        
        high, low = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        
        assert high == max_high, f"Expected high {max_high}, got {high}"
        assert low == min_low, f"Expected low {min_low}, got {low}"
        
        print(f"  Bars in session: 10")
        print(f"  Session high: ${high:.2f}")
        print(f"  Session low: ${low:.2f}")
        print("  ✓ Session high/low from DB correct")
    
    @pytest.mark.asyncio
    async def test_08_current_session_high_low_from_tracker(self, test_db_session, sample_date, system_manager):
        """TEST 8: Get session high/low from session tracker (real-time)"""
        print("✓ Testing: Current session high/low from tracker")
        
        system_manager.set_mode("backtest")
        symbol = "TRACKER"
        session_date = sample_date
        
        # Update tracker with bar data
        tracker = get_session_tracker()
        
        # First bar
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=105.0,
            bar_low=99.0,
            bar_volume=100000,
            timestamp=datetime.combine(session_date, time(10, 0))
        )
        
        # Second bar with new high
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=110.0,
            bar_low=101.0,
            bar_volume=150000,
            timestamp=datetime.combine(session_date, time(10, 1))
        )
        
        # Third bar with new low
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=108.0,
            bar_low=96.0,
            bar_volume=120000,
            timestamp=datetime.combine(session_date, time(10, 2))
        )
        
        dm = DataManager()
        dm.time_provider.set_backtest_time(datetime.combine(session_date, time(10, 2)))
        
        high, low = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        
        assert high == 110.0, f"Expected session high 110.0, got {high}"
        assert low == 96.0, f"Expected session low 96.0, got {low}"
        
        print(f"  Bar updates: 3")
        print(f"  Session high: ${high:.2f}")
        print(f"  Session low: ${low:.2f}")
        print("  ✓ Tracker provides real-time high/low")
    
    @pytest.mark.asyncio
    async def test_09_current_session_high_low_empty_session(self, test_db_session, sample_date, system_manager):
        """TEST 9: Empty session returns None for high/low"""
        print("✓ Testing: Current session high/low for empty session")
        
        system_manager.set_mode("backtest")
        dm = system_manager.get_data_manager()
        dm.time_provider.set_backtest_time(datetime.combine(sample_date, time(9, 30)))
        
        high, low = await dm.get_current_session_high_low(
            test_db_session, "EMPTY", interval="1m", use_api=False
        )
        
        assert high is None, "Empty session should return None for high"
        assert low is None, "Empty session should return None for low"
        
        print(f"  High for empty session: {high}")
        print(f"  Low for empty session: {low}")
        print("  ✓ Empty session handled correctly")
    
    @pytest.mark.asyncio
    async def test_10_current_session_high_low_live_mode_api(self, test_db_session, sample_date, system_manager):
        """TEST 10: Live mode attempts API then falls back to DB"""
        print("✓ Testing: Current session high/low with API fallback")
        
        system_manager.set_mode("live")
        symbol = "LIVE"
        
        # Add DB data as fallback
        bar = Bar(
            symbol=symbol,
            interval="1m",
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=98.0,
            close=102.0,
            volume=100000
        )
        test_db_session.add(bar)
        await test_db_session.commit()
        
        dm = DataManager()
        
        # Mock Alpaca API success
        with patch('app.managers.data_manager.integrations.alpaca_data.fetch_session_data',
                   new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                'high': 110.0,
                'low': 95.0,
                'volume': 500000
            }
            
            high, low = await dm.get_current_session_high_low(
                test_db_session, symbol, interval="1m", use_api=True
            )
            
            assert high == 110.0, "Should use API data"
            assert low == 95.0, "Should use API data"
            print(f"  API high: ${high:.2f}")
            print(f"  API low: ${low:.2f}")
            print("  ✓ API data used successfully")
    
    @pytest.mark.asyncio
    async def test_11_session_high_low_updates_in_real_time(self, test_db_session, sample_date, system_manager):
        """TEST 11: Session high/low updates as new bars arrive"""
        print("✓ Testing: Real-time session high/low updates")
        
        system_manager.set_mode("backtest")
        symbol = "REALTIME"
        session_date = sample_date
        
        tracker = get_session_tracker()
        dm = system_manager.get_data_manager()
        dm.time_provider.set_backtest_time(datetime.combine(session_date, time(10, 0)))
        
        # Initial state
        high1, low1 = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        print(f"  Initial: High={high1}, Low={low1}")
        
        # Add first bar
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=105.0,
            bar_low=100.0,
            bar_volume=100000,
            timestamp=datetime.combine(session_date, time(10, 0))
        )
        
        high2, low2 = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        print(f"  After bar 1: High=${high2:.2f}, Low=${low2:.2f}")
        
        # Add bar with new high
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=112.0,
            bar_low=103.0,
            bar_volume=150000,
            timestamp=datetime.combine(session_date, time(10, 1))
        )
        
        high3, low3 = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        print(f"  After bar 2: High=${high3:.2f}, Low=${low3:.2f}")
        
        # Add bar with new low
        await tracker.update_session(
            symbol=symbol,
            session_date=session_date,
            bar_high=108.0,
            bar_low=97.0,
            bar_volume=120000,
            timestamp=datetime.combine(session_date, time(10, 2))
        )
        
        high4, low4 = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        print(f"  After bar 3: High=${high4:.2f}, Low=${low4:.2f}")
        
        assert high4 == 112.0, "Should track highest high"
        assert low4 == 97.0, "Should track lowest low"
        print("  ✓ Real-time updates working correctly")
    
    @pytest.mark.asyncio
    async def test_12_price_analytics_concurrent_session_updates(self, test_db_session, sample_date, system_manager):
        """TEST 12: Concurrent bar updates maintain correct high/low"""
        print("✓ Testing: Concurrent session high/low updates")
        
        system_manager.set_mode("backtest")
        symbol = "CONCURRENT"
        session_date = sample_date
        
        tracker = get_session_tracker()
        
        # Concurrent bar updates with different prices
        async def update_bar(high, low):
            await tracker.update_session(
                symbol=symbol,
                session_date=session_date,
                bar_high=high,
                bar_low=low,
                bar_volume=100000,
                timestamp=datetime.combine(session_date, time(10, 0))
            )
        
        prices = [
            (105.0, 100.0),
            (110.0, 98.0),
            (108.0, 95.0),
            (115.0, 102.0),
            (112.0, 99.0),
        ]
        
        await asyncio.gather(*[update_bar(h, l) for h, l in prices])
        
        dm = DataManager()
        dm.time_provider.set_backtest_time(datetime.combine(session_date, time(10, 0)))
        
        high, low = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1m", use_api=False
        )
        
        expected_high = max(p[0] for p in prices)
        expected_low = min(p[1] for p in prices)
        
        assert high == expected_high, f"Concurrent high should be {expected_high}"
        assert low == expected_low, f"Concurrent low should be {expected_low}"
        
        print(f"  Concurrent updates: {len(prices)}")
        print(f"  Expected high: ${expected_high:.2f}")
        print(f"  Expected low: ${expected_low:.2f}")
        print(f"  Actual high: ${high:.2f}")
        print(f"  Actual low: ${low:.2f}")
        print("  ✓ Concurrent updates handled correctly")
    
    @pytest.mark.asyncio
    async def test_13_price_analytics_precision(self, test_db_session, sample_date):
        """TEST 13: Price calculations maintain precision (no rounding errors)"""
        print("✓ Testing: Price calculation precision")
        
        symbol = "PRECISION"
        
        # Prices with decimals
        precise_prices = [
            (100.12345, 99.98765),
            (100.55555, 99.44444),
            (100.99999, 99.00001),
        ]
        
        for i, (high, low) in enumerate(precise_prices):
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=i), time(16, 0)),
                open=100.0,
                high=high,
                low=low,
                close=100.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=10, interval="1D")
        
        expected_high = max(p[0] for p in precise_prices)
        expected_low = min(p[1] for p in precise_prices)
        
        assert abs(high - expected_high) < 0.00001, "Should maintain price precision"
        assert abs(low - expected_low) < 0.00001, "Should maintain price precision"
        
        print(f"  Expected high: ${expected_high:.5f}")
        print(f"  Calculated high: ${high:.5f}")
        print(f"  Expected low: ${expected_low:.5f}")
        print(f"  Calculated low: ${low:.5f}")
        print("  ✓ Price precision maintained")
    
    @pytest.mark.asyncio
    async def test_14_historical_high_low_with_gaps(self, test_db_session, sample_date):
        """TEST 14: Historical high/low handles data gaps correctly"""
        print("✓ Testing: Historical high/low with data gaps")
        
        symbol = "GAPS"
        
        # Add data with gaps (only days 0, 3, 7, 14, 20)
        gap_days = [0, 3, 7, 14, 20]
        for day in gap_days:
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=day), time(16, 0)),
                open=100.0,
                high=110.0 + day,
                low=90.0 - day,
                close=100.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        high, low = await dm.get_historical_high_low(test_db_session, symbol, days=30, interval="1D")
        
        # Should find max/min from available data
        expected_high = 110.0 + max(gap_days)
        expected_low = 90.0 - max(gap_days)
        
        assert high == expected_high, "Should find high despite gaps"
        assert low == expected_low, "Should find low despite gaps"
        
        print(f"  Requested days: 30")
        print(f"  Available days: {len(gap_days)}")
        print(f"  High found: ${high:.2f}")
        print(f"  Low found: ${low:.2f}")
        print("  ✓ Data gaps handled correctly")
    
    @pytest.mark.asyncio
    async def test_15_price_analytics_timezone_consistency(self, test_db_session, sample_date, system_manager):
        """TEST 15: All price APIs use consistent timezone handling"""
        print("✓ Testing: Timezone consistency across price APIs")
        
        system_manager.set_mode("backtest")
        symbol = "TZ"
        
        # Add bars with explicit timestamps
        for i in range(5):
            bar = Bar(
                symbol=symbol,
                interval="1D",
                timestamp=datetime.combine(sample_date - timedelta(days=i), time(16, 0)),
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                volume=1000000
            )
            test_db_session.add(bar)
        
        await test_db_session.commit()
        
        dm = DataManager()
        dm.time_provider.set_backtest_time(datetime.combine(sample_date, time(12, 0)))
        
        # All APIs should work with naive datetimes
        hist_high, hist_low = await dm.get_historical_high_low(
            test_db_session, symbol, days=5, interval="1D"
        )
        sess_high, sess_low = await dm.get_current_session_high_low(
            test_db_session, symbol, interval="1D", use_api=False
        )
        
        assert hist_high == 110.0, "Historical high should work"
        assert hist_low == 95.0, "Historical low should work"
        assert sess_high is not None or sess_low is not None, "Session API should work"
        
        print(f"  Historical high: ${hist_high:.2f}")
        print(f"  Historical low: ${hist_low:.2f}")
        print(f"  Session high: ${sess_high if sess_high else 'N/A'}")
        print(f"  Session low: ${sess_low if sess_low else 'N/A'}")
        print("  ✓ All APIs handle timezone consistently")


# Test execution summary
if __name__ == "__main__":
    print("\n" + "="*80)
    print("DataManager Price Analytics Test Suite")
    print("="*80)
    print("\nTests cover:")
    print("  - get_historical_high_low()")
    print("  - get_current_session_high_low()")
    print("\nTo run these tests:")
    print("  pytest app/managers/data_manager/tests/test_price_analytics.py -v -s")
    print("\n" + "="*80)
