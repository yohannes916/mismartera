# Phase 1.1 Complete: Adhoc APIs Implemented

## ✅ Implemented APIs

All adhoc APIs have been added to `app/managers/data_manager/session_data.py`:

### 1. Scanner Framework Support

```python
def set_indicator_manager(indicator_manager: Any) → None
def set_session_coordinator(coordinator: Any) → None
def register_config_symbol(symbol: str) → None
def get_config_symbols() → Set[str]
```

### 2. Lightweight Data Provisioning

```python
def add_historical_bars(symbol: str, interval: str, days: int) → bool
def add_session_bars(symbol: str, interval: str) → bool
def add_indicator(symbol: str, indicator_type: str, config: dict) → bool
```

**Key Feature**: `add_indicator()` uses `requirement_analyzer` to automatically provision required bars (unified routine).

### 3. Full Symbol Management

```python
def add_symbol(symbol: str) → bool  # Idempotent
def remove_symbol_adhoc(symbol: str) → bool  # Lock-protected
```

### 4. Symbol Locking

```python
def lock_symbol(symbol: str, reason: str) → bool
def unlock_symbol(symbol: str) → bool
def is_symbol_locked(symbol: str) → bool
```

---

## Implementation Details

### Tracking Structures Added

Added to `SessionData.__init__`:
```python
self._config_symbols: Set[str] = set()  # Symbols from session_config
self._symbol_locks: Dict[str, str] = {}  # {symbol: reason}
self._indicator_manager: Optional[Any] = None  # Set by coordinator
self._session_coordinator: Optional[Any] = None  # Set by coordinator
```

### Key Features

#### 1. Automatic Bar Provisioning

`add_indicator()` uses the **UNIFIED** `requirement_analyzer` routine:

```python
# Example: SMA(20) on 1d bars
session_data.add_indicator("SPY", "sma", {
    "period": 20,
    "interval": "1d"
})

# Automatically provisions:
# 1. Historical 1d bars (40 days for warmup)
# 2. Session 1d bars (for real-time)
# 3. Registers with IndicatorManager
```

#### 2. Idempotent add_symbol()

```python
# First call - adds symbol
session_data.add_symbol("TSLA")  # Returns True

# Second call - no-op
session_data.add_symbol("TSLA")  # Returns False (already exists)
```

#### 3. Lock-Protected Removal

```python
# Lock symbol (position open)
session_data.lock_symbol("TSLA", "open_position")

# Try to remove - FAILS
session_data.remove_symbol_adhoc("TSLA")  # Returns False

# Unlock symbol (position closed)
session_data.unlock_symbol("TSLA")

# Now can remove
session_data.remove_symbol_adhoc("TSLA")  # Returns True
```

---

## Integration Points

### TODO Items (Phase 2)

The following calls need to be wired up to SessionCoordinator:

1. **add_historical_bars**: Call `coordinator.load_historical_bars(symbol, interval, days)`
2. **add_session_bars**: Call `coordinator.start_bar_stream(symbol, interval)`
3. **add_symbol**: Call `await coordinator.add_symbol_mid_session(symbol)`

Currently these have placeholder TODOs in the code.

---

## Usage Example

```python
from app.managers.data_manager.session_data import get_session_data

session_data = get_session_data()

# Set references (called by coordinator)
session_data.set_indicator_manager(indicator_manager)
session_data.set_session_coordinator(coordinator)

# Register config symbols
session_data.register_config_symbol("AAPL")
session_data.register_config_symbol("MSFT")

# Scanner uses adhoc APIs
for symbol in scanner_universe:
    # Add indicator - bars provisioned automatically!
    session_data.add_indicator(symbol, "sma", {
        "period": 20,
        "interval": "1d",
        "type": "trend"
    })

# Scanner promotes qualifying symbol
if qualifies:
    session_data.add_symbol("TSLA")  # Full loading via coordinator

# Scanner cleanup in teardown
for symbol in universe:
    if symbol not in qualifying:
        if not session_data.is_symbol_locked(symbol):
            session_data.remove_symbol_adhoc(symbol)
```

---

## Files Modified

1. ✅ `/home/yohannes/mismartera/backend/app/managers/data_manager/session_data.py`
   - Added tracking structures to `__init__`
   - Added 12 new methods (400+ lines)
   - All methods are thread-safe (use `self._lock`)

---

## Testing Notes

### Manual Testing

Can test the APIs directly:

```python
from app.managers.data_manager.session_data import get_session_data

sd = get_session_data()

# Test add_indicator with automatic provisioning
sd.add_indicator("SPY", "sma", {"period": 20, "interval": "1d"})

# Test locking
sd.lock_symbol("SPY", "test")
assert sd.is_symbol_locked("SPY")
sd.unlock_symbol("SPY")
assert not sd.is_symbol_locked("SPY")

# Test config symbols
sd.register_config_symbol("AAPL")
assert "AAPL" in sd.get_config_symbols()
```

### Integration Testing

Full integration testing will be done in Phase 3 once:
- Scanner framework is implemented
- SessionCoordinator integration is complete

---

## Next Steps: Phase 1.2

**Update Session Config Models** to support scanner configuration:

1. Add `ScannerSchedule` dataclass
2. Add `ScannerConfig` dataclass
3. Update `SessionDataConfig` to include `scanners: List[ScannerConfig]`

**File**: `app/models/session_config.py`

**Estimated Time**: 1-2 hours

---

## Summary

✅ **Phase 1.1 Complete**: All adhoc APIs implemented in SessionData  
✅ **Thread-Safe**: All methods use locking  
✅ **Unified Routine**: `add_indicator()` uses `requirement_analyzer`  
✅ **Lock Protection**: Symbol removal is protected  
✅ **Idempotent**: `add_symbol()` safe to call multiple times  

**Ready for Phase 1.2!** 🎯
