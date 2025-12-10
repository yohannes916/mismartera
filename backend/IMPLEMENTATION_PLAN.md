# Scanner Framework & Adhoc API - Implementation Plan

## Overview

Implement the complete scanner framework with adhoc data management APIs.

---

## Phase 1: Adhoc APIs (Foundation)

### 1.1 Add Adhoc Methods to SessionData

**File**: `app/managers/data_manager/session_data.py`

**New Methods**:
```python
def add_historical_bars(symbol: str, interval: str, days: int) → bool
def add_session_bars(symbol: str, interval: str) → bool
def add_indicator(symbol: str, indicator_type: str, config: dict) → bool
def add_symbol(symbol: str) → bool
def remove_symbol(symbol: str) → bool
def lock_symbol(symbol: str, reason: str) → bool
def unlock_symbol(symbol: str) → bool
def is_symbol_locked(symbol: str) → bool
def get_config_symbols() → Set[str]
```

**Integration Points**:
- Use existing `requirement_analyzer` for indicator bar provisioning
- Use existing `add_symbol_mid_session()` from SessionCoordinator
- Track adhoc symbols separately from config symbols

**Estimated Time**: 4-6 hours

---

### 1.2 Update Session Config Models

**File**: `app/models/session_config.py`

**Add Scanner Configuration**:
```python
@dataclass
class ScannerSchedule:
    start: str
    end: str
    interval: str

@dataclass
class ScannerConfig:
    module: str
    enabled: bool
    pre_session: bool
    regular_session: Optional[List[ScannerSchedule]]
    config: Dict[str, Any]

@dataclass
class SessionDataConfig:
    # ... existing fields
    scanners: List[ScannerConfig] = field(default_factory=list)
```

**Estimated Time**: 1-2 hours

---

## Phase 2: Scanner Base Framework

### 2.1 Create Base Scanner Classes

**File**: `scanners/base.py`

**Classes**:
```python
@dataclass
class ScanContext:
    session_data: SessionData
    time_manager: TimeManager
    mode: str
    current_time: datetime
    config: Dict[str, Any]

@dataclass
class ScanResult:
    symbols: List[str]
    metadata: Dict[str, Any]
    execution_time_ms: float
    skipped: bool
    error: Optional[str]

class BaseScanner(ABC):
    def __init__(self, config: Dict[str, Any])
    def setup(self, context: ScanContext) → bool
    @abstractmethod
    def scan(self, context: ScanContext) → ScanResult
    def teardown(self, context: ScanContext)
    def _load_universe_from_file(self, file_path: str) → List[str]
```

**Estimated Time**: 2-3 hours

---

### 2.2 Create Scanner Manager

**File**: `app/threads/scanner_manager.py`

**Class**: `ScannerManager`

**Responsibilities**:
- Load scanner modules from config
- Execute setup() for all scanners
- Execute pre-session scans
- Schedule regular session scans
- Track scanner state (IDLE, SETTING_UP, READY, SCANNING, TEARING_DOWN, DONE)
- Handle blocking (backtest) vs async (live) execution
- Call teardown() after last scheduled scan

**Key Methods**:
```python
def load_scanners()
def setup_all() → int
def execute_pre_session_scans()
def should_run_scan(scanner_name: str) → bool
def execute_scheduled_scans()
def _execute_scan(scanner_name: str, scanner: BaseScanner) → ScanResult
async def _execute_scan_async(scanner_name: str, scanner: BaseScanner) → ScanResult
def _process_scan_result(scanner_name: str, result: ScanResult)
```

**Estimated Time**: 6-8 hours

---

### 2.3 Integrate with SessionCoordinator

**File**: `app/threads/session_coordinator.py`

**Changes**:
```python
class SessionCoordinator:
    def __init__(self):
        # ... existing
        self.scanner_manager = ScannerManager(
            session_config=self.session_config,
            session_data=self.session_data,
            time_manager=self._time_manager,
            session_coordinator=self
        )
    
    async def _coordinator_loop(self):
        # Before session activation:
        self.scanner_manager.load_scanners()
        self.scanner_manager.setup_all()
        self.scanner_manager.execute_pre_session_scans()
        
        # In streaming loop:
        self.scanner_manager.execute_scheduled_scans()
```

**Estimated Time**: 2-3 hours

---

## Phase 3: Example Scanners & Testing

### 3.1 Create Example Scanners

**Files**:
- `scanners/gap_scanner.py` - Pre-market gap scanner
- `scanners/momentum_scanner.py` - Intraday momentum scanner
- `scanners/examples/gap_scanner_complete.py` - Full documented example

**Estimated Time**: 3-4 hours

---

### 3.2 Create Universe Files

**Files**:
- `data/universes/sp500_sample.txt` - Sample SP500 (already created ✅)
- `data/universes/nasdaq100_sample.txt` - Sample NASDAQ100 (already created ✅)
- `data/universes/test_universe.txt` - Small test set (5-10 symbols)

**Estimated Time**: 1 hour

---

### 3.3 Integration Tests

**File**: `tests/integration/test_scanner_framework.py`

**Test Cases**:
```python
def test_scanner_loading()
def test_scanner_setup()
def test_pre_session_scan()
def test_regular_session_scan()
def test_scanner_teardown()
def test_scanner_state_machine()
def test_backtest_blocking()
def test_live_async()
def test_skip_on_overlap()
def test_automatic_bar_provisioning()
def test_symbol_cleanup()
```

**Estimated Time**: 4-6 hours

---

## Phase 4: Documentation & Polish

### 4.1 User Documentation

**Files**:
- `docs/SCANNER_GUIDE.md` - How to create scanners
- `docs/SCANNER_API_REFERENCE.md` - Complete API docs
- Update existing design docs

**Estimated Time**: 3-4 hours

---

### 4.2 Example Session Config

**File**: `session_configs/scanner_example.json`

**Content**: Full example with scanners configured

**Estimated Time**: 1 hour

---

## Total Time Estimates

| Phase | Task | Hours |
|-------|------|-------|
| **Phase 1** | Adhoc APIs | 5-8 |
| **Phase 2** | Scanner Framework | 10-14 |
| **Phase 3** | Examples & Tests | 8-11 |
| **Phase 4** | Documentation | 4-5 |
| **Total** | | **27-38 hours** |

---

## Implementation Order

### Step 1: Adhoc APIs (Phase 1)
- Add methods to SessionData
- Update session config models
- **Deliverable**: Can manually call adhoc APIs

### Step 2: Scanner Base (Phase 2.1-2.2)
- Create base classes
- Create scanner manager
- **Deliverable**: Can load and execute scanners manually

### Step 3: Integration (Phase 2.3)
- Wire into SessionCoordinator
- **Deliverable**: Scanners run automatically in session

### Step 4: Examples (Phase 3.1-3.2)
- Create example scanners
- Create universe files
- **Deliverable**: Working scanner examples

### Step 5: Testing (Phase 3.3)
- Integration tests
- **Deliverable**: Verified working system

### Step 6: Documentation (Phase 4)
- User guides
- API reference
- **Deliverable**: Complete documentation

---

## Dependencies & Prerequisites

### Already Complete ✅
- ✅ `requirement_analyzer` - Bar requirement analysis
- ✅ `IndicatorManager` - Indicator registration and calculation
- ✅ `SessionCoordinator.add_symbol_mid_session()` - Dynamic symbol addition
- ✅ `DataProcessor` - Bar and indicator processing
- ✅ `session_data` - Data storage and querying
- ✅ Design documents - Complete architectural design

### Need to Implement
- [ ] Adhoc APIs in SessionData
- [ ] Scanner base classes
- [ ] Scanner manager
- [ ] SessionCoordinator integration
- [ ] Example scanners

---

## Testing Strategy

### Unit Tests
- Test each adhoc API method
- Test scanner base class methods
- Test scanner manager state machine

### Integration Tests
- Test full scanner lifecycle
- Test pre-session vs regular session
- Test backtest vs live modes
- Test symbol provisioning and cleanup

### Manual Tests
- Run with test session config
- Verify logs show scanner activity
- Check session_data contents
- Verify symbol addition/removal

---

## Success Criteria

### Phase 1 Complete
- [ ] Can call `add_indicator()` and bars are provisioned
- [ ] Can call `add_symbol()` and symbol is loaded
- [ ] Can call `lock_symbol()` and `remove_symbol()` fails

### Phase 2 Complete
- [ ] Scanners load from config
- [ ] setup() called before session
- [ ] Pre-session scans execute
- [ ] Regular session scans execute on schedule
- [ ] teardown() called after last scan

### Phase 3 Complete
- [ ] Example scanners work
- [ ] Integration tests pass
- [ ] Symbol cleanup works correctly

### Phase 4 Complete
- [ ] Documentation complete
- [ ] User can create custom scanner in <30 min

---

## Ready to Start!

**Recommended Starting Point**: Phase 1.1 - Add adhoc methods to SessionData

This provides the foundation for everything else.

**Next Steps**:
1. Implement `add_historical_bars()` in SessionData
2. Implement `add_session_bars()` in SessionData
3. Implement `add_indicator()` with requirement_analyzer integration
4. Implement symbol management APIs
5. Test adhoc APIs manually

**Proceed with Phase 1.1?** 🚀
