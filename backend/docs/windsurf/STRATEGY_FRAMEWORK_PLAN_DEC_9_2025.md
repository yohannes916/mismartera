# Strategy Framework Plan - December 9, 2025

## Executive Summary

Plan to refactor the current AnalysisEngine into a robust, scanner-like strategy framework that supports multiple concurrent strategies with clean lifecycle management, selective data subscriptions, and performance monitoring.

---

## Current State Analysis

### What Exists: AnalysisEngine (Thread-Based)

**Location**: `app/threads/analysis_engine.py`

**Architecture**:
- Single thread that processes ALL data notifications
- Runs in event-driven loop waiting on notification queue
- Executes strategies sequentially on each notification
- Uses StreamSubscription for sync with DataProcessor
- Zero-copy access to SessionData

**Lifecycle**:
```python
start() → run() → _processing_loop() → stop() → join()
```

**Current Limitations**:
1. **No selective subscriptions** - Processes ALL symbols/intervals
2. **Sequential execution** - All strategies process every notification
3. **No per-strategy threads** - Single thread for all strategies
4. **Manual strategy registration** - Strategies not loaded from config
5. **No module-based loading** - Strategies not Python modules
6. **No teardown hooks** - Strategies can't cleanup

---

## Scanner Framework Study

### What Works Well

**Location**: `app/threads/scanner_manager.py`

**Key Features**:
1. ✅ **Module-based loading** - Scanners live in `scanners/` folder
2. ✅ **Organized by folders** - Can have `scanners/examples/`, `scanners/production/`
3. ✅ **Unique names** - File name = class name requirement
4. ✅ **Config-driven** - Session config specifies which scanners to run
5. ✅ **Clear lifecycle** - setup() → scan() → teardown()
6. ✅ **State machine** - Tracks scanner state (INITIALIZED, SCANNING, etc.)
7. ✅ **Manager pattern** - ScannerManager orchestrates all scanners
8. ✅ **Context pattern** - ScanContext provides access to data/services
9. ✅ **Performance timing** - Tracks execution time per operation

**Module Loading**:
```python
# scanners/examples/momentum_scanner.py
class MomentumScanner(BaseScanner):
    def setup(self, context: ScanContext) -> bool:
        # Load universe, configure
        pass
    
    def scan(self, context: ScanContext) -> ScanResult:
        # Execute scan logic
        pass
    
    def teardown(self, context: ScanContext):
        # Cleanup
        pass
```

**Config**:
```json
{
  "scanners": [
    {
      "module": "scanners.examples.momentum_scanner",
      "enabled": true,
      "config": {"universe": "sp500.txt"}
    }
  ]
}
```

---

## Proposed Strategy Framework

### Design Principles

1. **Simple** - A strategy is just a Python module with a strategy class
2. **Organized** - All strategies live in `strategies/` folder, can organize in subfolders
3. **Unique names** - File name must match class name (convention)
4. **Config-driven** - Session config specifies which strategies to run
5. **Concurrent** - Each strategy runs in its own thread
6. **Selective** - Strategies subscribe only to symbols/intervals they need
7. **Synchronized** - Use StreamSubscription for coordination with DataProcessor
8. **Fast access** - Zero-copy access to SessionData
9. **Monitored** - Performance counters, backpressure detection

### Directory Structure

```
strategies/
├── __init__.py
├── base.py                    # BaseStrategy abstract class
├── examples/
│   ├── simple_ma_cross.py     # SimpleMA CrossStrategy class
│   ├── rsi_strategy.py        # RsiStrategy class
│   └── vwap_strategy.py       # VwapStrategy class
└── production/
    ├── my_strategy.py         # MyStrategy class
    └── advanced_strategy.py   # AdvancedStrategy class
```

### Naming Convention

**REQUIRED**:
- File: `simple_ma_cross.py`
- Class: `SimpleMaCrossStrategy` (PascalCase, must end with "Strategy")
- Unique across all folders

---

## Architecture

### Component Overview

```
SystemManager
    ↓
StrategyManager (NEW - like ScannerManager)
    ↓
Strategy Threads (NEW - one per strategy)
    ↓
DataProcessor → notifies → Strategy Threads (via queues)
    ↓
SessionData (zero-copy access)
```

### Key Components

#### 1. StrategyManager

**Responsibilities**:
- Load strategies from session config
- Create strategy threads
- Wire subscriptions and queues
- Manage lifecycle (start, pause, stop)
- Collect statistics from all strategies
- Handle graceful shutdown

**API**:
```python
class StrategyManager:
    def __init__(self, system_manager)
    def initialize() -> bool
    def start_strategies() -> bool
    def pause_strategies() -> None
    def resume_strategies() -> None
    def stop_strategies() -> None
    def shutdown() -> None
    def get_statistics() -> Dict[str, Any]
```

#### 2. BaseStrategy (Abstract Base Class)

**Responsibilities**:
- Define strategy API contract
- Provide access to SessionData
- Define lifecycle hooks
- Define subscription interface

**API**:
```python
class BaseStrategy(ABC):
    def __init__(self, name: str, config: Dict[str, Any])
    
    # Lifecycle hooks
    @abstractmethod
    def setup(self, context: StrategyContext) -> bool
    
    @abstractmethod
    def on_bars(self, symbol: str, interval: str) -> List[Signal]
    
    def on_quality_update(self, symbol: str, interval: str, quality: float)
    def teardown(self, context: StrategyContext)
    
    # Subscription interface
    @abstractmethod
    def get_subscriptions(self) -> List[Tuple[str, str]]
        # Returns [(symbol, interval), ...]
```

#### 3. StrategyThread (NEW)

**Responsibilities**:
- Run strategy in own thread
- Wait on strategy-specific notification queue
- Synchronize with DataProcessor via StreamSubscription
- Call strategy hooks (on_bars, on_quality_update)
- Track performance metrics
- Handle errors gracefully

**Lifecycle**:
```python
class StrategyThread(threading.Thread):
    def __init__(self, strategy: BaseStrategy, ...)
    def run()                      # Main event loop
    def pause()                    # Pause processing
    def resume()                   # Resume processing
    def stop()                     # Graceful stop
    def signal_ready()             # To DataProcessor
    def get_statistics() -> Dict
```

#### 4. StrategyContext

**Responsibilities**:
- Provide access to system services
- Zero-copy access to SessionData
- Access to TimeManager, DataManager
- Strategy configuration

**API**:
```python
@dataclass
class StrategyContext:
    session_data: SessionData    # Zero-copy access
    time_manager: TimeManager
    data_manager: DataManager
    mode: str                    # "backtest" or "live"
    config: Dict[str, Any]       # Strategy config
    current_time: datetime
```

---

## Data Flow

### Selective Subscription Model

```
1. Strategy defines subscriptions:
   get_subscriptions() → [("AAPL", "5m"), ("GOOGL", "5m")]

2. StrategyManager creates queue for each strategy

3. DataProcessor notifies only subscribed strategies:
   for each (symbol, interval) update:
       for strategy in strategies_subscribed_to(symbol, interval):
           strategy.queue.put((symbol, interval, "bars"))

4. StrategyThread waits on its own queue:
   notification = self.queue.get(timeout=1.0)
   if notification:
       symbol, interval, data_type = notification
       bars = session_data.get_bars_ref(symbol, interval)  # Zero-copy
       signals = strategy.on_bars(symbol, interval)
```

### Synchronization Flow

```
DataProcessor:
    1. Process bars/indicators
    2. Notify subscribed strategies (put to queues)
    3. Wait for ALL strategies to signal ready
    4. Continue to next data

StrategyThread:
    1. Wait on notification queue
    2. Process data (call on_bars)
    3. Signal ready to DataProcessor
    4. Loop
```

---

## Session Config Format

```json
{
  "session_data_config": {
    "symbols": ["AAPL", "GOOGL"],
    "streams": ["1m", "5m"],
    "strategies": [
      {
        "module": "strategies.examples.simple_ma_cross",
        "enabled": true,
        "config": {
          "symbols": ["AAPL"],
          "interval": "5m",
          "fast_period": 10,
          "slow_period": 20
        }
      },
      {
        "module": "strategies.production.my_strategy",
        "enabled": true,
        "config": {
          "symbols": ["AAPL", "GOOGL"],
          "interval": "5m",
          "min_quality": 95.0
        }
      }
    ]
  }
}
```

---

## Lifecycle Management

### Startup Sequence

```
1. SystemManager.start_session()
2. StrategyManager.initialize()
   - Load strategy modules from config
   - Instantiate strategy classes
   - Create StrategyThread for each
   - Create notification queues
   - Wire StreamSubscriptions
3. StrategyManager.start_strategies()
   - Call strategy.setup(context)
   - Start strategy threads
   - Threads enter event loop
```

### Runtime Flow

```
1. DataProcessor processes new bars
2. Notifies subscribed strategies (queue.put)
3. StrategyThread wakes up
4. Calls strategy.on_bars(symbol, interval)
5. Strategy generates signals
6. StrategyThread signals ready to DataProcessor
7. DataProcessor waits for all strategies
8. Cycle repeats
```

### Shutdown Sequence

```
1. SystemManager.shutdown()
2. StrategyManager.stop_strategies()
   - Set stop event for each thread
   - Put None sentinel to queues
3. Wait for threads to finish
4. StrategyManager.shutdown()
   - Call strategy.teardown(context)
   - Clear resources
```

### Pause/Resume (Uses Existing Infrastructure)

**Existing Implementation**: `session_coordinator.py` lines 638-680

```python
# Already exists!
session_coordinator.pause_backtest()   # Pause clock
session_coordinator.resume_backtest()  # Resume clock
session_coordinator.is_paused()        # Check status
```

**When Used** (Clock-Driven Backtesting):
- Scanner execution (pause clock while scanner runs)
- Mid-session symbol insertion (pause clock during registration)

**Behavior**:
- Clock frozen at current time
- No new bars arrive
- Strategies idle (waiting on empty queues)
- Safe to modify SessionData
- Resume continues from same timestamp

---

## Performance Monitoring

### Per-Strategy Metrics

```python
{
    "strategy_name": "SimpleMaCrossStrategy",
    "running": true,
    "paused": false,
    "subscriptions": [("AAPL", "5m"), ("GOOGL", "5m")],
    "notifications_processed": 1234,
    "signals_generated": 45,
    "avg_processing_time_ms": 2.3,
    "max_processing_time_ms": 15.2,
    "queue_size": 0,
    "overruns": 0,
    "errors": 0
}
```

### System-Wide Metrics

```python
{
    "total_strategies": 3,
    "active_strategies": 3,
    "paused_strategies": 0,
    "total_signals": 150,
    "avg_strategy_lag_ms": 1.5,
    "max_strategy_lag_ms": 5.2,
    "backpressure_events": 0
}
```

### Backpressure Detection

**Indicators**:
1. Queue size > threshold (e.g., > 10)
2. Processing time > interval duration
3. Overrun count increasing
4. StreamSubscription timeout

**Action**:
- Log warning with strategy name
- Track in metrics
- Optional: Pause strategy if too slow

---

## Synchronization Details

### StreamSubscription Usage

**For Each Strategy**:
```python
# Created by StrategyManager
subscription = StreamSubscription(
    mode="data-driven" if speed==0 else "clock-driven",
    stream_id=f"processor->strategy:{strategy_name}"
)

# StrategyThread signals ready
def _processing_loop(self):
    while not stopped:
        notification = self.queue.get(timeout=1.0)
        if notification:
            self._process_notification(notification)
            self._subscription.signal_ready()  # Signal to DataProcessor
```

**DataProcessor Waits**:
```python
# After notifying all subscribed strategies
for subscription in active_strategy_subscriptions:
    ready = subscription.wait_until_ready(timeout=1.0)
    if not ready:
        logger.warning(f"Strategy {subscription.stream_id} timeout")
    subscription.reset()
```

### Queue-Based Notifications

**Why Queues?**:
- Each strategy has its own queue
- Decouples DataProcessor from strategy execution
- Allows selective routing (only notify subscribed strategies)
- Buffers notifications if strategy is slow

**Queue Management**:
- Max size: configurable (default 100)
- On full: log warning, drop oldest or block
- On empty: thread blocks with timeout

---

## Error Handling

### Strategy Errors

**During setup()**:
```python
try:
    success = strategy.setup(context)
    if not success:
        logger.error(f"Strategy {name} setup failed")
        # Don't start thread
except Exception as e:
    logger.error(f"Strategy {name} setup exception: {e}")
    # Mark as ERROR, don't start
```

**During on_bars()**:
```python
try:
    signals = strategy.on_bars(symbol, interval)
except Exception as e:
    logger.error(f"Strategy {name} error: {e}")
    self.error_count += 1
    # Continue processing (don't crash thread)
```

**During teardown()**:
```python
try:
    strategy.teardown(context)
except Exception as e:
    logger.error(f"Strategy {name} teardown failed: {e}")
    # Log but continue shutdown
```

---

## Migration from Current AnalysisEngine

### Phase 1: Create New Components

1. Create `strategies/` folder structure
2. Implement `BaseStrategy` abstract class
3. Implement `StrategyThread` class
4. Implement `StrategyManager` class
5. Implement `StrategyContext` dataclass

### Phase 2: Update Config Schema

1. Add `strategies` to `SessionDataConfig`
2. Add `StrategyConfig` model
3. Validate config format

### Phase 3: Wire into SystemManager

1. Create StrategyManager in SystemManager
2. Initialize during session start
3. Start strategy threads
4. Wire to DataProcessor
5. Handle shutdown

### Phase 4: Example Strategies

1. Convert current BaseStrategy to new format
2. Create example strategies:
   - Simple MA Cross
   - RSI Strategy
   - VWAP Strategy
3. Test with backtest

### Phase 5: Remove Old AnalysisEngine

1. Migrate any needed functionality
2. Remove `analysis_engine.py` (old version)
3. Update documentation

---

## File Organization

### New Files to Create

```
strategies/
├── __init__.py                    # Package marker
├── base.py                        # BaseStrategy abstract class
├── context.py                     # StrategyContext dataclass
└── examples/
    ├── __init__.py
    ├── simple_ma_cross.py         # Example strategy
    └── rsi_strategy.py            # Example strategy

app/threads/
├── strategy_manager.py            # NEW - StrategyManager class
└── strategy_thread.py             # NEW - StrategyThread class

app/models/
└── session_config.py              # UPDATE - Add StrategyConfig

docs/windsurf/
└── STRATEGY_FRAMEWORK.md          # NEW - Full documentation
```

### Files to Modify

```
app/managers/system_manager/api.py
- Add get_strategy_manager()
- Wire StrategyManager in lifecycle
- Update shutdown sequence

app/threads/data_processor.py
- Replace single AnalysisEngine queue with per-strategy queues
- Notify only subscribed strategies
- Wait for all strategy subscriptions

app/threads/session_coordinator.py
- Call strategy_manager.initialize()
- Call strategy_manager.start_strategies()
```

### Files to Remove (Eventually)

```
app/threads/analysis_engine.py    # After migration complete
```

---

## Testing Strategy

### Unit Tests

```
tests/unit/
├── test_strategy_manager.py      # StrategyManager tests
├── test_strategy_thread.py       # StrategyThread tests
└── test_base_strategy.py         # BaseStrategy tests
```

### Integration Tests

```
tests/integration/
└── test_strategy_execution.py    # End-to-end strategy tests
```

### E2E Tests

```
tests/e2e/
└── test_multi_strategy_backtest.py
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)

- [ ] Create `strategies/` folder structure
- [ ] Implement `BaseStrategy` abstract class
- [ ] Implement `StrategyContext` dataclass
- [ ] Add `StrategyConfig` to session config model
- [ ] Write unit tests for BaseStrategy

### Phase 2: Thread Infrastructure (Week 1)

- [ ] Implement `StrategyThread` class
- [ ] Add queue management
- [ ] Add StreamSubscription integration
- [ ] Add performance metrics
- [ ] Write unit tests for StrategyThread

### Phase 3: Manager (Week 2)

- [ ] Implement `StrategyManager` class
- [ ] Module loading logic
- [ ] Lifecycle management (start/pause/stop)
- [ ] Statistics aggregation
- [ ] Write unit tests for StrategyManager

### Phase 4: Integration (Week 2)

- [ ] Wire StrategyManager into SystemManager
- [ ] Update DataProcessor for multi-queue notifications
- [ ] Update session config loading
- [ ] Write integration tests

### Phase 5: Examples (Week 3)

- [ ] Create `SimpleMaCrossStrategy`
- [ ] Create `RsiStrategy`
- [ ] Create `VwapStrategy`
- [ ] Test with backtest

### Phase 6: Migration (Week 3)

- [ ] Migrate any needed functionality from old AnalysisEngine
- [ ] Remove old AnalysisEngine
- [ ] Update documentation
- [ ] Full E2E testing

---

## Success Criteria

1. ✅ Multiple strategies can run concurrently
2. ✅ Each strategy runs in own thread
3. ✅ Strategies load from config
4. ✅ Selective subscriptions work
5. ✅ Zero-copy SessionData access
6. ✅ Performance metrics collected
7. ✅ Pause/resume works
8. ✅ Graceful shutdown works
9. ✅ Backpressure detected and logged
10. ✅ Example strategies work in backtest

---

## Open Questions

1. **Strategy Communication**: Should strategies be able to communicate? (Probably no - keep isolated)
2. **Signal Routing**: Should StrategyManager collect all signals? Or direct to ExecutionManager?
3. **Resource Limits**: Should we limit number of concurrent strategies?
4. **Priority**: Should strategies have priority levels?
5. **Persistence**: Should strategy state be persisted between sessions?

---

## Comparison: Scanner vs Strategy Framework

| Feature | Scanner Framework | Strategy Framework |
|---------|------------------|-------------------|
| **Purpose** | Find qualifying symbols | Generate trading signals |
| **Execution** | Scheduled (pre-session, regular intervals) | Event-driven (on every bar) |
| **Threading** | Manager orchestrates, scanners sync | Each strategy in own thread |
| **Data Access** | Via context (setup/scan) | Zero-copy SessionData |
| **Lifecycle** | setup → scan → teardown | setup → on_bars loop → teardown |
| **Output** | List of symbols | Trading signals |
| **Config** | Pre-session + regular schedules | Subscriptions to symbol/interval |
| **Performance** | Timed per scan | Per-bar processing time |

**Key Difference**: Scanners are **scheduled**, strategies are **reactive**

---

## Next Steps

1. Review this plan with team/user
2. Get approval on architecture
3. Start Phase 1 implementation
4. Iterate based on feedback

---

## Status

**Created**: December 9, 2025  
**Status**: PLANNING  
**Next**: Await review and approval

