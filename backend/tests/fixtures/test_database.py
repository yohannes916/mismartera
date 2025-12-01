"""Test Database Fixtures

Provides in-memory storage for trading sessions during tests.
Uses simple dictionaries instead of SQL database for speed and simplicity.
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, date, time as time_obj
from typing import Dict

from app.managers.time_manager.models import TradingSession


# In-memory storage for test trading sessions
_test_trading_sessions: Dict[tuple, TradingSession] = {}


@pytest.fixture(scope="session")
def test_db_with_data():
    """Load synthetic trading sessions into memory (session-scoped).
    
    Loads data once per test session for efficiency.
    Returns dict of trading sessions keyed by (date, exchange).
    """
    global _test_trading_sessions
    _test_trading_sessions.clear()
    
    # Load market hours data
    data_file = Path(__file__).parent.parent / "data/market_hours.json"
    
    if not data_file.exists():
        raise FileNotFoundError(f"Market hours data not found: {data_file}")
    
    with open(data_file) as f:
        market_hours_data = json.load(f)
    
    # Create TradingSession objects
    for date_str, hours in market_hours_data.items():
        trading_date = date.fromisoformat(date_str)
        
        # Parse times (handle None for holidays)
        regular_open = (
            datetime.strptime(hours["regular_open"], "%H:%M:%S").time()
            if hours["regular_open"] else None
        )
        regular_close = (
            datetime.strptime(hours["regular_close"], "%H:%M:%S").time()
            if hours["regular_close"] else None
        )
        pre_market_open = (
            datetime.strptime(hours["pre_market_open"], "%H:%M:%S").time()
            if hours.get("pre_market_open") else None
        )
        post_market_close = (
            datetime.strptime(hours["post_market_close"], "%H:%M:%S").time()
            if hours.get("post_market_close") else None
        )
        
        session = TradingSession(
            date=trading_date,
            exchange=hours["exchange"],
            asset_class="equity",
            timezone=hours["timezone"],
            regular_open=regular_open,
            regular_close=regular_close,
            pre_market_open=pre_market_open,
            post_market_close=post_market_close,
            is_holiday=hours["is_holiday"],
            is_early_close=hours["is_early_close"],
            holiday_name=hours.get("holiday_name")
        )
        
        # Store by (date, exchange) key
        key = (trading_date, hours["exchange"])
        _test_trading_sessions[key] = session
    
    return _test_trading_sessions


@pytest.fixture
def test_db(test_db_with_data):
    """Provide access to test trading sessions.
    
    Simulates a database session but uses in-memory dict.
    """
    # Create a simple mock session object
    class MockSession:
        def __init__(self, sessions_dict):
            self._sessions = sessions_dict
        
        def query_trading_session(self, target_date: date, exchange: str = "NYSE"):
            """Query trading session by date and exchange."""
            key = (target_date, exchange)
            return self._sessions.get(key)
        
        def get_all_sessions(self):
            """Get all trading sessions."""
            return list(self._sessions.values())
        
        def rollback(self):
            """No-op for mock session."""
            pass
        
        def close(self):
            """No-op for mock session."""
            pass
    
    session = MockSession(test_db_with_data)
    yield session
    session.close()


@pytest.fixture
def test_db_stats(test_db):
    """Get statistics about test database contents."""
    all_sessions = test_db.get_all_sessions()
    
    stats = {
        "trading_sessions": len(all_sessions),
        "regular_days": sum(
            1 for s in all_sessions 
            if not s.is_holiday and not s.is_early_close
        ),
        "early_close_days": sum(1 for s in all_sessions if s.is_early_close),
        "holidays": sum(1 for s in all_sessions if s.is_holiday),
    }
    return stats
