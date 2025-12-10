# Symbol Scanner Framework - Design

## Overview

Dynamic symbol discovery and filtering system that integrates with session_data and session_coordinator to add symbols on-demand based on custom criteria.

---

## Core Concepts

### What is a Scanner?

A **scanner** is a Python module that:
1. **Discovers** symbols that meet specific criteria
2. **Registers** indicators/data needed for evaluation
3. **Filters** symbols based on technical/fundamental conditions
4. **Adds** qualifying symbols to the active session

### Use Cases

- **Pre-session screening**: Filter universe before trading starts
- **Intraday momentum**: Detect breakouts during session
- **Gap scanners**: Find pre-market gaps
- **Volume spikes**: Detect unusual activity
- **Sector rotation**: Monitor relative strength

---

## Architecture

### Component Hierarchy

```
session_config.json
    └─ scanners: [...]
         ↓
SessionCoordinator
    └─ ScannerManager
         ├─ load_scanner(name)
         ├─ schedule_scan(scanner, schedule)
         └─ execute_scan(scanner, context)
              ↓
BaseScanner (ABC)
    ├─ setup(context)      # One-time initialization
    ├─ scan(context)       # Periodic execution
    └─ teardown(context)   # Cleanup
         ↓
ConcreteScanner (user implementation)
    └─ implements scan logic
         ↓
session_data.add_indicator(symbol, config)
session_data.add_symbol(symbol)
```

---

## Configuration Schema

### session_config.json

```json
{
  "session_data_config": {
    "symbols": ["AAPL", "MSFT"],
    "streams": ["1m"],
    
    "scanners": [
      {
        "name": "gap_scanner",
        "module": "scanners.gap_scanner",
        "enabled": true,
        
        "pre_session": true,
        
        "schedule": {
          "interval": "5m",
          "start_time": "09:35",
          "end_time": "15:55",
          "days_of_week": ["Mon", "Tue", "Wed", "Thu", "Fri"]
        },
        
        "config": {
          "min_gap_percent": 2.0,
          "min_volume": 1000000,
          "max_price": 500.0,
          "universe": "sp500"
        },
        
        "symbol_requirements": {
          "streams": ["1m", "5m"],
          "load_historical": true,
          "historical_days": 5
        },
        
        "timeout_seconds": 30
      },
      
      {
        "name": "momentum_scanner",
        "module": "scanners.momentum",
        "enabled": true,
        "pre_session": false,
        
        "schedule": {
          "interval": "15m",
          "start_time": "09:30",
          "end_time": "16:00"
        },
        
        "config": {
          "min_rsi": 70,
          "min_volume_ratio": 2.0
        }
      }
    ]
  }
}
```

---

## Base Scanner Class

### scanners/base.py

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ScanContext:
    """Context provided to scanner during execution.
    
    Attributes:
        session_data: Reference to SessionData
        time_manager: Reference to TimeManager
        mode: "backtest" or "live"
        current_time: Current session time
        config: Scanner-specific config from session_config
    """
    session_data: 'SessionData'
    time_manager: 'TimeManager'
    mode: str
    current_time: datetime
    config: Dict[str, Any]


@dataclass
class ScanResult:
    """Result from a scan execution.
    
    Attributes:
        symbols: List of symbols that passed criteria
        metadata: Additional info per symbol (optional)
        execution_time_ms: How long scan took
        skipped: True if scan was skipped
        error: Error message if scan failed
    """
    symbols: List[str]
    metadata: Dict[str, Any] = None
    execution_time_ms: float = 0.0
    skipped: bool = False
    error: Optional[str] = None


class BaseScanner(ABC):
    """Base class for all scanners.
    
    Lifecycle:
    1. __init__(config) - Constructor
    2. setup(context) - One-time initialization (pre-session)
    3. scan(context) - Called per schedule
    4. teardown(context) - Cleanup (optional)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize scanner with configuration.
        
        Args:
            config: Scanner-specific config from session_config
        """
        self.config = config
        self._indicators_registered = {}
        self._universe = []
    
    def setup(self, context: ScanContext) -> bool:
        """One-time setup before session starts.
        
        Called ONCE before session activation.
        Use this to:
        - Register indicators needed for scanning
        - Load universe of symbols to scan
        - Prepare data structures
        
        Args:
            context: Scan context
            
        Returns:
            True if setup successful, False to disable scanner
            
        Example:
            def setup(self, context):
                # Register SMA indicator for all universe symbols
                for symbol in self._load_universe():
                    context.session_data.add_indicator(
                        symbol,
                        IndicatorConfig(name="sma", period=20, interval="1d")
                    )
                return True
        """
        return True
    
    @abstractmethod
    def scan(self, context: ScanContext) -> ScanResult:
        """Execute scan and return qualifying symbols.
        
        Called per schedule (e.g., every 5m).
        
        Args:
            context: Scan context with session_data access
            
        Returns:
            ScanResult with qualifying symbols
            
        Example:
            def scan(self, context):
                results = []
                for symbol in self._universe:
                    sma = context.session_data.get_indicator(symbol, "sma_20_1d")
                    price = context.session_data.get_latest_price(symbol)
                    
                    if price > sma * 1.02:  # 2% above SMA
                        results.append(symbol)
                
                return ScanResult(symbols=results)
        """
        pass
    
    def teardown(self, context: ScanContext):
        """Cleanup resources (optional).
        
        Called at session end.
        """
        pass
    
    # Helper methods
    def _load_universe(self) -> List[str]:
        """Load universe of symbols to scan.
        
        Override this to customize symbol universe.
        """
        universe_name = self.config.get("universe", "sp500")
        
        # Load from file or API
        # For now, placeholder
        return ["AAPL", "MSFT", "TSLA", "NVDA", "GOOGL"]
```

---

## Scanner Manager

### app/threads/scanner_manager.py

```python
import importlib
import logging
from typing import Dict, List, Optional
from datetime import datetime, time
from pathlib import Path

from .base import BaseScanner, ScanContext, ScanResult

logger = logging.getLogger(__name__)


class ScannerManager:
    """Manages scanner lifecycle and scheduling.
    
    Responsibilities:
    - Load scanner modules from configuration
    - Schedule scanner execution
    - Execute scans (blocking in backtest, async in live)
    - Handle timeouts and errors
    - Add symbols from scan results
    """
    
    def __init__(
        self,
        session_config,
        session_data,
        time_manager,
        session_coordinator
    ):
        self.session_config = session_config
        self.session_data = session_data
        self.time_manager = time_manager
        self.session_coordinator = session_coordinator
        
        self.scanners: Dict[str, BaseScanner] = {}
        self.scanner_configs: Dict[str, dict] = {}
        self.scan_schedules: Dict[str, dict] = {}
        
        # Track running scans (for live mode)
        self.running_scans: Dict[str, asyncio.Task] = {}
        
        # Performance tracking
        self.scan_history: List[dict] = []
    
    def load_scanners(self):
        """Load and initialize all enabled scanners from config."""
        scanner_configs = self.session_config.session_data_config.get("scanners", [])
        
        for config in scanner_configs:
            if not config.get("enabled", True):
                continue
            
            name = config["name"]
            module_path = config["module"]
            
            try:
                # Import scanner module
                module = importlib.import_module(module_path)
                
                # Instantiate scanner class
                # Convention: module.Scanner or module.{Name}Scanner
                scanner_class = getattr(module, "Scanner", None)
                if scanner_class is None:
                    class_name = f"{name.replace('_', ' ').title().replace(' ', '')}Scanner"
                    scanner_class = getattr(module, class_name)
                
                scanner = scanner_class(config.get("config", {}))
                
                self.scanners[name] = scanner
                self.scanner_configs[name] = config
                self.scan_schedules[name] = config.get("schedule", {})
                
                logger.info(f"[SCANNER] Loaded: {name} from {module_path}")
                
            except Exception as e:
                logger.error(f"[SCANNER] Failed to load {name}: {e}", exc_info=True)
    
    def setup_all(self) -> int:
        """Run setup() for all scanners.
        
        Called before session starts.
        
        Returns:
            Number of successfully initialized scanners
        """
        success_count = 0
        
        for name, scanner in self.scanners.items():
            try:
                context = self._create_context(scanner)
                
                logger.info(f"[SCANNER] Setting up: {name}")
                success = scanner.setup(context)
                
                if success:
                    success_count += 1
                    logger.info(f"[SCANNER] Setup complete: {name}")
                else:
                    logger.warning(f"[SCANNER] Setup failed: {name}")
                    
            except Exception as e:
                logger.error(f"[SCANNER] Setup error {name}: {e}", exc_info=True)
        
        return success_count
    
    def execute_pre_session_scans(self):
        """Execute all scanners with pre_session=true.
        
        Called after setup, before session activation.
        """
        for name, scanner in self.scanners.items():
            config = self.scanner_configs[name]
            
            if not config.get("pre_session", False):
                continue
            
            logger.info(f"[SCANNER] Pre-session scan: {name}")
            
            try:
                result = self._execute_scan(name, scanner)
                self._process_scan_result(name, result)
                
            except Exception as e:
                logger.error(f"[SCANNER] Pre-session scan error {name}: {e}", exc_info=True)
    
    def should_run_scan(self, name: str) -> bool:
        """Check if scanner should run at current time.
        
        Args:
            name: Scanner name
            
        Returns:
            True if scan should execute now
        """
        schedule = self.scan_schedules.get(name, {})
        current_time = self.time_manager.get_current_time()
        
        # Check time window
        start_time_str = schedule.get("start_time")
        end_time_str = schedule.get("end_time")
        
        if start_time_str and end_time_str:
            start = time.fromisoformat(start_time_str)
            end = time.fromisoformat(end_time_str)
            
            if not (start <= current_time.time() <= end):
                return False
        
        # Check day of week
        days = schedule.get("days_of_week", [])
        if days:
            current_day = current_time.strftime("%a")
            if current_day not in days:
                return False
        
        # Check interval
        interval_str = schedule.get("interval", "5m")
        # Parse interval (e.g., "5m" -> check if current minute % 5 == 0)
        
        return True
    
    def execute_scheduled_scans(self):
        """Execute all scanners that are due.
        
        Called from SessionCoordinator streaming loop.
        """
        mode = self.session_config.mode
        
        for name, scanner in self.scanners.items():
            if not self.should_run_scan(name):
                continue
            
            # Check if previous scan still running (live mode only)
            if mode == "live" and name in self.running_scans:
                if not self.running_scans[name].done():
                    logger.warning(f"[SCANNER] Skipping {name} - previous scan still running")
                    continue
            
            # Execute scan
            if mode == "backtest":
                # Blocking
                result = self._execute_scan(name, scanner)
                self._process_scan_result(name, result)
            else:
                # Async
                task = asyncio.create_task(self._execute_scan_async(name, scanner))
                self.running_scans[name] = task
    
    def _execute_scan(self, name: str, scanner: BaseScanner) -> ScanResult:
        """Execute scan (blocking).
        
        Args:
            name: Scanner name
            scanner: Scanner instance
            
        Returns:
            ScanResult
        """
        config = self.scanner_configs[name]
        timeout = config.get("timeout_seconds", 30)
        
        context = self._create_context(scanner)
        
        start_time = time.time()
        
        try:
            result = scanner.scan(context)
            result.execution_time_ms = (time.time() - start_time) * 1000
            
            logger.info(
                f"[SCANNER] {name}: Found {len(result.symbols)} symbols "
                f"({result.execution_time_ms:.1f}ms)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[SCANNER] {name} failed: {e}", exc_info=True)
            return ScanResult(symbols=[], error=str(e))
    
    async def _execute_scan_async(self, name: str, scanner: BaseScanner) -> ScanResult:
        """Execute scan (async for live mode)."""
        # Wrap blocking scan in executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._execute_scan, name, scanner)
        self._process_scan_result(name, result)
        return result
    
    def _process_scan_result(self, name: str, result: ScanResult):
        """Process scan result by adding symbols.
        
        Args:
            name: Scanner name
            result: Scan result
        """
        if result.error or result.skipped:
            return
        
        config = self.scanner_configs[name]
        symbol_reqs = config.get("symbol_requirements", {})
        
        for symbol in result.symbols:
            # Check if already active
            if symbol in self.session_data.get_active_symbols():
                logger.debug(f"[SCANNER] {name}: {symbol} already active")
                continue
            
            # Add symbol mid-session
            logger.info(f"[SCANNER] {name}: Adding symbol {symbol}")
            
            # Use existing add_symbol_mid_session
            asyncio.create_task(
                self.session_coordinator.add_symbol_mid_session(
                    symbol=symbol,
                    streams=symbol_reqs.get("streams", ["1m"]),
                    load_historical=symbol_reqs.get("load_historical", True),
                    historical_days=symbol_reqs.get("historical_days", 5)
                )
            )
        
        # Track history
        self.scan_history.append({
            "scanner": name,
            "timestamp": self.time_manager.get_current_time(),
            "symbols_found": len(result.symbols),
            "symbols": result.symbols,
            "execution_time_ms": result.execution_time_ms
        })
    
    def _create_context(self, scanner: BaseScanner) -> ScanContext:
        """Create scan context."""
        return ScanContext(
            session_data=self.session_data,
            time_manager=self.time_manager,
            mode=self.session_config.mode,
            current_time=self.time_manager.get_current_time(),
            config=scanner.config
        )
```

---

## Example Scanner Implementation

### scanners/gap_scanner.py

```python
"""Gap Scanner - Finds stocks with pre-market gaps.

Criteria:
- Gap >= min_gap_percent from previous close
- Volume >= min_volume
- Price <= max_price
"""

from typing import List
from scanners.base import BaseScanner, ScanContext, ScanResult
from app.indicators import IndicatorConfig, IndicatorType


class Scanner(BaseScanner):
    """Detects gap-up/gap-down opportunities."""
    
    def setup(self, context: ScanContext) -> bool:
        """Setup indicators for all universe symbols."""
        # Load universe
        self._universe = self._load_universe()
        
        # Register indicators needed for scanning
        for symbol in self._universe:
            # Need previous day's close
            context.session_data.add_indicator(
                symbol,
                IndicatorConfig(
                    name="sma",
                    type=IndicatorType.TREND,
                    period=1,
                    interval="1d",
                    params={}
                )
            )
        
        return True
    
    def scan(self, context: ScanContext) -> ScanResult:
        """Find stocks with significant gaps."""
        min_gap_pct = self.config.get("min_gap_percent", 2.0)
        min_volume = self.config.get("min_volume", 1000000)
        max_price = self.config.get("max_price", 500.0)
        
        results = []
        metadata = {}
        
        for symbol in self._universe:
            # Get current price
            latest_bar = context.session_data.get_latest_bar(symbol, "1m")
            if not latest_bar:
                continue
            
            current_price = latest_bar.close
            
            # Get previous close (from 1d indicator)
            prev_close_indicator = context.session_data.get_indicator(symbol, "sma_1_1d")
            if not prev_close_indicator or not prev_close_indicator.valid:
                continue
            
            prev_close = prev_close_indicator.current_value
            
            # Calculate gap
            gap_pct = ((current_price - prev_close) / prev_close) * 100
            
            # Check criteria
            if abs(gap_pct) >= min_gap_pct:
                if latest_bar.volume >= min_volume:
                    if current_price <= max_price:
                        results.append(symbol)
                        metadata[symbol] = {
                            "gap_percent": gap_pct,
                            "volume": latest_bar.volume,
                            "price": current_price
                        }
        
        return ScanResult(
            symbols=results,
            metadata=metadata
        )
```

---

## Flow Diagrams

### Lifecycle Flow

```
┌─────────────────────────────────────────────────────────────┐
│ SessionCoordinator Initialization                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. Load Session Config                                       │
│    - Parse scanners section                                  │
│    - Create ScannerManager                                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ScannerManager.load_scanners()                           │
│    - Import scanner modules                                  │
│    - Instantiate scanner classes                             │
│    - Store in scanners dict                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. ScannerManager.setup_all()                               │
│    - Call scanner.setup(context) for each                    │
│    - Scanners register indicators via session_data           │
│    - Scanners load symbol universes                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. ScannerManager.execute_pre_session_scans()               │
│    - Execute scanners with pre_session=true                  │
│    - Add qualifying symbols via add_symbol_mid_session()     │
│    - BLOCKING in backtest mode                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. SessionCoordinator.register_symbol()                     │
│    - Load historical data for scan results                   │
│    - Register with session_data                              │
│    - Register indicators                                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Session Activation                                        │
│    - session_data.activate_session()                         │
│    - Start streaming                                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Streaming Loop                                            │
│    ├─ Process bars                                           │
│    ├─ Check scanner schedules                                │
│    └─ Execute scheduled scans                                │
│        ├─ Backtest: Blocking (pause streaming)               │
│        └─ Live: Async (non-blocking)                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Scan Results → Add Symbols                                │
│    - Scanner returns ScanResult with symbols                 │
│    - ScannerManager calls add_symbol_mid_session()           │
│    - SessionCoordinator loads data & registers               │
│    - AnalysisEngine can now trade these symbols              │
└─────────────────────────────────────────────────────────────┘
```

### Scan Execution Flow

```
BACKTEST MODE (Blocking):
─────────────────────────
┌─────────────────┐
│ Streaming Loop  │
└────────┬────────┘
         │
         ├─ Check schedule
         ├─ scanner.should_run() → True
         │
         ├─ PAUSE STREAMING ⏸️
         │
         ├─ Execute scanner.scan(context)
         │    ├─ Query session_data
         │    ├─ Check indicators
         │    └─ Return qualifying symbols
         │
         ├─ Process results
         │    └─ Add symbols mid-session
         │
         ├─ RESUME STREAMING ▶️
         │
         └─ Continue


LIVE MODE (Async):
──────────────────
┌─────────────────┐
│ Streaming Loop  │
└────────┬────────┘
         │
         ├─ Check schedule
         ├─ scanner.should_run() → True
         │
         ├─ Check if previous scan running
         │    ├─ Yes → Skip (log warning)
         │    └─ No → Continue
         │
         ├─ asyncio.create_task(scan)
         │    └─ Non-blocking
         │
         └─ Continue streaming ← No pause!

         (Scan completes in background)
              ↓
         Results processed
              ↓
         Symbols added
```

---

## Integration Points

### 1. SessionCoordinator

```python
# Add to SessionCoordinator.__init__()
self.scanner_manager = ScannerManager(
    session_config=self.session_config,
    session_data=self.session_data,
    time_manager=self._time_manager,
    session_coordinator=self
)

# Add to SessionCoordinator._coordinator_loop()
# Before session activation:
self.scanner_manager.load_scanners()
self.scanner_manager.setup_all()
self.scanner_manager.execute_pre_session_scans()

# In streaming loop:
self.scanner_manager.execute_scheduled_scans()
```

### 2. session_data

```python
# Already exists:
session_data.add_indicator(symbol, config)
session_data.get_indicator(symbol, key)
session_data.get_latest_bar(symbol, interval)

# May need:
session_data.get_latest_price(symbol)  # Convenience method
```

### 3. SessionConfig

```python
# Add to SessionDataConfig
@dataclass
class SessionDataConfig:
    symbols: List[str]
    streams: List[str]
    scanners: List[ScannerConfig] = field(default_factory=list)  # NEW
```

---

## Scanner Directory Structure

```
backend/
├─ scanners/
│  ├─ __init__.py
│  ├─ base.py               # BaseScanner, ScanContext, ScanResult
│  │
│  ├─ gap_scanner.py        # Example: Pre-market gaps
│  ├─ momentum_scanner.py   # Example: Intraday momentum
│  ├─ volume_scanner.py     # Example: Unusual volume
│  └─ sector_rotation.py    # Example: Relative strength
│
├─ app/
│  └─ threads/
│     ├─ session_coordinator.py
│     └─ scanner_manager.py  # NEW
│
└─ session_configs/
   └─ example_with_scanner.json
```

---

## Key Design Decisions

### 1. ✅ Scanners as Separate Modules

**Why:** 
- Easy to add custom scanners without modifying core
- Users can write their own scanners
- Clean separation of concerns

### 2. ✅ Setup vs Scan Separation

**Why:**
- Setup runs once (expensive operations: load universe, register indicators)
- Scan runs repeatedly (fast: query existing data)
- Clear lifecycle phases

### 3. ✅ Blocking in Backtest, Async in Live

**Why:**
- Backtest: Need deterministic results, acceptable to pause
- Live: Cannot block streaming, scans in background
- Skip if previous scan not done (prevent queue buildup)

### 4. ✅ Scanners Use session_data API

**Why:**
- No direct database access from scanners
- All data flows through session_data (single source of truth)
- Consistent with architecture principle

### 5. ✅ Scanners Add Symbols via Existing API

**Why:**
- Reuse add_symbol_mid_session() logic
- Automatic requirement analysis
- Automatic historical loading
- Lag detection/catchup applies

---

## Simplicity Principles

### What We AVOID:

❌ Complex scheduling DSL → Use simple interval/time window  
❌ Database queries from scanners → Use session_data only  
❌ Direct config modification → Scanners don't touch session_config  
❌ Custom threading → Use existing asyncio  
❌ State persistence → Scanners are stateless (except setup)  

### What We EMBRACE:

✅ Single base class → Easy to understand/extend  
✅ Three lifecycle methods → setup, scan, teardown  
✅ Existing APIs → add_symbol_mid_session, add_indicator  
✅ Configuration-driven → Everything in session_config  
✅ Composable → Multiple scanners can run together  

---

## Future Extensions (Not in MVP)

- Scanner state persistence (survive restarts)
- Scanner analytics dashboard
- Scanner backtesting (test scanner logic separately)
- Scanner composition (combine multiple scanners)
- Scanner alerts/notifications
- Dynamic universe management
- Scanner performance metrics export

---

## Summary

### Components

1. **BaseScanner** - ABC with setup/scan/teardown
2. **ScannerManager** - Lifecycle and scheduling
3. **ScanContext** - Data access for scanners
4. **ScanResult** - Output from scanners
5. **Configuration** - JSON schema in session_config

### Flow

1. Load scanners from config
2. Call setup() for each scanner
3. Execute pre-session scans
4. Add qualifying symbols
5. Start streaming
6. Execute scheduled scans
7. Process results and add symbols

### Key Benefits

✅ **Simple** - 3 methods to implement  
✅ **Extensible** - Easy to add custom scanners  
✅ **Integrated** - Uses existing adhoc indicator pattern  
✅ **Flexible** - Pre-session and mid-session support  
✅ **Performant** - Async in live mode  
✅ **Deterministic** - Blocking in backtest mode  

This design is ready for iteration and refinement!
