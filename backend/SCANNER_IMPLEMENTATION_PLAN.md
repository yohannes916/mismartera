# Scanner Framework - Implementation Plan

## Overview

High-level plan for implementing the dynamic symbol scanner framework across 3 phases.

---

## Prerequisites (Already Complete ✅)

Before implementing scanners, these must exist:

- ✅ **session_data.add_indicator()** - Adhoc indicator addition
- ✅ **SessionCoordinator.add_symbol_mid_session()** - Dynamic symbol registration
- ✅ **requirement_analyzer** - Determines bar requirements
- ✅ **IndicatorManager** - Per-symbol indicator management
- ✅ **Lag detection/catchup** - Pause/resume streaming

**Status**: All prerequisites exist! Ready to implement scanners.

---

## Phase 1: Core Scanner Infrastructure

**Goal**: Basic scanner framework with manual testing

### Components to Build

#### 1. Base Scanner Class (`scanners/base.py`)
```python
- BaseScanner (ABC)
  ├─ __init__(config)
  ├─ setup(context) → bool
  ├─ scan(context) → ScanResult [abstract]
  └─ teardown(context)

- ScanContext (dataclass)
  ├─ session_data
  ├─ time_manager
  ├─ mode
  ├─ current_time
  └─ config

- ScanResult (dataclass)
  ├─ symbols: List[str]
  ├─ metadata: Dict
  ├─ execution_time_ms: float
  ├─ skipped: bool
  └─ error: Optional[str]
```

**Files**:
- `scanners/__init__.py`
- `scanners/base.py`

**Estimated**: 2-3 hours

---

#### 2. Scanner Manager (`app/threads/scanner_manager.py`)
```python
class ScannerManager:
    - load_scanners()           # Import from config
    - setup_all()               # Call setup() on each
    - execute_pre_session_scans()  # Run pre_session=true scanners
    - execute_scheduled_scans()    # Run on schedule
    - should_run_scan(name)        # Check schedule
    - _execute_scan(name, scanner) # Blocking execution
    - _process_scan_result(result) # Add symbols
```

**Files**:
- `app/threads/scanner_manager.py`

**Estimated**: 4-5 hours

---

#### 3. Configuration Schema (`app/models/session_config.py`)
```python
@dataclass
class ScannerSchedule:
    interval: str                    # "5m", "15m"
    start_time: Optional[str]        # "09:35"
    end_time: Optional[str]          # "15:55"
    days_of_week: List[str]          # ["Mon", "Tue", ...]

@dataclass
class ScannerConfig:
    name: str
    module: str
    enabled: bool
    pre_session: bool
    schedule: ScannerSchedule
    config: Dict[str, Any]
    symbol_requirements: Dict[str, Any]
    timeout_seconds: int

@dataclass
class SessionDataConfig:
    symbols: List[str]
    streams: List[str]
    scanners: List[ScannerConfig]  # NEW
```

**Files**:
- `app/models/session_config.py` (modifications)

**Estimated**: 2-3 hours

---

#### 4. SessionCoordinator Integration
```python
# In SessionCoordinator.__init__()
self.scanner_manager = ScannerManager(...)

# In _coordinator_loop(), before session activation
self.scanner_manager.load_scanners()
self.scanner_manager.setup_all()
self.scanner_manager.execute_pre_session_scans()

# In streaming loop
if self._should_run_scanners():
    self.scanner_manager.execute_scheduled_scans()
```

**Files**:
- `app/threads/session_coordinator.py` (modifications)

**Estimated**: 2-3 hours

---

### Phase 1 Testing

**Manual Tests**:
1. Create simple test scanner (`scanners/test_scanner.py`)
2. Add scanner to session_config
3. Run backtest and verify:
   - Scanner loads
   - setup() called
   - Pre-session scan executes
   - Symbols added
   - Logs show scanner activity

**Test Scanner**:
```python
class Scanner(BaseScanner):
    def setup(self, context):
        # Register SMA for SPY
        context.session_data.add_indicator(
            "SPY",
            IndicatorConfig(name="sma", period=20, interval="1d")
        )
        return True
    
    def scan(self, context):
        # Always return SPY
        return ScanResult(symbols=["SPY"])
```

**Expected Output**:
```
[SCANNER] Loaded: test_scanner
[SCANNER] Setting up: test_scanner
[SCANNER] Setup complete: test_scanner
[SCANNER] Pre-session scan: test_scanner
[SCANNER] test_scanner: Found 1 symbols (50ms)
[SCANNER] test_scanner: Adding symbol SPY
[SESSION] SPY registered mid-session
```

**Phase 1 Complete**: Basic framework working, can load/execute scanners

---

## Phase 2: Production Features

**Goal**: Make scanners production-ready

### Components to Add

#### 1. Async Execution (Live Mode)
```python
async def _execute_scan_async(self, name, scanner):
    """Non-blocking scan execution."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, self._execute_scan, name, scanner)
    self._process_scan_result(name, result)
    return result

# Check if previous scan running
if mode == "live" and name in self.running_scans:
    if not self.running_scans[name].done():
        logger.warning(f"Skipping {name} - previous scan running")
        return
```

**Estimated**: 3-4 hours

---

#### 2. Timeout Handling
```python
def _execute_scan_with_timeout(self, name, scanner):
    """Execute scan with timeout."""
    timeout = self.scanner_configs[name].get("timeout_seconds", 30)
    
    try:
        result = func_timeout(timeout, scanner.scan, args=[context])
    except FunctionTimedOut:
        logger.error(f"Scanner {name} timed out after {timeout}s")
        return ScanResult(symbols=[], error="Timeout")
```

**Estimated**: 1-2 hours

---

#### 3. Schedule Parsing
```python
def _parse_schedule(self, schedule_config):
    """Parse schedule config into cron-like rules."""
    # Support:
    # - interval: "5m", "15m", "1h"
    # - start_time/end_time: "09:35"
    # - days_of_week: ["Mon", "Tue", ...]
    
def should_run_scan(self, name):
    """Check if scan should run at current time."""
    # Implement proper schedule checking
```

**Estimated**: 2-3 hours

---

#### 4. Performance Tracking
```python
# Track scan history
self.scan_history.append({
    "scanner": name,
    "timestamp": current_time,
    "symbols_found": len(result.symbols),
    "execution_time_ms": result.execution_time_ms,
    "error": result.error
})

# Export in system status
def get_scanner_stats(self):
    """Return scanner performance stats."""
    return {
        "total_scans": len(self.scan_history),
        "avg_execution_time": ...,
        "total_symbols_added": ...,
        "by_scanner": {...}
    }
```

**Estimated**: 2-3 hours

---

#### 5. Error Recovery
```python
# Retry logic
if result.error and self._should_retry(name):
    logger.info(f"Retrying {name} (attempt {attempt}/3)")
    result = self._execute_scan(name, scanner)

# Disable on repeated failures
if self._consecutive_failures[name] >= 3:
    logger.error(f"Disabling {name} after 3 failures")
    self.scanners.pop(name)
```

**Estimated**: 2-3 hours

---

### Phase 2 Testing

**Integration Tests**:
1. Test async execution (live mode simulation)
2. Test timeout handling (slow scanner)
3. Test schedule parsing (various intervals)
4. Test error handling (exception in scan)
5. Test skip logic (previous scan running)

**Phase 2 Complete**: Production-ready scanner framework

---

## Phase 3: Example Scanners & Documentation

**Goal**: Provide useful scanners and documentation

### Example Scanners to Build

#### 1. Gap Scanner (`scanners/gap_scanner.py`)
```python
# Finds stocks with pre-market gaps
Criteria:
- Gap >= 2% from previous close
- Volume >= 1M shares
- Price <= $500
```
**Estimated**: 2-3 hours

---

#### 2. Momentum Scanner (`scanners/momentum_scanner.py`)
```python
# Finds stocks with intraday momentum
Criteria:
- RSI >= 70 (overbought)
- Volume ratio >= 2.0 (unusual volume)
- Price above 20-day SMA
```
**Estimated**: 2-3 hours

---

#### 3. Volume Scanner (`scanners/volume_scanner.py`)
```python
# Finds stocks with unusual volume
Criteria:
- Current volume >= 3x average
- Price change >= 1%
- Not in watchlist already
```
**Estimated**: 2-3 hours

---

#### 4. Breakout Scanner (`scanners/breakout_scanner.py`)
```python
# Finds stocks breaking resistance
Criteria:
- Price > 20-day high
- Volume > average
- Bullish candle pattern
```
**Estimated**: 3-4 hours

---

### Documentation

#### 1. Scanner Development Guide
- How to create custom scanner
- BaseScanner API reference
- ScanContext methods
- Best practices
- Example code

**Estimated**: 3-4 hours

---

#### 2. Configuration Guide
- Scanner config schema
- Schedule options
- Symbol requirements
- Timeout settings

**Estimated**: 2-3 hours

---

#### 3. Deployment Guide
- Where to place scanner files
- How to test scanners
- Debugging tips
- Performance tuning

**Estimated**: 2-3 hours

---

### Phase 3 Testing

**End-to-End Tests**:
1. Run all example scanners in backtest
2. Verify symbols added correctly
3. Check performance metrics
4. Validate documentation accuracy

**Phase 3 Complete**: Production-ready with examples

---

## Time Estimates

| Phase | Components | Hours | Notes |
|-------|-----------|-------|-------|
| **Phase 1** | Core Infrastructure | 10-14 | Base classes, manager, integration |
| **Phase 2** | Production Features | 12-17 | Async, timeouts, error handling |
| **Phase 3** | Examples & Docs | 12-17 | 4 scanners + documentation |
| **Total** | | **34-48** | ~1-2 weeks full-time |

---

## Dependencies Between Phases

```
Phase 1 (Core)
    │
    ├─ Must complete before Phase 2
    │  (Need basic framework to add features)
    │
    └─ Can start Phase 3 docs in parallel
       (Document API as you build)

Phase 2 (Production)
    │
    └─ Must complete before Phase 3 scanners
       (Example scanners need async/timeout)

Phase 3 (Examples)
    │
    └─ Independent work
       (Each scanner separate)
```

---

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_scanner_base.py
- Test ScanContext creation
- Test ScanResult validation
- Test BaseScanner methods

# tests/unit/test_scanner_manager.py
- Test scanner loading
- Test schedule parsing
- Test result processing
```

### Integration Tests
```python
# tests/integration/test_scanner_lifecycle.py
- Test full lifecycle (load → setup → scan → add symbols)
- Test pre-session vs mid-session
- Test backtest vs live mode

# tests/integration/test_scanner_examples.py
- Test each example scanner
- Verify criteria logic
- Check symbol selection
```

### Manual Tests
```
# Run with test session config
./start_cli.sh
system start session_configs/test_scanner_session.json

# Check logs for scanner activity
# Verify symbols added to session
# Export status and check scanner stats
```

---

## Success Criteria

### Phase 1
- [ ] Can load scanner from config
- [ ] setup() called before session
- [ ] scan() executed on schedule
- [ ] Symbols added to session_data
- [ ] Logs show scanner activity

### Phase 2
- [ ] Async execution in live mode
- [ ] Timeout protection works
- [ ] Error recovery handles exceptions
- [ ] Schedule parsing accurate
- [ ] Performance stats exported

### Phase 3
- [ ] 4 example scanners working
- [ ] Documentation complete
- [ ] Can create custom scanner in <30 min
- [ ] Performance acceptable (<500ms per scan)

---

## Risk Mitigation

### Potential Issues

1. **Scanner takes too long**
   - Solution: Timeout enforcement
   - Fallback: Skip and retry next interval

2. **Scanner adds too many symbols**
   - Solution: Symbol limit in config
   - Fallback: Log warning, take top N

3. **Historical data not loaded**
   - Solution: Check indicator.valid before scan
   - Fallback: Skip symbol in results

4. **Scanner crashes repeatedly**
   - Solution: Disable after N failures
   - Fallback: Continue with other scanners

5. **Memory usage from universe**
   - Solution: Lazy loading of indicators
   - Fallback: Limit universe size

---

## Post-Implementation

### Future Enhancements (Not in MVP)

1. **Scanner Composition**
   ```python
   # Combine multiple scanners
   combined = GapScanner() & MomentumScanner()
   ```

2. **Scanner Backtesting**
   ```python
   # Test scanner logic separately
   backtest_scanner(gap_scanner, date_range="2024-01-01:2024-12-31")
   ```

3. **Dynamic Universe**
   ```python
   # Update universe based on market cap, sector, etc.
   universe = DynamicUniverse(
       min_market_cap=1e9,
       sectors=["Technology", "Healthcare"]
   )
   ```

4. **Scanner Analytics Dashboard**
   - Web UI showing scanner performance
   - Historical scan results
   - Symbol attribution (which scanner found it)

5. **Scanner Alerts**
   - Send notification when scan finds symbols
   - Email/Slack/Discord integration

---

## Architecture Principles Maintained

✅ **session_data as ultimate source**
- Scanners query session_data only
- Scanners add symbols via session_data
- No direct database access

✅ **Separation of concerns**
- Scanners: Symbol discovery logic
- ScannerManager: Lifecycle & scheduling
- SessionCoordinator: Integration
- session_data: State storage

✅ **Composability**
- Multiple scanners run independently
- Results don't affect each other
- Easy to add/remove scanners

✅ **Testability**
- BaseScanner is mockable
- ScanContext is injectable
- Clear input/output contracts

✅ **Performance**
- Async in live mode
- Timeouts prevent blocking
- Minimal overhead when disabled

---

## Summary

### What We're Building

A **dynamic symbol discovery system** that:
- Loads custom Python scanners from config
- Runs setup phase (register indicators)
- Executes scans on schedule (find symbols)
- Adds qualifying symbols mid-session
- Handles errors gracefully
- Works in backtest and live mode

### Key Benefits

1. **Flexible**: Easy to add custom logic
2. **Integrated**: Uses existing infrastructure
3. **Performant**: Async, timeouts, lazy loading
4. **Reliable**: Error handling, retry logic
5. **Observable**: Logs, metrics, history

### Next Steps

1. ✅ Review design documents
2. → Start Phase 1 implementation
3. → Test with simple scanner
4. → Add Phase 2 features
5. → Build example scanners
6. → Write documentation

**Ready to start Phase 1!** 🚀
