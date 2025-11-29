"""
TimeManager Tests
Comprehensive tests for time management and calendar operations
"""
import pytest
from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo

from app.managers.time_manager import TimeManager, reset_time_manager, get_time_manager
from app.managers.time_manager.models import TradingSession, MarketHoursConfig
from app.models.database import SessionLocal


@pytest.fixture
def time_manager():
    """Create a fresh TimeManager instance for each test"""
    reset_time_manager()
    # Create mock system manager
    class MockSystemManager:
        class Mode:
            value = "live"
        mode = Mode()
    
    tm = TimeManager(system_manager=MockSystemManager())
    yield tm
    reset_time_manager()


@pytest.fixture
async def db_session():
    """Create a database session for testing"""
    with SessionLocal() as session:
        yield session


class TestCurrentTime:
    """Test current time operations"""
    
    def test_get_current_time_default_timezone(self, time_manager):
        """Test getting current time in default timezone"""
        current = time_manager.get_current_time()
        assert current.tzinfo is not None
        assert isinstance(current, datetime)
    
    def test_get_current_time_utc(self, time_manager):
        """Test getting current time in UTC"""
        current = time_manager.get_current_time(timezone="UTC")
        assert current.tzinfo == ZoneInfo("UTC")
    
    def test_get_current_time_tokyo(self, time_manager):
        """Test getting current time in Tokyo timezone"""
        current = time_manager.get_current_time(timezone="Asia/Tokyo")
        assert current.tzinfo == ZoneInfo("Asia/Tokyo")
    
    def test_backtest_time_naive(self, time_manager):
        """Test setting backtest time with naive datetime"""
        # Switch to backtest mode
        time_manager._system_manager.mode.value = "backtest"
        
        # Set naive time (assumed ET)
        test_time = datetime(2024, 11, 25, 10, 30)
        time_manager.set_backtest_time(test_time)
        
        # Should be stored as UTC internally
        assert time_manager._backtest_time.tzinfo == ZoneInfo("UTC")
        
        # Get in ET should match original
        et_time = time_manager.get_current_time()
        assert et_time.hour == 10
        assert et_time.minute == 30
    
    def test_backtest_time_aware(self, time_manager):
        """Test setting backtest time with timezone-aware datetime"""
        time_manager._system_manager.mode.value = "backtest"
        
        # Set UTC time
        test_time = datetime(2024, 11, 25, 15, 30, tzinfo=ZoneInfo("UTC"))
        time_manager.set_backtest_time(test_time)
        
        # Get in ET (15:30 UTC = 10:30 ET)
        et_time = time_manager.get_current_time()
        assert et_time.hour == 10
        assert et_time.minute == 30
    
    def test_get_current_mode(self, time_manager):
        """Test getting current operation mode"""
        assert time_manager.get_current_mode() == "live"
        
        time_manager._system_manager.mode.value = "backtest"
        assert time_manager.get_current_mode() == "backtest"


class TestMarketSessions:
    """Test market session operations"""
    
    @pytest.mark.asyncio
    async def test_get_trading_session_regular_day(self, time_manager, db_session):
        """Test getting trading session for a regular trading day"""
        # Wednesday, November 27, 2024 (regular day)
        session = await time_manager.get_trading_session(
            db_session,
            date(2024, 11, 27),
            exchange="NYSE",
            asset_class="EQUITY"
        )
        
        assert session is not None
        assert session.is_trading_day is True
        assert session.is_holiday is False
        assert session.regular_open == time(9, 30)
        assert session.regular_close == time(16, 0)
        assert session.timezone == "America/New_York"
    
    @pytest.mark.asyncio
    async def test_get_trading_session_weekend(self, time_manager, db_session):
        """Test getting trading session for a weekend"""
        # Saturday, November 30, 2024
        session = await time_manager.get_trading_session(
            db_session,
            date(2024, 11, 30),
            exchange="NYSE",
            asset_class="EQUITY"
        )
        
        assert session is not None
        assert session.is_trading_day is False
        assert session.is_holiday is False
    
    @pytest.mark.asyncio
    async def test_trading_session_datetime_helpers(self, time_manager, db_session):
        """Test TradingSession datetime helper methods"""
        session = await time_manager.get_trading_session(
            db_session,
            date(2024, 11, 27),
            exchange="NYSE",
            asset_class="EQUITY"
        )
        
        # Test get_regular_open_datetime
        open_dt = session.get_regular_open_datetime()
        assert open_dt.tzinfo == ZoneInfo("America/New_York")
        assert open_dt.hour == 9
        assert open_dt.minute == 30
        
        # Test get_regular_open_utc
        open_utc = session.get_regular_open_utc()
        assert open_utc.tzinfo == ZoneInfo("UTC")
        assert open_utc.hour == 14  # 9:30 ET = 14:30 UTC (EST)
        assert open_utc.minute == 30


class TestMarketStatus:
    """Test market status checks"""
    
    @pytest.mark.asyncio
    async def test_is_market_open_regular_hours(self, time_manager, db_session):
        """Test checking if market is open during regular hours"""
        # 11/27/2024 at 10:30 AM ET (market open)
        timestamp = datetime(2024, 11, 27, 10, 30, tzinfo=ZoneInfo("America/New_York"))
        
        is_open = await time_manager.is_market_open(
            db_session,
            timestamp,
            exchange="NYSE",
            asset_class="EQUITY"
        )
        
        assert is_open is True
    
    @pytest.mark.asyncio
    async def test_is_market_open_after_hours(self, time_manager, db_session):
        """Test checking if market is open after hours"""
        # 11/27/2024 at 5:00 PM ET (market closed)
        timestamp = datetime(2024, 11, 27, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        
        is_open = await time_manager.is_market_open(
            db_session,
            timestamp,
            exchange="NYSE",
            asset_class="EQUITY"
        )
        
        assert is_open is False
    
    @pytest.mark.asyncio
    async def test_is_market_open_extended_hours(self, time_manager, db_session):
        """Test checking if market is open with extended hours"""
        # 11/27/2024 at 5:00 PM ET (post-market)
        timestamp = datetime(2024, 11, 27, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        
        is_open = await time_manager.is_market_open(
            db_session,
            timestamp,
            exchange="NYSE",
            asset_class="EQUITY",
            include_extended=True
        )
        
        assert is_open is True  # Post-market open until 8 PM
    
    @pytest.mark.asyncio
    async def test_is_trading_day(self, time_manager, db_session):
        """Test checking if date is a trading day"""
        # Regular day
        is_trading = await time_manager.is_trading_day(
            db_session,
            date(2024, 11, 27),
            exchange="NYSE"
        )
        assert is_trading is True
        
        # Weekend
        is_trading = await time_manager.is_trading_day(
            db_session,
            date(2024, 11, 30),  # Saturday
            exchange="NYSE"
        )
        assert is_trading is False
    
    @pytest.mark.asyncio
    async def test_get_session_type(self, time_manager, db_session):
        """Test getting session type"""
        # Regular hours
        timestamp = datetime(2024, 11, 27, 10, 30, tzinfo=ZoneInfo("America/New_York"))
        session_type = await time_manager.get_session_type(
            db_session, timestamp, "NYSE", "EQUITY"
        )
        assert session_type == "regular"
        
        # Pre-market
        timestamp = datetime(2024, 11, 27, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        session_type = await time_manager.get_session_type(
            db_session, timestamp, "NYSE", "EQUITY"
        )
        assert session_type == "pre_market"
        
        # Post-market
        timestamp = datetime(2024, 11, 27, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        session_type = await time_manager.get_session_type(
            db_session, timestamp, "NYSE", "EQUITY"
        )
        assert session_type == "post_market"
        
        # Closed
        timestamp = datetime(2024, 11, 27, 21, 0, tzinfo=ZoneInfo("America/New_York"))
        session_type = await time_manager.get_session_type(
            db_session, timestamp, "NYSE", "EQUITY"
        )
        assert session_type == "closed"


class TestTradingDateNavigation:
    """Test trading date navigation"""
    
    @pytest.mark.asyncio
    async def test_get_next_trading_date(self, time_manager, db_session):
        """Test getting next trading date"""
        # From Wednesday to Thursday
        next_date = await time_manager.get_next_trading_date(
            db_session,
            date(2024, 11, 27),  # Wednesday
            n=1,
            exchange="NYSE"
        )
        assert next_date == date(2024, 11, 29)  # Friday (skip Thanksgiving)
    
    @pytest.mark.asyncio
    async def test_get_next_trading_date_skip_weekend(self, time_manager, db_session):
        """Test getting next trading date skipping weekend"""
        next_date = await time_manager.get_next_trading_date(
            db_session,
            date(2024, 11, 29),  # Friday
            n=1,
            exchange="NYSE"
        )
        assert next_date == date(2024, 12, 2)  # Monday
    
    @pytest.mark.asyncio
    async def test_get_previous_trading_date(self, time_manager, db_session):
        """Test getting previous trading date"""
        prev_date = await time_manager.get_previous_trading_date(
            db_session,
            date(2024, 12, 2),  # Monday
            n=1,
            exchange="NYSE"
        )
        assert prev_date == date(2024, 11, 29)  # Friday
    
    @pytest.mark.asyncio
    async def test_count_trading_days(self, time_manager, db_session):
        """Test counting trading days in a range"""
        # November 2024 has ~21 trading days
        count = await time_manager.count_trading_days(
            db_session,
            date(2024, 11, 1),
            date(2024, 11, 30),
            exchange="NYSE"
        )
        assert count >= 19  # At least 19 (accounting for Thanksgiving)
        assert count <= 22
    
    @pytest.mark.asyncio
    async def test_get_trading_dates_in_range(self, time_manager, db_session):
        """Test getting list of trading dates"""
        dates = await time_manager.get_trading_dates_in_range(
            db_session,
            date(2024, 11, 25),
            date(2024, 11, 29),
            exchange="NYSE"
        )
        
        # Should include 11/25, 11/26, 11/27, 11/29 (skip Thanksgiving 11/28)
        assert len(dates) >= 3
        assert date(2024, 11, 27) in dates  # Wednesday
        assert date(2024, 11, 30) not in dates  # Saturday


class TestTimezoneConversion:
    """Test timezone conversion utilities"""
    
    def test_convert_timezone(self, time_manager):
        """Test converting between timezones"""
        et_time = datetime(2024, 11, 25, 10, 30, tzinfo=ZoneInfo("America/New_York"))
        
        # Convert to UTC
        utc_time = time_manager.convert_timezone(et_time, "UTC")
        assert utc_time.tzinfo == ZoneInfo("UTC")
        assert utc_time.hour == 15  # 10:30 ET = 15:30 UTC (EST)
        
        # Convert to Tokyo
        jst_time = time_manager.convert_timezone(et_time, "Asia/Tokyo")
        assert jst_time.tzinfo == ZoneInfo("Asia/Tokyo")
        assert jst_time.hour == 0  # Next day in Tokyo
    
    def test_to_utc(self, time_manager):
        """Test converting to UTC"""
        et_time = datetime(2024, 11, 25, 10, 30, tzinfo=ZoneInfo("America/New_York"))
        utc_time = time_manager.to_utc(et_time)
        
        assert utc_time.tzinfo == ZoneInfo("UTC")
        assert utc_time.hour == 15
    
    def test_to_market_timezone(self, time_manager):
        """Test converting to market timezone"""
        utc_time = datetime(2024, 11, 25, 15, 30, tzinfo=ZoneInfo("UTC"))
        market_time = time_manager.to_market_timezone(utc_time, "NYSE")
        
        assert market_time.hour == 10
        assert market_time.minute == 30
    
    def test_get_market_timezone(self, time_manager):
        """Test getting market timezone"""
        tz = time_manager.get_market_timezone("NYSE")
        assert tz == "America/New_York"
        
        tz = time_manager.get_market_timezone("NASDAQ")
        assert tz == "America/New_York"


class TestConfiguration:
    """Test market configuration"""
    
    @pytest.mark.asyncio
    async def test_register_market_hours(self, time_manager, db_session):
        """Test registering market hours configuration"""
        config = MarketHoursConfig(
            exchange="TEST_EXCHANGE",
            asset_class="EQUITY",
            timezone="America/Chicago",
            regular_open=time(8, 30),
            regular_close=time(15, 0)
        )
        
        await time_manager.register_market_hours(config)
        
        # Verify registration
        retrieved = await time_manager.get_market_config(
            db_session,
            "TEST_EXCHANGE",
            "EQUITY"
        )
        assert retrieved is not None
        assert retrieved.timezone == "America/Chicago"
        assert retrieved.regular_open == time(8, 30)
    
    @pytest.mark.asyncio
    async def test_get_market_config(self, time_manager, db_session):
        """Test getting market configuration"""
        config = await time_manager.get_market_config(
            db_session,
            "NYSE",
            "EQUITY"
        )
        
        assert config is not None
        assert config.exchange == "NYSE"
        assert config.asset_class == "EQUITY"
        assert config.timezone == "America/New_York"
        assert config.regular_open == time(9, 30)
        assert config.regular_close == time(16, 0)


class TestSingleton:
    """Test singleton behavior"""
    
    def test_singleton_pattern(self):
        """Test that get_time_manager returns same instance"""
        reset_time_manager()
        
        tm1 = get_time_manager()
        tm2 = get_time_manager()
        
        assert tm1 is tm2
        
        reset_time_manager()
    
    def test_reset_time_manager(self):
        """Test resetting the singleton"""
        tm1 = get_time_manager()
        reset_time_manager()
        tm2 = get_time_manager()
        
        assert tm1 is not tm2
        
        reset_time_manager()


# Run pytest with: pytest app/managers/time_manager/tests/test_time_manager.py -v
