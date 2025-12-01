"""Test Fixtures Package

Provides reusable test fixtures for all test modules.

Fixtures:
- test_database: Test database with synthetic data
- test_time_manager: TimeManager configured for testing
- synthetic_data: Bar data generation utilities
- test_symbols: Pre-defined test symbols with known characteristics
- test_parquet_data: Parquet test data with isolated storage (NEW)
"""

# Export main fixtures for easy importing
from tests.fixtures.test_database import (
    test_db_with_data,
    test_db,
    test_db_stats
)

from tests.fixtures.test_time_manager import (
    test_time_manager_with_db,
    test_time_manager_simple
)

from tests.fixtures.synthetic_data import (
    bar_data_generator,
    bar_data_generator_from_symbol,
    create_dataframe_from_bars,
    gap_analyzer
)

from tests.fixtures.test_symbols import (
    TEST_SYMBOLS,
    get_test_symbol,
    get_all_test_dates
)

from tests.fixtures.test_parquet_data import (
    isolated_parquet_storage,
    parquet_data_builder,
    perfect_1s_data,
    perfect_1m_data,
    multi_symbol_data,
    date_range_data,
    ParquetTestDataBuilder
)

__all__ = [
    # Database fixtures
    "test_db_with_data",
    "test_db",
    "test_db_stats",
    # TimeManager fixtures
    "test_time_manager_with_db",
    "test_time_manager_simple",
    # Data generation fixtures
    "bar_data_generator",
    "bar_data_generator_from_symbol",
    "create_dataframe_from_bars",
    "gap_analyzer",
    # Test symbols
    "TEST_SYMBOLS",
    "get_test_symbol",
    "get_all_test_dates",
    # Parquet fixtures (NEW)
    "isolated_parquet_storage",
    "parquet_data_builder",
    "perfect_1s_data",
    "perfect_1m_data",
    "multi_symbol_data",
    "date_range_data",
    "ParquetTestDataBuilder",
]
