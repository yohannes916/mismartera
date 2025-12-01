"""TimeManager Fixtures for Testing

Provides TimeManager instances configured to use test database.
"""
import pytest
from unittest.mock import Mock
from datetime import datetime

from app.managers.time_manager.api import TimeManager


@pytest.fixture
def test_time_manager_with_db(test_db):
    """Create TimeManager that uses test database.
    
    This TimeManager will query the test database for trading sessions
    instead of the production database.
    
    Args:
        test_db: Test database session fixture
    
    Returns:
        TimeManager instance configured for testing
    """
    # Create mock system_manager
    system_manager = Mock()
    system_manager.session_config = Mock()
    
    # Create TimeManager
    time_mgr = TimeManager(system_manager)
    
    # Override get_trading_session to use test_db
    original_method = time_mgr.get_trading_session
    
    def get_trading_session_from_test_db(session, target_date, exchange="NYSE"):
        """Override to use test_db instead of production database."""
        # Ignore the passed session, use test_db
        return test_db.query_trading_session(target_date, exchange)
    
    time_mgr.get_trading_session = get_trading_session_from_test_db
    
    # Set a fixed current time for testing
    test_current_time = datetime(2025, 1, 2, 12, 0)  # Noon on test day
    time_mgr._backtest_time = test_current_time
    
    return time_mgr


@pytest.fixture
def test_time_manager_simple():
    """Create simple TimeManager with mocked trading sessions.
    
    Lightweight alternative when you don't need actual database.
    """
    system_manager = Mock()
    time_mgr = TimeManager(system_manager)
    
    # Set a fixed time
    time_mgr._backtest_time = datetime(2025, 1, 2, 12, 0)
    
    return time_mgr
