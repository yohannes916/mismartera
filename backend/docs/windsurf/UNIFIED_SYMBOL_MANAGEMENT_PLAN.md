# Unified Symbol Management Implementation Plan

**Date:** 2025-12-02  
**Status:** Implementation Ready  
**Objective:** Implement generalized session deactivation with lag-based detection and unified symbol add/remove operations

---

## Overview

Replace special-case mid-session symbol addition logic with a generalized lag-detection system that automatically manages session state. This approach handles multiple scenarios: mid-session addition, live reconnection, system pause/resume, etc.

---

## Core Concept

**Streaming loop monitors data lag and auto-manages session state:**
- Lag > threshold → Deactivate session (block external notifications)
- Lag ≤ threshold → Activate session (enable external notifications)
- Internal sync (SessionCoordinator ↔ DataProcessor) continues regardless
- External notifications (DataProcessor → AnalysisEngine) blocked when deactivated

---

## Phase 1: Configuration Model Updates

### 1.1 Add StreamingConfig Class

**File:** `/home/yohannes/mismartera/backend/app/models/session_config.py`

**Location:** After `GapFillerConfig`

```python
@dataclass
class StreamingConfig:
    """Streaming configuration for session coordinator.
    
    Controls automatic session state management based on data lag.
    
    Attributes:
        catchup_threshold_seconds: Lag threshold for session deactivation (default: 60)
                                   If streaming data is more than this many seconds behind
                                   current time, session is auto-deactivated to prevent
                                   notifying analysis engine of old data.
        catchup_check_interval: Check lag every N bars (default: 10)
                               Lower = more responsive, higher = less overhead
    """
    catchup_threshold_seconds: int = 60
    catchup_check_interval: int = 10
    
    def validate(self) -> None:
        """Validate streaming configuration."""
        if self.catchup_threshold_seconds < 1:
            raise ValueError("catchup_threshold_seconds must be >= 1")
        
        if not (1 <= self.catchup_check_interval <= 100):
            raise ValueError("catchup_check_interval must be between 1 and 100")
```

### 1.2 Update SessionDataConfig

**File:** `/home/yohannes/mismartera/backend/app/models/session_config.py`

**Location:** Line 208 (SessionDataConfig class)

```python
@dataclass
class SessionDataConfig:
    """Session data configuration.
    
    Attributes:
        symbols: List of symbols to trade/analyze
        streams: Requested data streams (coordinator determines streamed vs generated)
        streaming: Streaming behavior configuration
        historical: Historical data and indicators configuration
        gap_filler: Gap filler configuration (DataQualityManager)
    """
    symbols: List[str]
    streams: List[str]
    streaming: StreamingConfig = field(default_factory=StreamingConfig)  # NEW
    historical: HistoricalConfig = field(default_factory=HistoricalConfig)
    gap_filler: GapFillerConfig = field(default_factory=GapFillerConfig)
    
    def validate(self) -> None:
        """Validate session data configuration."""
        # ... existing validation ...
        
        # Validate streaming config
        self.streaming.validate()  # NEW
```

### 1.3 Update SessionConfig.from_dict

**File:** `/home/yohannes/mismartera/backend/app/models/session_config.py`

**Location:** Line 430-484 (within from_dict method)

```python
# Parse streaming config
stream_data = sd_data.get("streaming", {})
streaming = StreamingConfig(
    catchup_threshold_seconds=stream_data.get("catchup_threshold_seconds", 60),
    catchup_check_interval=stream_data.get("catchup_check_interval", 10)
)

# ... in SessionDataConfig construction ...
session_data_config = SessionDataConfig(
    symbols=symbols,
    streams=streams,
    streaming=streaming,  # NEW
    historical=historical,
    gap_filler=gap_filler
)
```

### 1.4 Update SessionConfig.to_dict

**File:** `/home/yohannes/mismartera/backend/app/models/session_config.py`

**Location:** Line 576-596 (within to_dict method)

```python
result["session_data_config"] = {
    "symbols": self.session_data_config.symbols,
    "streams": self.session_data_config.streams,
    "streaming": {  # NEW
        "catchup_threshold_seconds": self.session_data_config.streaming.catchup_threshold_seconds,
        "catchup_check_interval": self.session_data_config.streaming.catchup_check_interval
    },
    "historical": {
        # ... existing ...
    },
    "gap_filler": {
        # ... existing ...
    }
}
```

---

## Phase 2: SessionCoordinator Updates

### 2.1 Add State Variables

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** `__init__` method (around line 150)

```python
# Symbol management (thread-safe)
self._symbol_operation_lock = threading.Lock()
self._loaded_symbols: Set[str] = set()
self._pending_symbols: Set[str] = set()

# Streaming configuration
self._catchup_threshold = 60  # Will be set from config
self._catchup_check_interval = 10  # Will be set from config
```

### 2.2 Initialize from Config

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** `__init__` method (after state variables)

```python
# Load streaming configuration
if self.session_config.session_data_config.streaming:
    streaming_config = self.session_config.session_data_config.streaming
    self._catchup_threshold = streaming_config.catchup_threshold_seconds
    self._catchup_check_interval = streaming_config.catchup_check_interval
    logger.info(
        f"[CONFIG] Streaming: catchup_threshold={self._catchup_threshold}s, "
        f"check_interval={self._catchup_check_interval} bars"
    )
```

### 2.3 Parameterize Existing Methods

Add `symbols: Optional[List[str]] = None` parameter to:

1. **`_validate_and_mark_streams()`** (line ~1450)
2. **`_manage_historical_data()`** (line ~1661)
3. **`_load_backtest_queues()`** (line ~826)

**Pattern:**
```python
def _method_name(self, symbols: Optional[List[str]] = None):
    """Process symbols.
    
    Args:
        symbols: Symbols to process. If None, uses all from config.
    """
    symbols_to_process = symbols or self.session_config.session_data_config.symbols
    
    for symbol in symbols_to_process:
        # ... existing logic unchanged ...
```

### 2.4 Add Accessor Methods

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** After `__init__` (around line 300)

```python
# =========================================================================
# Public API - Thread-Safe Accessors
# =========================================================================

def get_loaded_symbols(self) -> Set[str]:
    """Get currently loaded symbols (thread-safe)."""
    with self._symbol_operation_lock:
        return self._loaded_symbols.copy()

def get_pending_symbols(self) -> Set[str]:
    """Get symbols waiting to be loaded (thread-safe)."""
    with self._symbol_operation_lock:
        return self._pending_symbols.copy()

def get_generated_data(self) -> Dict[str, List[int]]:
    """Get intervals that need generation per symbol (thread-safe)."""
    with self._symbol_operation_lock:
        return self._generated_data.copy()

def get_streamed_data(self) -> Dict[str, List[str]]:
    """Get data types being streamed per symbol (thread-safe)."""
    with self._symbol_operation_lock:
        return self._streamed_data.copy()
```

### 2.5 Implement add_symbol Method

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** After accessor methods

```python
def add_symbol(self, symbol: str, streams: Optional[List[str]] = None) -> bool:
    """Add symbol to session (thread-safe, can be called from any thread).
    
    The symbol is added to config and marked as pending. The streaming loop
    will automatically detect and process it.
    
    Args:
        symbol: Symbol to add
        streams: Data streams (default: ["1m"] for backtest)
    
    Returns:
        True if added, False if already exists
    """
    streams = streams or ["1m"]
    
    with self._symbol_operation_lock:
        # Check if already exists
        if symbol in self.session_config.session_data_config.symbols:
            logger.warning(f"[SYMBOL] {symbol} already in session")
            return False
        
        # Add to config (single source of truth)
        self.session_config.session_data_config.symbols.append(symbol)
        
        # Add to streams config
        if "1m" not in self.session_config.session_data_config.streams:
            self.session_config.session_data_config.streams.append("1m")
        
        # Mark as pending
        self._pending_symbols.add(symbol)
        
        logger.info(
            f"[SYMBOL] Added {symbol} to config with streams {streams}, "
            f"marked as pending"
        )
        return True
```

### 2.6 Implement remove_symbol Method

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py**

**Location:** After add_symbol method

```python
def remove_symbol(self, symbol: str) -> bool:
    """Remove symbol from session (thread-safe, can be called from any thread).
    
    Removes symbol from config, clears all queues, removes from session_data.
    Other threads naturally adapt by polling config.
    
    Args:
        symbol: Symbol to remove
    
    Returns:
        True if removed, False if not found
    """
    with self._symbol_operation_lock:
        # Check if exists
        if symbol not in self.session_config.session_data_config.symbols:
            logger.warning(f"[SYMBOL] {symbol} not in session")
            return False
        
        logger.info(f"[SYMBOL] Removing {symbol} from session")
        
        # Remove from config (single source of truth)
        self.session_config.session_data_config.symbols.remove(symbol)
        
        # Remove from loaded set
        self._loaded_symbols.discard(symbol)
        
        # Remove from pending (if was pending)
        self._pending_symbols.discard(symbol)
        
        # Clear and remove all queues for symbol
        queues_to_remove = [
            key for key in self._bar_queues.keys() 
            if key[0] == symbol
        ]
        for key in queues_to_remove:
            del self._bar_queues[key]
            logger.debug(f"[SYMBOL] Removed queue {key}")
        
        # Remove from streamed/generated tracking
        self._streamed_data.pop(symbol, None)
        self._generated_data.pop(symbol, None)
        
        logger.info(
            f"[SYMBOL] Removed {symbol} - "
            f"cleared {len(queues_to_remove)} queues"
        )
    
    # Remove from session_data (has its own lock)
    removed = self.session_data.remove_symbol(symbol)
    
    if removed:
        logger.info(f"[SYMBOL] Successfully removed {symbol} from session")
    else:
        logger.warning(f"[SYMBOL] {symbol} not found in session_data")
    
    return True
```

### 2.7 Implement _process_pending_symbols Method

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** Before _streaming_phase method

```python
def _process_pending_symbols(self):
    """Process pending symbols using existing infrastructure.
    
    No manual session deactivation - streaming loop handles it automatically
    based on data lag.
    """
    # Get pending (thread-safe)
    with self._symbol_operation_lock:
        pending = list(self._pending_symbols)
        self._pending_symbols.clear()
    
    if not pending:
        return
    
    logger.info(f"[SYMBOL] Processing {len(pending)} pending symbols: {pending}")
    
    # Pause streaming to safely modify queues
    self._stream_paused.clear()
    time.sleep(0.1)
    
    try:
        # Load symbols using existing methods (95% reuse)
        logger.info("[SYMBOL] Phase 1: Validating streams")
        self._validate_and_mark_streams(symbols=pending)
        
        logger.info("[SYMBOL] Phase 2: Loading historical data")
        self._manage_historical_data(symbols=pending)
        
        logger.info("[SYMBOL] Phase 3: Loading queues")
        self._load_backtest_queues(symbols=pending)
        
        # Mark as loaded
        with self._symbol_operation_lock:
            self._loaded_symbols.update(pending)
        
        logger.info(f"[SYMBOL] Loaded {len(pending)} symbols successfully")
        
    except Exception as e:
        logger.error(f"[SYMBOL] Error loading symbols: {e}", exc_info=True)
    finally:
        # Resume streaming
        self._stream_paused.set()
        logger.info("[SYMBOL] Streaming resumed - lag detection will manage session state")
```

### 2.8 Add Lag Detection to Streaming Loop

**File:** `/home/yohannes/mismartera/backend/app/threads/session_coordinator.py`

**Location:** Within `_streaming_phase` method (backtest section)

```python
def _streaming_phase(self):
    """Streaming phase with automatic session state management.
    
    Automatically deactivates session when processing old data (lag > threshold).
    Automatically reactivates session when caught up (lag ≤ threshold).
    
    This handles:
    - Mid-session symbol addition (new queues with old bars)
    - Live mode reconnection (backlog of missed data)
    - System pause/resume (queues build up)
    - Any scenario where streaming falls behind
    """
    
    logger.info(
        f"[STREAMING] Starting streaming phase "
        f"(catchup_threshold={self._catchup_threshold}s, "
        f"check_interval={self._catchup_check_interval} bars)"
    )
    
    bars_processed = 0
    
    while self._session_active:
        # Check for pending symbols
        if self._pending_symbols:
            self._process_pending_symbols()
            # Streaming resumes, lag check will handle session state
        
        # Check pause
        if not self._stream_paused.is_set():
            time.sleep(0.01)
            continue
        
        # Get oldest bar from all queues
        oldest_bar_info = self._get_oldest_bar_from_queues()
        if not oldest_bar_info:
            logger.info("[STREAMING] No more bars in queues")
            break
        
        symbol, interval, bar = oldest_bar_info
        
        # Get current time from TimeManager
        current_time = self._time_manager.get_current_time()
        
        # Periodically check lag and auto-manage session state
        if bars_processed % self._catchup_check_interval == 0:
            lag_seconds = (current_time - bar.timestamp).total_seconds()
            
            # Auto-manage session state based on lag
            if lag_seconds > self._catchup_threshold:
                # Processing old data - deactivate if not already
                if self.session_data._session_active:
                    logger.info(
                        f"[STREAMING] Lag detected ({lag_seconds:.1f}s > "
                        f"{self._catchup_threshold}s) - deactivating session "
                        f"(processing {symbol} bar at {bar.timestamp.strftime('%H:%M:%S')})"
                    )
                    self.session_data.deactivate_session()
            else:
                # Caught up to current data - activate if not already
                if not self.session_data._session_active:
                    logger.info(
                        f"[STREAMING] Caught up ({lag_seconds:.1f}s ≤ "
                        f"{self._catchup_threshold}s) - reactivating session "
                        f"(current bar: {symbol} at {bar.timestamp.strftime('%H:%M:%S')})"
                    )
                    self.session_data.activate_session()
        
        # Remove bar from queue
        queue_key = (symbol, interval)
        self._bar_queues[queue_key].popleft()
        
        # Validate trading hours using TimeManager
        with SessionLocal() as db_session:
            trading_session = self._time_manager.get_trading_session(
                db_session, 
                bar.timestamp.date()
            )
        
        if trading_session:
            market_open = datetime.combine(
                bar.timestamp.date(), 
                trading_session.regular_open
            )
            market_close = datetime.combine(
                bar.timestamp.date(), 
                trading_session.regular_close
            )
            
            # Only process bars within trading hours
            if market_open <= bar.timestamp < market_close:
                # Write to session_data
                self.session_data.append_bar(symbol, interval, bar)
                
                # Notify internal subscriber (DataProcessor)
                if self.data_processor_subscription:
                    self.data_processor_subscription.notify(
                        symbol=symbol,
                        interval=interval,
                        data_type="bars"
                    )
                    # DataProcessor will check session_active before notifying externally
            else:
                # Pre/post market bar - drop
                logger.debug(
                    f"[STREAMING] Dropped {symbol} bar at "
                    f"{bar.timestamp.strftime('%H:%M:%S')} (outside regular hours)"
                )
        
        # Advance time if needed (backtest mode)
        if self.mode == "backtest":
            if bar.timestamp >= current_time:
                # Advance to next minute
                next_time = bar.timestamp + timedelta(minutes=1)
                self._time_manager.set_backtest_time(next_time)
        
        bars_processed += 1
    
    logger.info(
        f"[STREAMING] Streaming phase complete "
        f"({bars_processed} bars processed)"
    )
```

---

## Phase 3: SessionData Updates

### 3.1 Add internal Parameter to Read Methods

**File:** `/home/yohannes/mismartera/backend/app/managers/data_manager/session_data.py`

**Location:** get_bars method (around line 400)

```python
def get_bars(
    self, 
    symbol: str, 
    interval: str,
    internal: bool = False
) -> Optional[List[BarData]]:
    """Get bars for symbol/interval.
    
    Args:
        symbol: Symbol to query
        interval: Bar interval (e.g., "1m", "5m")
        internal: If True, bypass session_active check.
                 Use True for internal threads (DataProcessor, DataQualityManager).
                 Use False (default) for external subscribers (AnalysisEngine).
    
    Returns:
        List of bars, or None if session deactivated (external callers only)
    """
    # Block external callers during deactivation
    if not internal and not self._session_active:
        return None
    
    with self._lock:
        symbol_data = self._symbols.get(symbol)
        if not symbol_data:
            return None
        
        # Return bars based on interval
        if interval == "1m":
            return symbol_data.bars_1m.copy()
        elif interval.endswith("m") and interval != "1m":
            minutes = int(interval[:-1])
            return symbol_data.bars_derived.get(minutes, []).copy()
        
        return None
```

### 3.2 Add remove_symbol Method

**File:** `/home/yohannes/mismartera/backend/app/managers/data_manager/session_data.py`

**Location:** After existing methods

```python
def remove_symbol(self, symbol: str) -> bool:
    """Remove symbol and all its data (thread-safe).
    
    Args:
        symbol: Symbol to remove
    
    Returns:
        True if removed, False if not found
    """
    with self._lock:
        if symbol not in self._symbols:
            return False
        
        # Remove SymbolSessionData
        del self._symbols[symbol]
        
        logger.info(
            f"[SESSION_DATA] Removed {symbol} "
            f"({len(self._symbols)} symbols remaining)"
        )
        
        return True
```

---

## Phase 4: DataProcessor Updates

### 4.1 Use internal=True for Reads

**File:** `/home/yohannes/mismartera/backend/app/threads/data_processor.py`

**Location:** Wherever session_data.get_bars() is called

```python
# Read bars with internal=True (bypasses session_active check)
bars_1m = self.session_data.get_bars(symbol, "1m", internal=True)
```

### 4.2 Check session_active Before External Notifications

**File:** `/home/yohannes/mismartera/backend/app/threads/data_processor.py`

**Location:** Where notifications are sent to analysis_queue

```python
def _notify_external_subscribers(
    self, 
    symbol: str, 
    interval: str, 
    data_type: str
):
    """Notify external subscribers if session is active.
    
    During catchup (session deactivated), skip notifications.
    """
    notification = (symbol, interval, data_type)
    
    # Check if session is active
    if not self.session_data._session_active:
        logger.debug(
            f"[DATA_PROCESSOR] Session deactivated - "
            f"skipping external notification for {notification}"
        )
        return
    
    # Session active - send notification
    if self._analysis_queue:
        self._analysis_queue.put(notification)
        logger.debug(f"[DATA_PROCESSOR] Notified: {notification}")
```

---

## Phase 5: Configuration File Updates

### 5.1 Update example_session.json

**File:** `/home/yohannes/mismartera/backend/session_configs/example_session.json`

**Location:** Inside session_data_config

```json
{
  "session_data_config": {
    "symbols": ["RIVN"],
    "streams": ["1m"],
    "streaming": {
      "catchup_threshold_seconds": 60,
      "catchup_check_interval": 10
    },
    "historical": {
      ...existing...
    },
    "gap_filler": {
      ...existing...
    }
  }
}
```

---

## Phase 6: Testing Plan

### 6.1 Unit Tests

**File:** `/home/yohannes/mismartera/backend/tests/unit/test_session_coordinator_lag_detection.py`

```python
"""Unit tests for session coordinator lag detection."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from app.threads.session_coordinator import SessionCoordinator

class TestLagDetection:
    """Test automatic session state management based on lag."""
    
    def test_deactivate_on_high_lag(self):
        """Session should deactivate when lag exceeds threshold."""
        # Setup: coordinator with 60s threshold
        # Queue with bars from 09:30, current time 12:00
        # Lag = 2.5 hours = 9000s > 60s
        # Expected: session deactivated
        pass
    
    def test_reactivate_on_low_lag(self):
        """Session should reactivate when lag drops below threshold."""
        # Setup: session deactivated, processing old bars
        # Eventually catch up to current time
        # Expected: session reactivated
        pass
    
    def test_check_interval(self):
        """Lag should only be checked every N bars."""
        # Setup: check_interval = 10
        # Process 15 bars
        # Expected: lag checked at bars 0, 10 (not every bar)
        pass
    
    def test_configuration_loading(self):
        """Streaming config should load from session config."""
        # Setup: session_config with custom threshold/interval
        # Expected: coordinator uses those values
        pass
```

### 6.2 Integration Tests

**File:** `/home/yohannes/mismartera/backend/tests/integration/test_symbol_management.py`

```python
"""Integration tests for symbol addition and removal."""

import pytest
from app.managers.system_manager import SystemManager
from app.models.database import SessionLocal

class TestSymbolManagement:
    """Test adding and removing symbols during active session."""
    
    @pytest.fixture
    def system_manager(self):
        """Create system manager with test config."""
        # Load test config via DataManager.get_bars()
        # Use Parquet files for test data
        pass
    
    def test_add_symbol_mid_session(self, system_manager):
        """Add symbol during active session.
        
        Uses DataManager API, TimeManager for all time operations.
        """
        # Start system with RIVN
        # Run until 10:00
        # Add AAPL
        # Verify:
        # - AAPL queue created
        # - Historical bars loaded (09:30-16:00)
        # - Session deactivated (lag > 60s)
        # - Bars processed quickly
        # - Session reactivated when caught up
        # - AAPL bars in session_data
        pass
    
    def test_remove_symbol(self, system_manager):
        """Remove symbol from active session."""
        # Start with RIVN, AAPL
        # Remove AAPL
        # Verify:
        # - AAPL not in config
        # - AAPL queues removed
        # - AAPL session_data removed
        # - Other threads skip AAPL
        pass
    
    def test_multiple_symbols(self, system_manager):
        """Add multiple symbols at once."""
        # Add AAPL, TSLA simultaneously
        # Verify both processed correctly
        pass
```

### 6.3 End-to-End Tests

**File:** `/home/yohannes/mismartera/backend/tests/e2e/test_full_backtest_with_dynamic_symbols.py`

```python
"""E2E test: Full backtest with dynamic symbol addition."""

import pytest
from datetime import datetime, time
from app.managers.system_manager import SystemManager
from app.models.database import SessionLocal

class TestFullBacktestDynamic:
    """Run full backtest with mid-session symbol changes."""
    
    @pytest.fixture
    def system_manager(self):
        """Create system manager with test config."""
        # Uses test fixtures from tests/fixtures/
        # Uses test data from tests/data/bar_data/
        pass
    
    def test_complete_flow(self, system_manager):
        """Complete backtest with symbol addition and removal.
        
        Setup:
        - Use test Parquet files via DataManager (tests/data/bar_data/)
        - TimeManager for all time operations
        - Start with RIVN only
        - Add AAPL at 10:00
        - Remove RIVN at 14:00
        - Run until market close
        
        Verify:
        - All bars processed correctly via session_data queries
        - No gaps in data (check bar timestamps)
        - Session state transitions correct (deactivate/reactivate on lag)
        - Symbol counts correct at each stage
        """
        # 1. Setup test data (via DataManager API)
        with SessionLocal() as db_session:
            dm = system_manager.get_data_manager()
            # Test data already in tests/data/bar_data/ Parquet files
        
        # 2. Start system
        system_manager.start()
        time_mgr = system_manager.get_time_manager()
        coordinator = system_manager._coordinator
        
        # 3. Verify initial state
        assert "RIVN" in coordinator.get_loaded_symbols()
        assert "AAPL" not in coordinator.get_loaded_symbols()
        
        # 4. Wait until 10:00 (use TimeManager)
        while time_mgr.get_current_time().time() < time(10, 0):
            time.sleep(0.1)
        
        # 5. Add AAPL and verify
        assert coordinator.add_symbol("AAPL") is True
        assert "AAPL" in coordinator.get_pending_symbols()
        
        # Wait for processing
        while "AAPL" in coordinator.get_pending_symbols():
            time.sleep(0.1)
        
        assert "AAPL" in coordinator.get_loaded_symbols()
        
        # Verify AAPL bars in session_data
        session_data = coordinator.session_data
        aapl_bars = session_data.get_bars("AAPL", "1m")
        assert aapl_bars is not None
        assert len(aapl_bars) > 0
        
        # 6. Wait until 14:00
        while time_mgr.get_current_time().time() < time(14, 0):
            time.sleep(0.1)
        
        # 7. Remove RIVN and verify
        assert coordinator.remove_symbol("RIVN") is True
        assert "RIVN" not in coordinator.get_loaded_symbols()
        
        # Verify RIVN removed from session_data
        rivn_bars = session_data.get_bars("RIVN", "1m")
        assert rivn_bars is None
        
        # 8. Run until market close
        while system_manager.is_running():
            time.sleep(0.1)
        
        # 9. Verify final state
        assert "AAPL" in coordinator.get_loaded_symbols()
        assert "RIVN" not in coordinator.get_loaded_symbols()
        
        # Verify no gaps in AAPL data
        aapl_bars_final = session_data.get_bars("AAPL", "1m")
        timestamps = [bar.timestamp for bar in aapl_bars_final]
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i-1]).total_seconds()
            assert gap == 60, f"Gap detected: {gap}s between bars"
```

---

## Implementation Order

1. ✅ Configuration models (Phase 1)
2. ✅ SessionData updates (Phase 3)
3. ✅ SessionCoordinator - accessor methods (Phase 2.1-2.4)
4. ✅ SessionCoordinator - add/remove methods (Phase 2.5-2.7)
5. ✅ SessionCoordinator - lag detection (Phase 2.8)
6. ✅ DataProcessor updates (Phase 4)
7. ✅ Configuration file (Phase 5)
8. ✅ Unit tests (Phase 6.1)
9. ✅ Integration tests (Phase 6.2)
10. ✅ E2E tests (Phase 6.3)

---

## Testing Guidelines

### Data Access
- ✅ **Use DataManager.get_bars() for all bar reads**
- ✅ **Use DataManager.write_bars() for test data setup**
- ✅ **Use Parquet files for integration/E2E tests**
- ❌ Never directly read/write to database in tests
- ❌ Never bypass DataManager API

### Time Operations
- ✅ **Use TimeManager.get_current_time() for all time queries**
- ✅ **Use TimeManager.get_trading_session() for market hours**
- ✅ **Use TimeManager.set_backtest_time() for time advancement**
- ❌ Never use datetime.now() or date.today()
- ❌ Never hardcode trading hours

### Logging
- ✅ **Use logger from app.logger (Loguru - already configured)**
- ✅ **Log all state transitions**
- ✅ **Log lag detection events**
- ✅ **Use appropriate levels (INFO, DEBUG, WARNING, ERROR)**

---

## Success Criteria

### Functional
- ✅ Symbol addition works mid-session
- ✅ Symbol removal works mid-session
- ✅ Session auto-deactivates on high lag
- ✅ Session auto-reactivates when caught up
- ✅ Internal sync continues during catchup
- ✅ External notifications blocked during catchup
- ✅ Works in both backtest and live mode

### Performance
- ✅ Lag check overhead minimal (check every N bars, not every bar)
- ✅ Catchup completes quickly (no external notifications = faster)
- ✅ No race conditions in symbol operations

### Quality
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ E2E test validates via session_data queries and assertions
- ✅ No gaps in data (verified by timestamp continuity)
- ✅ 100% bar quality maintained

---

## Documentation Updates

1. Update SYMBOL_LOADING_FLOW_ANALYSIS.md with new unified approach
2. Create SYMBOL_MANAGEMENT_API.md documenting add/remove methods
3. Update SESSION_ARCHITECTURE.md with lag detection details
4. Add examples to docs/examples/

---

## Rollback Plan

If implementation issues arise:
1. Revert config model changes
2. Remove lag detection from streaming loop
3. Keep existing mid-session logic
4. Document issues for future iteration

---

## Notes

- This approach eliminates special-case logic
- Makes system robust against multiple scenarios
- Reduces coupling between components
- Enables self-adapting behavior
- Future-proof for live mode
