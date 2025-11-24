# DataManager Test Suite

Comprehensive test suite for the DataManager module with focus on correctness, edge cases, and real-world scenarios.

## 🏗️ Architecture (2025-11)

All tests use **SystemManager** as the single source of truth for operation mode:

- **SystemManager owns mode** - Tests set mode via `system_manager.set_mode("live"|"backtest")`
- **DataManager from SystemManager** - Tests get DataManager via `system_manager.get_data_manager()`
- **No direct settings access** - Tests don't set `settings.SYSTEM_OPERATING_MODE` directly
- **Enforces production architecture** - Tests mirror real usage patterns

**Why this matters:**
- Prevents mode inconsistencies between components
- Ensures single source of truth (SystemManager.mode)
- Tests fail if architecture is violated
- TimeProvider requires SystemManager reference

## 📋 Test Framework Information

**Framework:** pytest (v7.4.3) with pytest-asyncio (v0.21.1)

**Test Source Directory:** `/home/yohannes/mismartera/backend/app/managers/data_manager/tests/`

**Test Execution Directory:** `/home/yohannes/mismartera/backend/`

## 🚀 Running Tests

### Quick Start

```bash
# From backend directory
cd /home/yohannes/mismartera/backend

# Run all DataManager tests
pytest app/managers/data_manager/tests/ -v -s

# Run specific test file
pytest app/managers/data_manager/tests/test_get_current_time.py -v -s

# Run with test runner script
./run_tests.sh
```

### Using Test Runner Script

```bash
# Interactive mode
./run_tests.sh

# Direct commands
./run_tests.sh all              # Run all tests
./run_tests.sh time             # Run get_current_time tests only
./run_tests.sh coverage         # Run with coverage report
```

### Running Specific Tests

```bash
# Run single test method
pytest app/managers/data_manager/tests/test_get_current_time.py::TestGetCurrentTime::test_01_live_mode_returns_current_system_time -v -s

# Run tests matching pattern
pytest app/managers/data_manager/tests/ -k "backtest" -v -s

# Run with minimal output
pytest app/managers/data_manager/tests/ -v

# Run with full output (see print statements)
pytest app/managers/data_manager/tests/ -v -s
```

## 📝 Test Files

### `test_get_current_time.py` - Time Management (20 tests)

Comprehensive test suite for `DataManager.get_current_time()` method.

**Architecture:** All tests use SystemManager fixture. Mode is set via `system_manager.set_mode()` and DataManager is obtained via `system_manager.get_data_manager()`.

**Test Coverage:**

1. ✅ **Live Mode System Time** - Verifies live mode returns current system time
2. ✅ **Uninitialized Backtest** - Checks ValueError when backtest time not set
3. ✅ **Backtest Simulated Time** - Validates backtest mode returns simulated time
4. ✅ **Mode Switching** - Tests Live → Backtest → Live transitions
5. ✅ **Time Advancement** - Verifies backtest time advances correctly
6. ✅ **Timezone Conversion** - Checks UTC to Eastern Time conversion
7. ✅ **Case Insensitivity** - Tests mode values are case-insensitive
8. ✅ **Invalid Mode Handling** - Validates graceful handling of invalid modes
9. ✅ **Naive Datetime** - Ensures returned datetime has no timezone info
10. ✅ **Time Persistence** - Verifies backtest time persists until changed
11. ✅ **DST Spring Forward** - Tests daylight saving time transitions
12. ✅ **DST Fall Back** - Tests DST fall back transitions
13. ✅ **Concurrent Access** - Validates thread-safe concurrent calls
14. ✅ **Stream Stopping (init_backtest)** - Checks streams stopped before init
15. ✅ **Stream Stopping (reset_clock)** - Checks streams stopped before reset
16. ✅ **Async Behavior** - Validates async methods require await
17. ✅ **Initialization Time** - Checks backtest initializes to market open
18. ✅ **TimeProvider Integration** - Validates delegation to TimeProvider
19. ✅ **Backtest Window** - Verifies time within backtest window
20. ✅ **Synchronous Method** - Confirms get_current_time() needs no await

### Test Output Example

```
============================= test session starts ==============================
platform linux -- Python 3.11.x, pytest-7.4.3, pluggy-1.x
collecting ... collected 20 items

test_get_current_time.py::TestGetCurrentTime::test_01_live_mode_returns_current_system_time 
================================================================================
STARTING NEW TEST
================================================================================
✓ Testing: Live mode returns current system time
  Current time in live mode: 2025-11-20 14:30:00.123456
  ✓ Live mode working correctly
PASSED

test_get_current_time.py::TestGetCurrentTime::test_02_backtest_mode_raises_error_when_uninitialized 
================================================================================
STARTING NEW TEST
================================================================================
✓ Testing: Backtest mode raises ValueError when uninitialized
  ✓ ValueError raised correctly for uninitialized backtest mode
PASSED
...
```

## 🎯 Test Categories

### Unit Tests
- Individual method behavior
- Edge case handling
- Error validation

### Integration Tests
- Mode switching
- TimeProvider integration
- Stream coordination

### Async Tests
- Concurrent access
- Async method validation
- Coroutine handling

## 📊 Coverage

To generate coverage reports:

```bash
# HTML report (opens in browser)
pytest app/managers/data_manager/tests/ --cov=app/managers/data_manager --cov-report=html
open htmlcov/index.html

# Terminal report
pytest app/managers/data_manager/tests/ --cov=app/managers/data_manager --cov-report=term

# Both
./run_tests.sh coverage
```

## 🔧 Configuration

### pytest.ini

Located in `/home/yohannes/mismartera/backend/pytest.ini`

Key configurations:
- Test discovery patterns
- Async mode settings
- Logging configuration
- Custom markers

### conftest.py

Shared fixtures and test utilities:
- `test_db_session` - In-memory SQLite database for isolated testing
- `system_manager` - Fresh SystemManager instance for each test (replaces `original_mode`)
- `sample_date` - Consistent test dates (2025-11-20)
- `market_open_time` - Market open time (9:30 AM ET)
- `market_close_time` - Market close time (4:00 PM ET)
- Event loop management for async tests

**SystemManager Fixture:**
```python
@pytest.fixture
def system_manager():
    """Create a SystemManager instance for tests."""
    from app.managers.system_manager import SystemManager, reset_system_manager
    
    reset_system_manager()  # Fresh instance
    sys_mgr = SystemManager()
    yield sys_mgr
    reset_system_manager()  # Cleanup
```

## 📚 Writing New Tests

### Test Template

```python
def test_XX_descriptive_name(self, system_manager):
    """TEST XX: One-line description of what this test validates"""
    print("✓ Testing: Human-readable description")
    
    # Setup - Use SystemManager to set mode
    system_manager.set_mode("live")
    dm = system_manager.get_data_manager()
    
    # Execute
    result = dm.get_current_time()
    
    # Assert
    assert result is not None, "Description of expected outcome"
    
    print(f"  Result: {result}")
    print("  ✓ Test passed message")
```

**Key Changes from Old Pattern:**
- ✅ Use `system_manager` fixture (not `original_mode`)
- ✅ Set mode via `system_manager.set_mode()`
- ✅ Get DataManager via `system_manager.get_data_manager()`
- ❌ Don't use `settings.SYSTEM_OPERATING_MODE` directly
- ❌ Don't instantiate `DataManager()` directly

### Async Test Template

```python
@pytest.mark.asyncio
async def test_XX_async_test(self, system_manager, test_db_session):
    """TEST XX: Description"""
    print("✓ Testing: Description")
    
    # Setup with SystemManager
    system_manager.set_mode("backtest")
    dm = system_manager.get_data_manager()
    
    # Initialize backtest
    await dm.init_backtest(test_db_session)
    
    # Test
    result = dm.get_current_time()
    assert result is not None
    
    print("  ✓ Passed")
```

**Mode Switching in Tests:**
```python
# Mode can only be changed when system is STOPPED
system_manager.stop()  # Required before mode change
system_manager.set_mode("backtest")

# For rapid testing, create fresh SystemManager
from app.managers.system_manager import reset_system_manager
reset_system_manager()
system_manager2 = SystemManager()
system_manager2.set_mode("live")
```

## 🐛 Debugging Tests

### Enable Debug Output

```bash
# See all print statements
pytest app/managers/data_manager/tests/ -v -s

# More verbose logging
pytest app/managers/data_manager/tests/ -v -s --log-cli-level=DEBUG

# Show local variables on failure
pytest app/managers/data_manager/tests/ -v -s --showlocals
```

### Run Single Test

```bash
pytest app/managers/data_manager/tests/test_get_current_time.py::TestGetCurrentTime::test_01_live_mode_returns_current_system_time -v -s
```

### Use pdb Debugger

```python
def test_something(self):
    import pdb; pdb.set_trace()  # Breakpoint
    # ... test code
```

## 📖 Best Practices

### General Testing

1. **One Assertion Per Test** - Each test should verify one specific behavior
2. **Descriptive Names** - Test names should describe what they verify
3. **Print Progress** - Use print statements to show what's being tested
4. **Clean Setup/Teardown** - Use fixtures for setup, avoid test interdependencies
5. **Mock External Dependencies** - Don't rely on external services in tests
6. **Test Edge Cases** - Include boundary conditions and error cases

### SystemManager Architecture

7. **Always use `system_manager` fixture** - Never set `settings.SYSTEM_OPERATING_MODE` directly
8. **Get DataManager from SystemManager** - Use `system_manager.get_data_manager()`
9. **Stop before mode changes** - Call `system_manager.stop()` before `set_mode()`
10. **Single source of truth** - All mode queries go through SystemManager
11. **Test will fail without SystemManager** - TimeProvider requires it, enforcing architecture

### Anti-Patterns to Avoid

❌ `settings.SYSTEM_OPERATING_MODE = "backtest"`  # Don't do this
❌ `dm = DataManager()`  # Don't instantiate directly
❌ Mixing SystemManager and settings  # Causes inconsistencies

✅ `system_manager.set_mode("backtest")`  # Correct
✅ `dm = system_manager.get_data_manager()`  # Correct
✅ Use SystemManager exclusively  # Single source of truth

### `test_volume_analytics.py` - Volume Analytics APIs (15 tests)

Comprehensive test suite for volume analytics methods.

**Test Coverage:**

1. ✅ **Average Volume Basic** - Multi-day average calculation
2. ✅ **Average Volume No Data** - Returns 0 for missing symbols
3. ✅ **Average Volume Single Day** - Single data point handling
4. ✅ **Average Volume Cache** - Caching behavior validation
5. ✅ **Average Volume Different Intervals** - 1m, 5m, 1D support
6. ✅ **Time-Specific Volume Basic** - Volume up to specific time
7. ✅ **Time-Specific Volume Market Open** - Edge case at 9:30 AM
8. ✅ **Time-Specific Volume Cache** - Caching mechanism
9. ✅ **Current Session Volume from DB** - Database query in backtest
10. ✅ **Current Session Volume from Tracker** - Real-time updates
11. ✅ **Current Session Volume Empty** - New session returns 0
12. ✅ **Current Session Volume Live API** - Alpaca API fallback
13. ✅ **Current Session Concurrent Updates** - Thread safety
14. ✅ **Volume Timezone Consistency** - Naive datetime handling
15. ✅ **Volume with Data Gaps** - Missing days handling

**APIs Tested:**
- `get_average_volume()` - Average daily volume over N days
- `get_time_specific_average_volume()` - Average volume up to time
- `get_current_session_volume()` - Real-time session volume

### `test_price_analytics.py` - Price Analytics APIs (15 tests)

Comprehensive test suite for price analytics methods.

**Test Coverage:**

1. ✅ **Historical High/Low Basic** - Multi-day calculation
2. ✅ **Historical 52-Week** - 252 trading days calculation
3. ✅ **Historical No Data** - Returns None for missing symbols
4. ✅ **Historical Single Price** - Single data point
5. ✅ **Historical Cache** - Caching behavior
6. ✅ **Historical Extreme Prices** - Large price movements
7. ✅ **Current Session High/Low from DB** - Database query
8. ✅ **Current Session High/Low from Tracker** - Real-time updates
9. ✅ **Current Session Empty** - New session returns None
10. ✅ **Current Session Live API** - Alpaca API integration
11. ✅ **Session Updates Real-Time** - Progressive updates
12. ✅ **Session Concurrent Updates** - Thread safety
13. ✅ **Price Precision** - Decimal precision maintenance
14. ✅ **Historical with Gaps** - Missing days handling
15. ✅ **Price Timezone Consistency** - Naive datetime handling

**APIs Tested:**
- `get_historical_high_low()` - High/low over N days/years
- `get_current_session_high_low()` - Real-time session extremes

### `test_snapshot_api.py` - Snapshot API (15 tests)

Comprehensive test suite for market snapshot functionality.

**Test Coverage:**

1. ✅ **Snapshot Live Mode Success** - Full snapshot retrieval
2. ✅ **Snapshot Backtest Unavailable** - Returns None in backtest
3. ✅ **Snapshot Invalid Symbol** - Invalid symbol handling
4. ✅ **Snapshot API Failure** - Connection error handling
5. ✅ **Snapshot Missing Trade Data** - Partial snapshot handling
6. ✅ **Snapshot Data Structure** - Structure validation
7. ✅ **Snapshot Timestamp Parsing** - ISO format validation
8. ✅ **Snapshot Price Precision** - Decimal precision
9. ✅ **Snapshot Concurrent Requests** - Multiple symbols
10. ✅ **Snapshot Extended Hours** - Pre/post market data
11. ✅ **Snapshot No Caching** - Always fresh data
12. ✅ **Snapshot Unsupported Provider** - Provider validation
13. ✅ **Snapshot Rate Limiting** - Rapid requests
14. ✅ **Snapshot Market Status** - Status indicators
15. ✅ **Snapshot Alpaca Fields** - Provider-specific data

**APIs Tested:**
- `get_snapshot()` - Live market snapshot from Alpaca

## 🎓 Next Steps

Future test files to create:
- `test_streaming.py` - Stream coordination tests
- `test_session_tracker.py` - Session tracking tests
- `test_backtest_coordinator.py` - Backtest stream merging tests

## 📞 Support

For questions or issues with tests:
1. Check test output for detailed error messages
2. Review the test documentation in each test file
3. Run with `-v -s --showlocals` for maximum debugging info
