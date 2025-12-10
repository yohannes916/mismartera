# Phase 2.1 Complete: Scanner Base Classes

## ✅ Implemented

Created the base scanner framework classes and infrastructure.

---

## Files Created

### 1. `scanners/__init__.py`

Package initialization with exports:
```python
from scanners.base import (
    BaseScanner,
    ScanContext,
    ScanResult,
)
```

**Purpose**: Clean API surface for scanner imports.

---

### 2. `scanners/base.py`

Complete base scanner framework with 3 main classes:

#### A. ScanContext

```python
@dataclass
class ScanContext:
    """Context provided to scanner methods.
    
    Attributes:
        session_data: SessionData instance for data access
        time_manager: TimeManager instance for time operations
        mode: Execution mode ("backtest" or "live")
        current_time: Current time (simulated or real)
        config: Scanner-specific configuration
    """
    session_data: Any
    time_manager: Any
    mode: str
    current_time: datetime
    config: Dict[str, Any]
```

**Purpose**: Provides scanners access to system components.

---

#### B. ScanResult

```python
@dataclass
class ScanResult:
    """Result of a scan operation.
    
    Attributes:
        symbols: List of qualifying symbols found
        metadata: Optional metadata (counts, criteria, etc.)
        execution_time_ms: Time taken to execute scan
        skipped: Whether scan was skipped (overlap)
        error: Error message if scan failed
    """
    symbols: List[str]
    metadata: Dict[str, Any]
    execution_time_ms: float
    skipped: bool
    error: Optional[str]
```

**Purpose**: Structured return type for scan operations.

---

#### C. BaseScanner (Abstract)

```python
class BaseScanner(ABC):
    """Base class for all scanners.
    
    Lifecycle:
    1. setup() - Called once before session starts
    2. scan() - Called on schedule (abstract, must implement)
    3. teardown() - Called after last scheduled scan
    """
    
    def __init__(self, config: Dict[str, Any])
    def setup(self, context: ScanContext) -> bool
    @abstractmethod
    def scan(self, context: ScanContext) -> ScanResult
    def teardown(self, context: ScanContext) -> None
    def _load_universe_from_file(self, file_path: str) -> List[str]
    def _get_scanner_name(self) -> str
```

**Key Features**:
- Abstract `scan()` method (must be implemented)
- Default `setup()` and `teardown()` (can be overridden)
- Built-in `_load_universe_from_file()` helper
- Automatic scanner name derivation

---

## Helper Methods

### 1. _load_universe_from_file()

```python
def _load_universe_from_file(self, file_path: str) -> List[str]:
    """Load universe symbols from text file.
    
    File format:
    - One symbol per line
    - Lines starting with # are comments
    - Blank lines ignored
    - Symbols automatically uppercased
    
    Handles both relative and absolute paths.
    Relative paths resolved from backend directory.
    """
```

**Example Universe File**:
```
# SP500 Technology Stocks
AAPL
MSFT
GOOGL
# Semiconductors
NVDA
AMD
TSM
```

---

### 2. _get_scanner_name()

```python
def _get_scanner_name(self) -> str:
    """Get scanner name from class name.
    
    Examples:
    - GapScanner → "gap_scanner"
    - MomentumScanner → "momentum_scanner"
    - MyCustomScanner → "my_custom_scanner"
    """
```

**Purpose**: Automatic naming for logging and tracking.

---

## Scanner Lifecycle

### Complete Flow

```
┌──────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION                                         │
│    scanner = GapScanner(config)                          │
│    scanner.__init__(config)                              │
└──────────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────┐
│ 2. SETUP (Before session starts, clock STOPPED)          │
│    scanner.setup(context)                                │
│    ├─ Load universe from file                            │
│    ├─ Provision lightweight data (add_indicator)         │
│    └─ Return True if successful                          │
└──────────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────────┐
│ 3. SCAN (On schedule, clock STOPPED in backtest)         │
│    result = scanner.scan(context)                        │
│    ├─ Query lightweight data                             │
│    ├─ Apply criteria                                     │
│    ├─ Promote qualifying symbols (add_symbol)            │
│    └─ Return ScanResult                                  │
└──────────────────────────────────────────────────────────┘
                        ↓
                  (Repeat scans on schedule)
                        ↓
┌──────────────────────────────────────────────────────────┐
│ 4. TEARDOWN (After last scan, clock STOPPED)             │
│    scanner.teardown(context)                             │
│    ├─ Remove unqualified symbols (remove_symbol_adhoc)   │
│    ├─ Free resources                                     │
│    └─ Cleanup complete                                   │
└──────────────────────────────────────────────────────────┘
```

---

## Usage Example

```python
from scanners.base import BaseScanner, ScanContext, ScanResult
from app.logger import logger


class MyScanner(BaseScanner):
    """Custom scanner example."""
    
    MIN_VOLUME = 1_000_000
    
    def setup(self, context: ScanContext) -> bool:
        """Setup lightweight data."""
        # Load universe
        universe_file = self.config.get("universe")
        self._universe = self._load_universe_from_file(universe_file)
        
        logger.info(f"Loaded {len(self._universe)} symbols")
        
        # Provision lightweight data
        for symbol in self._universe:
            # Add indicator - bars auto-provisioned!
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20,
                "interval": "1d"
            })
        
        return True
    
    def scan(self, context: ScanContext) -> ScanResult:
        """Scan universe for qualifying symbols."""
        results = []
        
        for symbol in self._universe:
            # Get data
            symbol_data = context.session_data.get_symbol_data(symbol)
            if not symbol_data:
                continue
            
            # Check criteria
            if self._meets_criteria(symbol_data):
                # Promote to full symbol (idempotent)
                context.session_data.add_symbol(symbol)
                results.append(symbol)
        
        return ScanResult(
            symbols=results,
            metadata={"total_scanned": len(self._universe)}
        )
    
    def teardown(self, context: ScanContext):
        """Cleanup unused symbols."""
        config_symbols = context.session_data.get_config_symbols()
        
        for symbol in self._universe:
            # Skip config symbols
            if symbol in config_symbols:
                continue
            
            # Remove if not locked
            if not context.session_data.is_symbol_locked(symbol):
                context.session_data.remove_symbol_adhoc(symbol)
    
    def _meets_criteria(self, symbol_data) -> bool:
        """Check if symbol meets criteria."""
        # Example: Check volume
        if symbol_data.metrics.volume < self.MIN_VOLUME:
            return False
        
        return True
```

---

## Integration with Existing Code

### Updated gap_scanner_complete.py

- ✅ Imports from `scanners.base`
- ✅ Inherits from `BaseScanner`
- ✅ Uses `ScanContext` and `ScanResult`
- ✅ Removed duplicate `_load_universe_from_file()` (uses base)
- ✅ Full working example

**Usage**:
```python
from scanners.examples.gap_scanner_complete import GapScannerComplete

scanner = GapScannerComplete(config={"universe": "data/universes/sp500.txt"})
```

---

## Key Design Patterns

### 1. Abstract Base Class

```python
class BaseScanner(ABC):
    @abstractmethod
    def scan(self, context: ScanContext) -> ScanResult:
        """Must be implemented by subclasses."""
        pass
```

**Benefit**: Enforces scanner contract.

---

### 2. Context Object Pattern

```python
context = ScanContext(
    session_data=session_data,
    time_manager=time_manager,
    mode="backtest",
    current_time=datetime.now(),
    config=scanner_config
)
```

**Benefit**: Clean dependency injection.

---

### 3. Result Object Pattern

```python
return ScanResult(
    symbols=["TSLA", "NVDA"],
    metadata={"scanned": 500, "qualified": 2},
    execution_time_ms=123.45
)
```

**Benefit**: Structured, extensible return values.

---

### 4. Helper Methods

```python
# Universe loading (built-in)
symbols = self._load_universe_from_file("data/universes/sp500.txt")

# Scanner naming (built-in)
name = self._get_scanner_name()  # "gap_scanner"
```

**Benefit**: Code reuse across all scanners.

---

## Path Resolution

### Universe File Paths

**Relative paths** (recommended):
```python
"universe": "data/universes/sp500.txt"
# Resolved to: /home/user/mismartera/backend/data/universes/sp500.txt
```

**Absolute paths**:
```python
"universe": "/full/path/to/universe.txt"
# Used as-is
```

**Resolution Logic**:
1. Check if path is absolute
2. If relative, resolve from backend directory
3. Validate file exists
4. Parse and return symbols

---

## Error Handling

### Built-in Validation

```python
# FileNotFoundError
symbols = self._load_universe_from_file("nonexistent.txt")
# Raises: FileNotFoundError: Universe file not found: ...

# ValueError (empty file)
symbols = self._load_universe_from_file("empty.txt")
# Raises: ValueError: No symbols found in universe file: ...
```

---

## Files Modified

1. ✅ Created `/home/yohannes/mismartera/backend/scanners/__init__.py`
2. ✅ Created `/home/yohannes/mismartera/backend/scanners/base.py`
3. ✅ Updated `/home/yohannes/mismartera/backend/scanners/examples/gap_scanner_complete.py`

---

## Next Steps: Phase 2.2

**Scanner Manager Implementation**

What's needed:
- Create `app/threads/scanner_manager.py`
- Load scanners from config
- Execute lifecycle methods
- Handle blocking (backtest) vs async (live)
- Track scanner state machine
- Call teardown after last scan

**Estimated Time**: 6-8 hours

---

## Summary

✅ **Phase 2.1 Complete**: Scanner base classes implemented  
✅ **Abstract Base**: Enforces scanner contract  
✅ **Context Pattern**: Clean dependency injection  
✅ **Helper Methods**: Universe loading, naming  
✅ **Path Resolution**: Relative/absolute support  
✅ **Error Handling**: Built-in validation  
✅ **Example Updated**: Working gap scanner  

**Ready for Phase 2.2: Scanner Manager!** 🚀
