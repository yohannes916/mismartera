# Strategy Framework Tests

## Overview

Comprehensive test suite for the strategy framework with **145+ tests** across unit, integration, E2E, and performance categories.

## Quick Start

### Run All Strategy Tests
```bash
# From backend directory
pytest tests/unit/strategies/ tests/integration/strategies/ tests/e2e/strategies/ -v
```

### Run By Category
```bash
# Unit tests only (fastest)
pytest tests/unit/strategies/ -v

# Integration tests
pytest tests/integration/strategies/ -v

# E2E tests
pytest tests/e2e/strategies/ -v

# Performance tests (with output)
pytest tests/performance/test_strategy_performance.py -v -s
```

### Run Specific Test File
```bash
pytest tests/unit/strategies/test_base_strategy.py -v
pytest tests/unit/strategies/test_strategy_thread.py -v
pytest tests/unit/strategies/test_strategy_manager.py -v
```

## Test Coverage

### Unit Tests (5 files, ~80 tests)
- **test_base_strategy.py** (41 tests) - BaseStrategy, Signal, StrategyContext
- **test_strategy_thread.py** (38 tests) - Threading, queue, metrics
- **test_strategy_manager.py** (42 tests) - Manager, loading, routing
- **test_strategy_config.py** (21 tests) - Configuration validation
- **test_simple_ma_cross.py** (29 tests) - Example strategy

### Integration Tests (2 files, ~35 tests)
- **test_strategy_lifecycle.py** (18 tests) - Full lifecycle testing
- **test_strategy_subscriptions.py** (17 tests) - Subscription routing

### E2E Tests (1 file, ~15 tests)
- **test_strategy_e2e.py** (15 tests) - Complete system integration

### Performance Tests (1 file, ~15 tests)
- **test_strategy_performance.py** (15 tests) - Throughput, latency, memory

## Coverage Report

```bash
# Generate HTML coverage report
pytest tests/unit/strategies/ --cov=app.strategies --cov-report=html

# Open in browser
open htmlcov/index.html
```

## Test Requirements

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-benchmark psutil
```

## Test Patterns

### Unit Test Example
```python
def test_base_strategy_setup(strategy_context):
    """Test BaseStrategy.setup() lifecycle."""
    strategy = ConcreteStrategy(name="test", config={})
    result = strategy.setup(strategy_context)
    assert result is True
    assert strategy.context is strategy_context
```

### Integration Test Example
```python
def test_strategy_full_lifecycle(mock_system_manager):
    """Test complete lifecycle: load → setup → run → teardown."""
    manager = StrategyManager(mock_system_manager)
    manager.initialize()
    manager.start_strategies()
    # ... test ...
    manager.stop_strategies()
```

### Performance Test Example
```python
def test_throughput_single_strategy(mock_system_manager, benchmark):
    """Benchmark throughput with single strategy."""
    def send_notifications():
        for i in range(1000):
            manager.notify_strategies("AAPL", "5m", "bars")
    result = benchmark(send_notifications)
```

## Expected Results

All tests should pass:
```
===== 145 passed in 2.5s =====
```

## Troubleshooting

### Tests Fail to Import
```bash
# Ensure you're in backend directory
cd /home/yohannes/mismartera/backend

# Add to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

### Slow Tests
```bash
# Run only fast tests
pytest tests/unit/strategies/ -v

# Skip performance tests
pytest tests/unit/strategies/ tests/integration/strategies/ -v
```

## Documentation

See comprehensive documentation:
- **STRATEGY_FRAMEWORK_COMPLETE_DEC_9_2025.md** - Full completion summary
- **STRATEGY_FRAMEWORK_PROGRESS_DEC_9_2025.md** - Progress tracking
- **STRATEGY_FRAMEWORK_IMPLEMENTATION_DEC_9_2025.md** - Implementation details
