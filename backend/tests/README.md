# Test Infrastructure Documentation

## Overview

Comprehensive testing infrastructure with three tiers:
1. **Unit Tests** - Fast, isolated tests with mocks
2. **Integration Tests** - Real database with synthetic data
3. **E2E Tests** - Full system workflows (future)

---

## Directory Structure

```
tests/
├── fixtures/                    # Shared test fixtures
│   ├── __init__.py             # Fixture exports
│   ├── test_database.py        # Test database setup
│   ├── test_time_manager.py    # TimeManager fixtures
│   ├── test_symbols.py         # Symbol definitions
│   ├── synthetic_data.py       # Bar data generation
│   └── stream_test_data.py     # Stream determination scenarios
├── data/                        # Static test data
│   ├── market_hours.json       # Trading hours/holidays (used by test_database)
│   └── bar_data/               # (Reserved for future Parquet data)
├── session_configs/             # Test session configs
│   └── test_perfect.json       # Perfect data config (example only)
├── unit/                        # Unit tests (mocks only)
│   ├── test_quality_helpers.py
│   ├── test_stream_determination.py  # Stream determination logic
│   ├── test_scanner_base.py    # Scanner base classes (NEW)
│   └── test_scanner_manager.py # Scanner manager (NEW)
├── integration/                 # Integration tests (test DB)
│   ├── test_quality_calculation_flow.py
│   ├── test_quality_with_database.py
│   ├── test_stream_determination_with_db.py  # Stream determination + DB
│   └── test_scanner_integration.py  # Scanner with real components (NEW)
├── e2e/                         # End-to-end tests
│   ├── __init__.py
│   └── test_scanner_e2e.py     # Full scanner lifecycle (NEW)
├── conftest.py                  # Pytest configuration
└── README.md                    # This file
```

---

## Test Database

### Philosophy

- **In-Memory SQLite** - Fast, isolated, no disk I/O
- **Synthetic Data** - Predictable, reproducible results
- **Controlled Scenarios** - Test corner cases systematically
- **Reusable Fixtures** - Same infrastructure for all modules

### Test Symbols

Pre-defined symbols with known characteristics:

| Symbol | Description | Scenario |
|--------|-------------|----------|
| `SYMBOL_X` | Perfect data, no gaps | 100% quality baseline |
| `SYMBOL_Y` | Small gaps (3-5 bars) | ~99% quality |
| `SYMBOL_Z` | Early close day | Half-day trading |
| `SYMBOL_W` | Holiday | Market closed |
| `SYMBOL_V` | Large gap (2 hours) | ~69% quality |

### Market Hours Data

Static trading hours in `data/market_hours.json`:
- Regular days (9:30 AM - 4:00 PM)
- Early closes (9:30 AM - 1:00 PM)
- Holidays (market closed)

---

## Running Tests

### All Tests
```bash
# Run everything
pytest tests/ -v

# With coverage
pytest tests/ --cov=app/threads/quality --cov-report=html
```

### By Test Type
```bash
# Unit tests only (fast, mocks only)
pytest tests/unit/ -v

# Integration tests only (test database)
pytest tests/integration/ -v -m integration

# Specific test file
pytest tests/integration/test_quality_with_database.py -v
```

### By Marker
```bash
# Only fast unit tests
pytest -m unit -v

# Skip slow tests
pytest -m "not slow" -v

# Only database tests
pytest -m db -v
```

### VS Code
Use F5 with these launch configurations:
- "Tests: All Quality Tests"
- "Tests: Quality Unit Tests"
- "Tests: Quality Integration Tests"
- "Tests: All Backend Tests"

---

## Using Test Fixtures

### Test Database

```python
def test_with_database(test_db, test_time_manager_with_db):
    """Integration test using test database."""
    # test_db: SQLAlchemy session with synthetic data
    # test_time_manager_with_db: TimeManager using test_db
    
    quality = calculate_quality_for_historical_date(
        test_time_manager_with_db,
        test_db,
        "SYMBOL_X",
        "1m",
        date(2025, 1, 2),
        actual_bars=390
    )
    
    assert quality == 100.0
```

### Test Symbols

```python
from tests.fixtures.test_symbols import get_test_symbol

def test_with_symbol():
    """Use pre-defined test symbol."""
    symbol_x = get_test_symbol("SYMBOL_X")
    
    # Access properties
    assert symbol_x.bars_per_day == 390
    assert symbol_x.expected_quality == 100.0
    
    # Get actual bars for date
    actual = symbol_x.get_actual_bars_for_date(date(2025, 1, 2))
```

### Bar Data Generation

```python
def test_with_synthetic_bars(bar_data_generator):
    """Generate synthetic bar data."""
    bars = bar_data_generator(
        symbol="TEST",
        target_date=date(2025, 1, 2),
        start_time=time(9, 30),
        end_time=time(16, 0),
        interval_minutes=1,
        missing_times=["09:35", "10:15"]  # Create gaps
    )
    
    assert len(bars) == 388  # 390 - 2 missing
```

### Gap Analysis

```python
def test_gap_analysis(bar_data_generator, gap_analyzer):
    """Analyze gaps in bar data."""
    bars = bar_data_generator(...)
    
    analysis = gap_analyzer(
        bars,
        expected_start=datetime(...),
        expected_end=datetime(...),
        interval_minutes=1
    )
    
    assert analysis["quality_percent"] == 99.49
    assert analysis["missing_count"] == 2
```

---

## Adding New Tests

### Unit Test (with Mocks)

```python
# tests/unit/test_my_module.py
import pytest
from unittest.mock import Mock

def test_my_function():
    """Unit test with mocks."""
    mock_time_mgr = Mock()
    # ... test logic ...
```

**When to use:**
- Testing pure logic
- Need maximum speed
- No database required

### Integration Test (with Test DB)

```python
# tests/integration/test_my_module_with_db.py
import pytest

@pytest.mark.integration
def test_with_database(test_db, test_time_manager_with_db):
    """Integration test with test database."""
    # ... test logic using real database ...
```

**When to use:**
- Testing component interaction
- Need real database behavior
- Verify SQL queries
- Test TimeManager integration

---

## Test Data Maintenance

### Adding New Symbols

Edit `tests/fixtures/test_symbols.py`:

```python
"SYMBOL_NEW": TestSymbol(
    symbol="SYMBOL_NEW",
    description="Your description",
    trading_days=[date(2025, 1, 2)],
    bars_per_day=390,
    missing_bars={...},
    expected_quality=100.0
)
```

### Adding New Trading Days

Edit `tests/data/market_hours.json`:

```json
{
  "2025-01-06": {
    "regular_open": "09:30:00",
    "regular_close": "16:00:00",
    "is_holiday": false,
    "is_early_close": false,
    ...
  }
}
```

### Adding Session Configs (Future)

Session configs are currently managed programmatically in test code rather than as separate JSON files.

If needed in the future, create `tests/session_configs/test_my_scenario.json`:

```json
{
  "session_name": "test_my_scenario",
  "data_streams": [...],
  "session_data_config": {...}
}
```

**Note:** `test_perfect.json` exists as an example but is not currently used by tests.

---

## Best Practices

### DO ✅
- Use test database for integration tests
- Use mocks for unit tests
- Test one thing per test
- Use descriptive test names
- Verify against test symbols
- Check database stats
- Use pytest fixtures

### DON'T ❌
- Mix unit and integration tests
- Use production database
- Hardcode dates or times
- Test multiple things in one test
- Skip error cases
- Forget to clean up (fixtures handle this)

---

## Performance

### Speed Comparison

| Test Type | Count | Duration | Per Test |
|-----------|-------|----------|----------|
| Unit (mocks) | 80 | ~0.7s | ~9ms |
| Integration (test DB) | 53 | ~1.0s | ~19ms |
| **Total** | **133** | **~1.7s** | **~13ms** |

**Breakdown by Module:**
- Quality Helpers: 36 tests (unit) + 19 tests (integration) = 55 tests
- Stream Determination: 44 tests (unit) + 21 tests (integration) = 65 tests
- Quality Flow: 13 tests (integration)

### Why Fast?

1. **In-memory SQLite** - No disk I/O
2. **Session-scoped fixtures** - Data loaded once
3. **Transaction rollback** - Fast cleanup
4. **Minimal data** - Only what's needed

---

## Troubleshooting

### Test Database Not Loading

```python
# Check database stats
def test_debug(test_db_stats):
    print(test_db_stats)
```

### Fixture Not Found

```python
# Make sure conftest.py loads fixtures
pytest_plugins = [
    "tests.fixtures.test_database",
    ...
]
```

### TimeManager Not Using Test DB

```python
# Use test_time_manager_with_db, not test_time_manager_simple
def test_my_test(test_time_manager_with_db):  # ✅ Correct
    ...

def test_my_test(test_time_manager_simple):   # ❌ Wrong for DB tests
    ...
```

---

## Stream Determination Tests (NEW)

### Overview

Comprehensive test suite for the stream determination architecture (Phase 5, December 2025).

**Test Files:**
- `tests/unit/test_stream_determination.py` (44 tests)
- `tests/integration/test_stream_determination_with_db.py` (21 tests)
- `tests/fixtures/stream_test_data.py` (10 test scenarios)

**Total:** 65 tests, all passing in ~0.36s

### What's Tested

#### Unit Tests (44 tests)

1. **Interval Parsing** (9 tests)
   - Parse 1s, 1m, 1d, 5s, 5m intervals
   - Parse quotes and ticks special cases
   - Invalid format handling
   - DB storage capability flags

2. **Stream Decisions** (8 tests)
   - Stream smallest (1s > 1m > 1d priority)
   - Generate all other intervals
   - Quote handling (live: stream, backtest: generate)
   - Error cases (no base interval)
   - Ticks ignored

3. **Historical Decisions** (10 tests)
   - Load from DB if available
   - Generate with fallback logic
   - Sub-minute: only from 1s
   - Minute: prefer 1m, fallback 1s
   - Day: prefer 1d → 1m → 1s fallback chain
   - Error cases

4. **Generation Priority** (5 tests)
   - 5s → ["1s"]
   - 5m, 15m → ["1m", "1s"]
   - 5d → ["1d", "1m", "1s"]

5. **Gap Filling** (5 tests)
   - Can fill with 100% source quality
   - Cannot fill with <100%
   - Source must be smaller than target
   - Valid derivation checks

6. **Completeness Checks** (7 tests)
   - 100% complete → generate
   - <100% complete → skip
   - Expected count calculations

#### Integration Tests (21 tests)

1. **Stream Determination with DB** (8 tests)
   - Perfect 1s, 1m, 1d data scenarios
   - Both 1s and 1m available
   - All intervals available
   - No base interval error
   - Quote handling (live vs backtest)

2. **Historical Loading with DB** (6 tests)
   - Load from DB when available
   - Generate 5m from 1m
   - Generate 5m from 1s (fallback)
   - Generate 1d from 1m
   - Fallback chain for 5d
   - Error when no source

3. **Gap Filling with DB** (4 tests)
   - Fill 1m from complete 1s (60 bars)
   - Cannot fill with partial 1s
   - Fill 1d from complete 1m (390 bars)
   - Cannot fill with partial 1m

4. **Completeness Enforcement** (3 tests)
   - Skip aggregation with incomplete data
   - Succeed with complete data
   - Completeness calculations

### Test Scenarios

**File:** `tests/fixtures/stream_test_data.py`

Pre-defined scenarios for deterministic testing:

| Scenario | Description | 1s | 1m | 1d | Expected Stream |
|----------|-------------|----|----|-----|-----------------|
| `perfect_1s` | Complete 1s data | ✅ | ❌ | ❌ | 1s |
| `perfect_1m` | Complete 1m data | ❌ | ✅ | ❌ | 1m |
| `only_1d` | Only daily data | ❌ | ❌ | ✅ | 1d |
| `1s_and_1m` | Both available | ✅ | ✅ | ❌ | 1s (smallest) |
| `all_intervals` | All available | ✅ | ✅ | ✅ | 1s |
| `no_base` | No base intervals | ❌ | ❌ | ❌ | ERROR |
| `1m_with_gaps` | 1m with gaps (99%) | ❌ | ✅ | ❌ | 1m |
| `1s_complete_1m_gaps` | Gap fill scenario | ✅ | ✅ | ❌ | 1s |
| `with_quotes` | Has quotes | ❌ | ✅ | ❌ | 1m |

### Running Stream Determination Tests

```bash
# All stream determination tests
pytest tests/unit/test_stream_determination.py tests/integration/test_stream_determination_with_db.py -v

# Unit tests only (fast)
pytest tests/unit/test_stream_determination.py -v

# Integration tests only
pytest tests/integration/test_stream_determination_with_db.py -v -m integration

# Specific test
pytest tests/unit/test_stream_determination.py::TestStreamDecision::test_stream_smallest_1s_when_available -v
```

### Key Features

**100% Completeness Requirement:**
- Derived bars ONLY generated from 100% complete source data
- Missing even 1 bar = skip generation
- Prevents misleading partial aggregations

**Unified Logic:**
- Same algorithm for backtest and live modes
- Only difference: quote handling
- Consistent behavior across modes

**Intelligent Fallbacks:**
- Sub-minute (5s, 10s): ONLY from 1s
- Minute (5m, 15m): Prefer 1m, fallback 1s
- Day (5d): Prefer 1d → 1m → 1s

**Quote Generation:**
- Live: stream real quotes from API
- Backtest: generate synthetic quotes (bid = ask = close)
- Priority: 1s bar > 1m bar > 1d bar

### Example Test

```python
def test_stream_smallest_1s_when_available():
    """Stream 1s when available (smallest)."""
    availability = AvailabilityInfo(
        symbol="AAPL",
        has_1s=True,
        has_1m=True,
        has_1d=True,
        has_quotes=False
    )
    
    decision = determine_stream_interval(
        symbol="AAPL",
        requested_intervals=["1s", "1m", "5m"],
        availability=availability,
        mode="backtest"
    )
    
    assert decision.stream_interval == "1s"  # Smallest
    assert decision.generate_intervals == ["1m", "5m"]  # All others
    assert decision.error is None
```

---

## Future Enhancements

### Potential Additions
- [ ] More test symbols with edge case scenarios
- [ ] Bar data in Parquet format (directory already exists)
- [ ] Additional session configs (if needed for specific test scenarios)
- [ ] Extended market hours data (more historical dates)
- [ ] E2E tests with full system workflows
- [ ] Performance benchmarks and profiling
- [ ] Load testing utilities
- [ ] Test data visualization tools

---

## Scanner Framework Tests

### Test Coverage

**Unit Tests** (`tests/unit/`)
- `test_scanner_base.py` - BaseScanner, ScanContext, ScanResult
- `test_scanner_manager.py` - ScannerManager, state machine, lifecycle

**Integration Tests** (`tests/integration/`)
- `test_scanner_integration.py` - Scanner with real SessionData

**E2E Tests** (`tests/e2e/`)
- `test_scanner_e2e.py` - Complete scanner workflows

### Running Scanner Tests

```bash
# All scanner tests
pytest tests/ -k scanner -v

# Unit tests only (fast)
pytest tests/unit/test_scanner_*.py -v

# Integration tests
pytest tests/integration/test_scanner_integration.py -v

# E2E tests (slow)
pytest tests/e2e/test_scanner_e2e.py -v -m e2e
```

### Scanner Test Scenarios

**Pre-Session Scanner**
- Setup → Scan → Teardown (immediate)
- Universe loading from file
- Indicator provisioning
- Symbol promotion
- Symbol cleanup

**Regular Session Scanner**
- Setup → Session Start → Scheduled Scans → Teardown
- Schedule parsing (HH:MM format)
- Next scan time calculation
- Multiple scan executions
- End-of-session teardown

**Error Handling**
- Import failures
- Setup failures
- Scan exceptions
- Missing universe files

---

## References

- **Architecture:** `backend/docs/SESSION_ARCHITECTURE.md`
- **Time Manager:** `backend/docs/TIME_MANAGER.md`
- **Quality Audit:** `backend/docs/QUALITY_CALCULATION_AUDIT.md`
- **Scanner Framework:** `backend/SCANNER_FRAMEWORK_COMPLETE.md`
- **Pytest Docs:** https://docs.pytest.org/

---

**Last Updated:** December 8, 2025  
**Test Count:** 160+ tests (95+ unit + 60+ integration + 5+ e2e)  
**Coverage:** ~97% for quality modules, ~95% for scanner framework  
**Execution Time:** ~2.5s (all tests, excluding e2e)
