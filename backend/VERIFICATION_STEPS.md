# Phase 1 Verification Steps

## Prerequisites

Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

---

## Step 1: Run Unit Tests

```bash
cd /home/yohannes/mismartera/backend

# Run session_data tests
python3 -m pytest app/managers/data_manager/tests/test_session_data.py -v

# Expected output: 12 tests passing
```

Expected results:
```
test_register_symbol PASSED
test_add_bar PASSED
test_add_bars_batch PASSED
test_get_latest_bar PASSED
test_get_last_n_bars PASSED
test_get_bars_since PASSED
test_get_bar_count PASSED
test_get_latest_bars_multi PASSED
test_session_lifecycle PASSED
test_get_bars_with_filters PASSED
test_thread_safety PASSED
```

---

## Step 2: Verify Module Imports

```bash
python3 -c "
from app.managers.data_manager.session_data import get_session_data, SessionData
from app.managers.system_manager import get_system_manager
from app.managers.data_manager.api import DataManager

print('✅ All modules import successfully')
"
```

---

## Step 3: Quick Integration Test

Create a test file `test_integration.py`:

```python
import asyncio
from datetime import datetime
from app.managers.system_manager import get_system_manager
from app.managers.data_manager.session_data import get_session_data
from app.models.trading import BarData

async def test_integration():
    print("Testing Phase 1 Integration...")
    
    # 1. Access via SystemManager
    system_mgr = get_system_manager()
    session_data = system_mgr.session_data
    print("✅ SystemManager.session_data accessible")
    
    # 2. Add test bar
    bar = BarData(
        symbol="AAPL",
        timestamp=datetime(2025, 1, 1, 9, 30),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000
    )
    await session_data.add_bar("AAPL", bar)
    print("✅ Bar added successfully")
    
    # 3. Test O(1) latest bar access
    latest = await session_data.get_latest_bar("AAPL")
    assert latest.close == 150.5
    print(f"✅ Latest bar retrieved: ${latest.close}")
    
    # 4. Add more bars
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30 + i),
            open=150.0 + i,
            high=151.0 + i,
            low=149.0 + i,
            close=150.5 + i,
            volume=1000
        )
        for i in range(1, 21)  # 20 more bars
    ]
    await session_data.add_bars_batch("AAPL", bars)
    print(f"✅ Batch added 20 bars")
    
    # 5. Test last-N bars
    last_10 = await session_data.get_last_n_bars("AAPL", 10)
    assert len(last_10) == 10
    print(f"✅ Last 10 bars retrieved: {len(last_10)} bars")
    
    # 6. Test bar count
    count = await session_data.get_bar_count("AAPL")
    assert count == 21  # 1 initial + 20 batch
    print(f"✅ Bar count: {count}")
    
    # 7. Test metrics
    metrics = await session_data.get_session_metrics("AAPL")
    print(f"✅ Session metrics: volume={metrics['session_volume']}, "
          f"high={metrics['session_high']}, low={metrics['session_low']}")
    
    # 8. Test multi-symbol
    await session_data.add_bar("GOOGL", bars[0])
    await session_data.add_bar("MSFT", bars[1])
    
    latest_multi = await session_data.get_latest_bars_multi(["AAPL", "GOOGL", "MSFT"])
    assert len(latest_multi) == 3
    print(f"✅ Multi-symbol latest bars: {list(latest_multi.keys())}")
    
    print("\n🎉 All integration tests passed!")
    print(f"   Active symbols: {session_data.get_active_symbols()}")

if __name__ == "__main__":
    asyncio.run(test_integration())
```

Run:
```bash
python3 test_integration.py
```

---

## Step 4: Verify Deprecation Warning

```python
# This should show deprecation warning
python3 -c "
import warnings
warnings.simplefilter('always', DeprecationWarning)

from app.managers.data_manager.session_tracker import get_session_tracker
print('✅ SessionTracker still works (with deprecation warning)')
"
```

Expected: See deprecation warning but code still works.

---

## Step 5: Test BacktestStreamCoordinator Integration

Create `test_coordinator_integration.py`:

```python
import asyncio
from datetime import datetime
from app.managers.system_manager import get_system_manager
from app.managers.data_manager.backtest_stream_coordinator import (
    get_coordinator, 
    StreamType
)
from app.managers.data_manager.session_data import get_session_data
from app.models.trading import BarData

async def test_coordinator():
    print("Testing BacktestStreamCoordinator integration...")
    
    # Get coordinator and session_data
    system_mgr = get_system_manager()
    coordinator = get_coordinator(system_mgr)
    session_data = get_session_data()
    
    # Register a stream
    success, queue = coordinator.register_stream("TSLA", StreamType.BAR)
    assert success
    print("✅ Stream registered")
    
    # Note: Full coordinator test requires running worker thread
    # For now, verify that coordinator has session_data reference
    assert coordinator._session_data is not None
    print("✅ Coordinator has session_data reference")
    
    # Verify session_data is accessible
    assert session_data is system_mgr.session_data
    print("✅ session_data accessible via SystemManager")
    
    print("\n🎉 Coordinator integration verified!")

if __name__ == "__main__":
    asyncio.run(test_coordinator())
```

Run:
```bash
python3 test_coordinator_integration.py
```

---

## Step 6: Performance Benchmark (Optional)

Create `benchmark_session_data.py`:

```python
import asyncio
import time
from datetime import datetime
from app.managers.data_manager.session_data import get_session_data, reset_session_data
from app.models.trading import BarData

async def benchmark():
    print("Benchmarking session_data performance...\n")
    
    reset_session_data()
    session_data = get_session_data()
    
    # Prepare test data
    bars = [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 1, 9, 30, i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000
        )
        for i in range(1000)
    ]
    
    await session_data.add_bars_batch("AAPL", bars)
    print(f"✅ Added {len(bars)} bars")
    
    # Benchmark get_latest_bar
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        await session_data.get_latest_bar("AAPL")
    elapsed = time.perf_counter() - start
    
    per_call_us = (elapsed / iterations) * 1_000_000
    print(f"\n📊 get_latest_bar:")
    print(f"   {iterations} calls: {elapsed:.4f}s")
    print(f"   Per call: {per_call_us:.2f}µs")
    print(f"   Throughput: {iterations/elapsed:,.0f} ops/sec")
    
    # Benchmark get_last_n_bars
    start = time.perf_counter()
    for _ in range(iterations):
        await session_data.get_last_n_bars("AAPL", 20)
    elapsed = time.perf_counter() - start
    
    per_call_us = (elapsed / iterations) * 1_000_000
    print(f"\n📊 get_last_n_bars(20):")
    print(f"   {iterations} calls: {elapsed:.4f}s")
    print(f"   Per call: {per_call_us:.2f}µs")
    print(f"   Throughput: {iterations/elapsed:,.0f} ops/sec")
    
    # Benchmark get_bar_count
    start = time.perf_counter()
    for _ in range(iterations):
        await session_data.get_bar_count("AAPL")
    elapsed = time.perf_counter() - start
    
    per_call_us = (elapsed / iterations) * 1_000_000
    print(f"\n📊 get_bar_count:")
    print(f"   {iterations} calls: {elapsed:.4f}s")
    print(f"   Per call: {per_call_us:.2f}µs")
    print(f"   Throughput: {iterations/elapsed:,.0f} ops/sec")
    
    print("\n✅ Benchmark complete!")

if __name__ == "__main__":
    asyncio.run(benchmark())
```

Run:
```bash
python3 benchmark_session_data.py
```

Expected performance:
- `get_latest_bar`: < 1µs per call
- `get_last_n_bars(20)`: < 5µs per call
- `get_bar_count`: < 0.1µs per call

---

## Success Criteria Checklist

- [ ] All unit tests pass (12 tests)
- [ ] Modules import without errors
- [ ] Integration test passes
- [ ] SessionTracker shows deprecation warning
- [ ] Coordinator has session_data reference
- [ ] Performance benchmarks meet targets
- [ ] SystemManager.session_data accessible
- [ ] DataManager.session_data accessible

---

## Troubleshooting

### Import Errors
```bash
# Install dependencies
pip install -r requirements.txt

# Or install individually
pip install loguru sqlalchemy asyncpg
```

### Test Failures
Check:
1. Python version (3.11+ recommended)
2. All files created in correct locations
3. No syntax errors in modified files

### Performance Issues
If performance is significantly slower:
1. Check Python version (3.11+ has better async performance)
2. Verify deque is being used (not list)
3. Check lock contention (should be minimal)

---

## Next Steps After Verification

Once all checks pass:

1. **Commit changes**:
```bash
git add app/managers/data_manager/session_data.py
git add app/managers/data_manager/tests/test_session_data.py
git add app/managers/system_manager.py
git add app/managers/data_manager/api.py
git add app/managers/data_manager/backtest_stream_coordinator.py
git add app/managers/data_manager/session_tracker.py
git commit -m "feat: Implement session_data singleton for Phase 1"
```

2. **Review documentation**:
   - `PHASE1_COMPLETE.md`
   - `SESSION_DATA_PERFORMANCE.md`
   - `ARCHITECTURE_COMPARISON.md`

3. **Plan Phase 2**:
   - Review `STREAM_COORDINATOR_ANALYSIS.md`
   - Phase 2: Data-Upkeep Thread (3 weeks)

---

## Quick Verification (No Tests)

If you just want to verify the code compiles:

```bash
python3 -m py_compile app/managers/data_manager/session_data.py
python3 -m py_compile app/managers/data_manager/tests/test_session_data.py

echo "✅ Python syntax check passed"
```

---

**Status**: Ready for verification  
**Estimated time**: 10-15 minutes  
**Dependencies**: Python 3.11+, requirements.txt packages
