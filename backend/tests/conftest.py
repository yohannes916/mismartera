"""Pytest Configuration and Shared Fixtures

This file is automatically loaded by pytest and makes all fixtures available to all tests.
"""
import pytest
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Import all fixture modules to register them
pytest_plugins = [
    "tests.fixtures.test_database",
    "tests.fixtures.test_time_manager",
    "tests.fixtures.synthetic_data",
    "tests.fixtures.test_parquet_data",  # NEW: Parquet test data fixtures
]


def pytest_configure(config):
    """Configure pytest with custom markers."""
    # Register custom markers
    config.addinivalue_line(
        "markers",
        "integration: Integration tests using test database (slower than unit tests)"
    )
    config.addinivalue_line(
        "markers",
        "unit: Unit tests with mocks only (fast)"
    )
    config.addinivalue_line(
        "markers",
        "slow: Slow-running tests (skip with -m 'not slow')"
    )
    config.addinivalue_line(
        "markers",
        "db: Tests requiring database (test or production)"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Auto-mark tests in unit/ directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Auto-mark tests in integration/ directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Auto-mark tests that use test_db fixture
        if "test_db" in item.fixturenames:
            item.add_marker(pytest.mark.db)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment before any tests run."""
    # This runs once per test session
    print("\n🔧 Setting up test environment...")
    
    yield
    
    # Teardown
    print("\n✅ Test environment cleaned up")


@pytest.fixture
def captured_logs(caplog):
    """Capture log messages during test."""
    return caplog
