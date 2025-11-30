# Architecture Reorganization Plan

## 🎯 Problem Analysis

### Current Issues

#### 1. **Naming Confusion**
- Mixed terminology: "manager", "service", "thread", "engine"
- Unclear what each term means
- Example: `system_manager.py` (file) vs `time_manager/` (package)

#### 2. **Directory Organization**
```
app/
├── threads/           # Has coordinator, processor, quality manager, analysis engine
├── managers/          # Has time_manager/, data_manager/, execution_manager/, analysis_engine/
├── services/          # Has random stuff: auth, csv_import, probability engines
├── integrations/      # Has API clients: alpaca, schwab, claude
├── data/              # Only session_data.py (singleton store)
├── repositories/      # Only 2 repos (calendar, user)
└── ...
```

**Problems:**
- Duplicate `analysis_engine` (in both `/threads/` and `/managers/`)
- `data_manager/` has 15+ files including threads, configs, APIs
- `services/` contains unrelated utilities
- No clear separation of layers

#### 3. **Architectural Ambiguity**
- What's the difference between a "manager", "service", "thread"?
- Where do new features go?
- How do layers communicate?

---

## 🏗️ Proposed Architecture

### ⚠️ CRITICAL: Synchronous Thread Pool Model (NO ASYNCIO)

**Architecture Decision:**
- ✅ **Use `threading.Thread`** for all background workers
- ✅ **Use `SessionLocal`** (synchronous) for database access
- ✅ **Use `time.sleep()`** for delays, NOT `asyncio.sleep()`
- ✅ **Use `with` context managers**, NOT `async with`
- ❌ **NO `async def`** in threads, managers, services, repositories
- ❌ **NO `await`** keywords in core business logic
- ❌ **NO `AsyncSessionLocal`** anywhere

**Exception:** FastAPI REST API handlers in `app/api/routes/` may use async (FastAPI requirement only)

**Thread Communication:**
- ✅ Use `queue.Queue` (thread-safe queues)
- ✅ Use `threading.Event` (signals)
- ✅ Use `StreamSubscription` (custom notification system)
- ❌ NOT `asyncio.Queue` or coroutines

**Why This Matters:**
- Simpler mental model (no async/await complexity)
- Better performance for I/O-bound workloads with blocking operations
- Easier debugging (standard threading tools)
- Avoids mixing threading and asyncio (which causes errors)

---

### Clear Terminology

| Term | Definition | Example | Location |
|------|------------|---------|----------|
| **Thread** | Long-running background worker using `threading.Thread` (NOT asyncio) | `SessionCoordinator`, `DataProcessor` | `app/threads/` |
| **Manager** | Stateful orchestrator/facade providing high-level APIs (synchronous) | `TimeManager`, `DataManager`, `SystemManager` | `app/managers/` |
| **Service** | Stateless business logic utility (pure functions/classes, synchronous) | `GapDetectionService`, `BarAggregationService` | `app/services/` |
| **Repository** | Database access layer using `SessionLocal` (synchronous CRUD) | `TradingCalendarRepository`, `BarRepository` | `app/repositories/` |
| **Integration** | External API client wrapper (may use async internally if needed) | `AlpacaClient`, `SchwabClient` | `app/integrations/` |
| **Core** | Fundamental data structures and primitives | `SessionData`, `Bar`, `Quote` | `app/core/` |
| **API** | REST API routes and endpoints (FastAPI async handlers OK here only) | `market_data.py`, `auth.py` | `app/api/` |
| **CLI** | Command-line interface commands (synchronous) | `system_commands.py`, `data_commands.py` | `app/cli/` |

---

## 📁 New Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point
│   ├── logger.py                  # Logging configuration
│   │
│   ├── core/                      # ⭐ NEW: Fundamental data structures
│   │   ├── __init__.py
│   │   ├── data_structures/       # Bar, Quote, Tick, Trade
│   │   ├── session_data.py        # Unified session data store (singleton)
│   │   ├── enums.py               # SystemState, OperationMode, etc.
│   │   └── exceptions.py          # Custom exceptions
│   │
│   ├── config/                    # Configuration
│   │   ├── __init__.py
│   │   └── settings.py            # Global settings (NOT session config)
│   │
│   ├── models/                    # Database models (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── database.py            # DB connection, SessionLocal
│   │   ├── session_config.py      # SessionConfig (Pydantic models)
│   │   ├── trading_calendar.py    # TradingSession, MarketHours
│   │   ├── account.py             # Account, Position
│   │   ├── orders.py              # Order, Trade
│   │   └── user.py                # User, authentication
│   │
│   ├── repositories/              # Database access layer
│   │   ├── __init__.py
│   │   ├── bar_repository.py      # Bar CRUD operations
│   │   ├── calendar_repository.py # Trading calendar queries
│   │   ├── order_repository.py    # Order persistence
│   │   └── user_repository.py     # User queries
│   │
│   ├── services/                  # ⭐ REFACTORED: Stateless business logic
│   │   ├── __init__.py
│   │   ├── market_data/           # Market data services
│   │   │   ├── gap_detection.py   # Gap detection algorithms
│   │   │   ├── bar_aggregation.py # 1m → 5m, 15m, etc.
│   │   │   ├── quality_scoring.py # Quality calculation
│   │   │   └── parquet_storage.py # Parquet I/O
│   │   ├── indicators/            # Technical indicators
│   │   │   ├── moving_averages.py
│   │   │   ├── rsi.py
│   │   │   └── ...
│   │   ├── analysis/              # Analysis services
│   │   │   ├── probability_engine.py
│   │   │   └── signal_generator.py
│   │   ├── auth/                  # Authentication
│   │   │   └── auth_service.py
│   │   └── csv_import/            # CSV import utilities
│   │       └── csv_import_service.py
│   │
│   ├── integrations/              # External API clients
│   │   ├── __init__.py
│   │   ├── alpaca/
│   │   │   ├── __init__.py
│   │   │   └── client.py          # AlpacaClient
│   │   ├── schwab/
│   │   │   ├── __init__.py
│   │   │   └── client.py          # SchwabClient
│   │   └── claude/
│   │       ├── __init__.py
│   │       ├── client.py          # ClaudeClient
│   │       └── usage_tracker.py   # Claude usage tracking
│   │
│   ├── managers/                  # ⭐ CLEAN: High-level orchestrators
│   │   ├── __init__.py
│   │   ├── system_manager.py      # System orchestrator (singleton)
│   │   ├── time_manager/          # Time/calendar manager
│   │   │   ├── __init__.py
│   │   │   ├── api.py             # TimeManager class
│   │   │   ├── models.py          # TimeManager-specific models
│   │   │   └── repositories/      # Calendar repos
│   │   ├── data_manager/          # Market data manager
│   │   │   ├── __init__.py
│   │   │   ├── api.py             # DataManager class
│   │   │   ├── stream_manager.py  # Stream lifecycle
│   │   │   └── repositories/      # Bar repos
│   │   └── execution_manager/     # Order/execution manager
│   │       ├── __init__.py
│   │       ├── api.py             # ExecutionManager class
│   │       └── repositories/      # Order repos
│   │
│   ├── threads/                   # ⭐ CLEAN: Background worker threads
│   │   ├── __init__.py
│   │   ├── session_coordinator.py # Phase 3: Session orchestrator
│   │   ├── data_processor.py      # Phase 4: Derived bars + indicators
│   │   ├── data_quality_manager.py # Phase 5: Quality + gap filling
│   │   ├── analysis_engine.py     # Phase 7: Strategy execution
│   │   └── sync/                  # Thread synchronization
│   │       ├── __init__.py
│   │       └── stream_subscription.py
│   │
│   ├── monitoring/                # Performance and metrics
│   │   ├── __init__.py
│   │   └── performance_metrics.py
│   │
│   ├── strategies/                # Trading strategies
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   └── ...
│   │
│   ├── api/                       # REST API
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI router
│   │   ├── middleware/            # Auth, CORS, etc.
│   │   └── routes/                # API endpoints
│   │       ├── auth.py
│   │       ├── market_data.py
│   │       ├── system.py          # System control
│   │       └── ...
│   │
│   ├── cli/                       # CLI interface
│   │   ├── __init__.py
│   │   ├── interactive.py         # CLI shell
│   │   └── commands/              # Command implementations
│   │       ├── system_commands.py
│   │       ├── data_commands.py
│   │       ├── time_commands.py
│   │       └── ...
│   │
│   └── utils/                     # General utilities
│       ├── __init__.py
│       └── ...
│
├── session_configs/               # Session configuration files
├── validation/                    # CSV validation tools
├── tests/                         # Test suite
└── ...
```

---

## � Code Patterns (Synchronous Thread Pool)

### Thread Pattern (threading.Thread)

```python
# ✅ CORRECT - Synchronous thread
import threading
import time
from app.models.database import SessionLocal

class SessionCoordinator(threading.Thread):
    """Background worker using threading.Thread (NOT async)."""
    
    def __init__(self, system_manager, data_manager, session_config, mode="backtest"):
        super().__init__(name="SessionCoordinator", daemon=True)
        self._system_manager = system_manager
        self._time_manager = system_manager.get_time_manager()
        self._stop_event = threading.Event()
        self._running = False
    
    def run(self):
        """Main thread loop (synchronous)."""
        self._running = True
        while not self._stop_event.is_set():
            # Synchronous work
            self._process_data()
            time.sleep(0.1)  # ✅ Use time.sleep(), NOT asyncio.sleep()
    
    def _process_data(self):
        """Synchronous data processing."""
        # Use TimeManager (synchronous)
        current_time = self._time_manager.get_current_time()
        
        # Use synchronous database access
        with SessionLocal() as session:  # ✅ with, NOT async with
            trading_session = self._time_manager.get_trading_session(session, date)
        
        # Process data...
    
    def stop(self):
        """Stop the thread."""
        self._stop_event.set()
        self._running = False
```

### Manager Pattern (Synchronous Facade)

```python
# ✅ CORRECT - Synchronous manager
from app.models.database import SessionLocal

class TimeManager:
    """Stateful orchestrator with synchronous API."""
    
    def __init__(self):
        self._cache = {}
    
    def get_current_time(self) -> datetime:
        """Get current time (synchronous)."""
        if self._mode == "backtest":
            return self._backtest_time
        else:
            return datetime.now(self._timezone)
    
    def get_trading_session(self, session: Session, date: date) -> TradingSession:
        """Get trading session (synchronous, NOT async)."""
        # Check cache
        if date in self._cache:
            return self._cache[date]
        
        # Query database (synchronous)
        result = session.query(TradingSession).filter_by(date=date).first()
        
        # Cache and return
        self._cache[date] = result
        return result
```

### Service Pattern (Stateless Utility)

```python
# ✅ CORRECT - Stateless service (pure functions)
class GapDetectionService:
    """Stateless utility for gap detection."""
    
    @staticmethod
    def detect_gaps(
        symbol: str,
        session_start: datetime,
        current_time: datetime,
        existing_bars: List[Bar]
    ) -> List[Gap]:
        """Detect gaps in bar data (pure function)."""
        # Pure business logic, no state
        gaps = []
        expected_bars = calculate_expected_bars(session_start, current_time)
        actual_bars = len(existing_bars)
        
        if actual_bars < expected_bars:
            gaps.append(Gap(...))
        
        return gaps
```

### Repository Pattern (Synchronous Database Access)

```python
# ✅ CORRECT - Synchronous repository
from app.models.database import SessionLocal

class BarRepository:
    """Database access layer (synchronous CRUD)."""
    
    def get_bars(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date
    ) -> List[Bar]:
        """Get bars from database (synchronous)."""
        with SessionLocal() as session:  # ✅ Synchronous context manager
            query = session.query(Bar).filter(
                Bar.symbol == symbol,
                Bar.interval == interval,
                Bar.timestamp >= start_date,
                Bar.timestamp <= end_date
            )
            return query.all()  # ✅ No await
    
    def save_bars(self, bars: List[Bar]) -> None:
        """Save bars to database (synchronous)."""
        with SessionLocal() as session:
            session.bulk_save_objects(bars)
            session.commit()  # ✅ No await
```

### Thread Communication (Queues & Events)

```python
# ✅ CORRECT - Thread-safe communication
import queue
import threading

class DataProcessor(threading.Thread):
    """Consumer thread."""
    
    def __init__(self, input_queue: queue.Queue):
        super().__init__(name="DataProcessor", daemon=True)
        self._input_queue = input_queue  # ✅ queue.Queue (thread-safe)
        self._stop_event = threading.Event()
    
    def run(self):
        """Process data from queue."""
        while not self._stop_event.is_set():
            try:
                # Get data from queue (blocks with timeout)
                data = self._input_queue.get(timeout=1.0)  # ✅ No await
                self._process(data)
                self._input_queue.task_done()
            except queue.Empty:
                continue  # Timeout, check stop_event

# Producer (e.g., SessionCoordinator)
class SessionCoordinator(threading.Thread):
    def __init__(self, output_queue: queue.Queue):
        self._output_queue = output_queue
    
    def _send_data(self, data):
        """Send data to consumer."""
        self._output_queue.put(data)  # ✅ Thread-safe, no await
```

### ❌ WRONG Patterns (What NOT to Do)

```python
# ❌ WRONG - Async thread (DON'T DO THIS)
import asyncio

class BadThread(threading.Thread):
    async def run(self):  # ❌ Don't use async def
        await self._process()  # ❌ Don't use await
    
    async def _process(self):  # ❌ Don't use async def
        async with AsyncSessionLocal() as session:  # ❌ Don't use AsyncSessionLocal
            result = await session.execute(query)  # ❌ Don't use await

# ❌ WRONG - Mixing threading and asyncio
class BadManager:
    async def get_data(self):  # ❌ Don't use async def in managers
        await asyncio.sleep(1)  # ❌ Don't use asyncio.sleep()
        return data
```

---

## �🔄 Key Changes

### 1. **New `app/core/` Directory**
**Purpose:** Fundamental data structures used everywhere

**Contents:**
- `session_data.py` - Moved from `app/data/`
- `data_structures/` - Bar, Quote, Tick classes
- `enums.py` - SystemState, OperationMode
- `exceptions.py` - Custom exceptions

**Rationale:** These are core primitives, not "data management"

### 2. **Cleaned `app/threads/`**
**Before:**
```
threads/
├── session_coordinator.py
├── data_processor.py
├── data_quality_manager.py
├── analysis_engine.py          # Thread implementation
└── sync/
```

**After:** ✅ Already clean! Just remove any non-thread files.

### 3. **Cleaned `app/managers/`**
**Before:**
```
managers/
├── system_manager.py            # File (inconsistent)
├── time_manager/                # Package
├── data_manager/                # Package with 15+ files
├── execution_manager/           # Package
└── analysis_engine/             # Duplicate? Should be thread only
```

**After:**
```
managers/
├── system_manager.py            # ✅ Keep as file (singleton)
├── time_manager/
│   ├── api.py                   # TimeManager class
│   ├── models.py
│   └── repositories/
├── data_manager/
│   ├── api.py                   # DataManager class
│   ├── stream_manager.py        # Stream lifecycle helper
│   └── repositories/
└── execution_manager/
    ├── api.py                   # ExecutionManager class
    └── repositories/
```

**What Moves Out:**
- `data_manager/backtest_stream_coordinator.py` → DELETE (replaced by `threads/session_coordinator.py`)
- `data_manager/data_upkeep_thread.py` → DELETE (replaced by threads)
- `data_manager/gap_detection.py` → `services/market_data/gap_detection.py`
- `data_manager/derived_bars.py` → `services/market_data/bar_aggregation.py`
- `data_manager/quality_checker.py` → `services/market_data/quality_scoring.py`
- `data_manager/parquet_storage.py` → `services/market_data/parquet_storage.py`
- `data_manager/session_data.py` → `core/session_data.py`

### 4. **Cleaned `app/services/`**
**Before:** Random collection
```
services/
├── auth_service.py
├── claude_probability.py
├── claude_usage_tracker.py
├── csv_import_service.py
├── hybrid_probability_engine.py
├── technical_indicators.py
└── traditional_probability.py
```

**After:** Organized by domain
```
services/
├── market_data/              # Market data utilities
│   ├── gap_detection.py
│   ├── bar_aggregation.py
│   ├── quality_scoring.py
│   └── parquet_storage.py
├── indicators/               # Technical indicators
│   ├── moving_averages.py
│   └── ...
├── analysis/                 # Analysis utilities
│   └── probability_engine.py
├── auth/
│   └── auth_service.py
└── csv_import/
    └── csv_import_service.py
```

### 5. **Cleaned `app/integrations/`**
**Before:** Flat files
```
integrations/
├── alpaca_client.py
├── schwab_client.py
└── claude_client.py
```

**After:** Organized by provider
```
integrations/
├── alpaca/
│   ├── __init__.py
│   └── client.py
├── schwab/
│   ├── __init__.py
│   └── client.py
└── claude/
    ├── __init__.py
    ├── client.py
    └── usage_tracker.py
```

---

## 📋 Layer Communication Rules

### Architecture Layers (Top to Bottom)

```
┌─────────────────────────────────────────────────┐
│  API / CLI (Entry Points)                       │
├─────────────────────────────────────────────────┤
│  Managers (Orchestrators)                       │
│  • system_manager                               │
│  • time_manager                                 │
│  • data_manager                                 │
│  • execution_manager                            │
├─────────────────────────────────────────────────┤
│  Threads (Background Workers)                   │
│  • session_coordinator                          │
│  • data_processor                               │
│  • data_quality_manager                         │
│  • analysis_engine                              │
├─────────────────────────────────────────────────┤
│  Services (Business Logic)                      │
│  • Stateless utilities                          │
│  • Pure functions                               │
├─────────────────────────────────────────────────┤
│  Integrations (External APIs)                   │
│  • alpaca, schwab, claude                       │
├─────────────────────────────────────────────────┤
│  Repositories (Data Access)                     │
│  • Database CRUD                                │
├─────────────────────────────────────────────────┤
│  Core (Primitives)                              │
│  • SessionData, Bar, Quote                      │
│  • Enums, Exceptions                            │
└─────────────────────────────────────────────────┘
```

### Communication Rules

1. ✅ **Downward dependencies only** (upper layers depend on lower)
2. ❌ **No upward dependencies** (repositories can't call managers)
3. ✅ **Threads communicate via queues/subscriptions** (not direct calls)
4. ✅ **Services are pure/stateless** (can be called from anywhere)
5. ✅ **Managers provide facades** (hide complexity)

---

## 🔄 Migration Plan

### Phase 1: Create New Structure (No Breaking Changes)
1. Create `app/core/` directory
2. Create organized `app/services/` subdirectories
3. Create organized `app/integrations/` subdirectories
4. Copy files to new locations (keep old ones for now)

### Phase 2: Update Imports
1. Update imports to use new paths
2. Test that system still works
3. Fix any broken imports

### Phase 3: Remove Old Files
1. Delete old locations
2. Remove backup files
3. Clean up `_backup` directories

### Phase 4: Update Documentation
1. Update README files
2. Update SESSION_ARCHITECTURE.md references
3. Update PROGRESS.md

---

## 🎯 Key Benefits

1. **Clear terminology** - Everyone knows what a "manager" vs "service" vs "thread" is
2. **Logical organization** - Related files grouped together
3. **Easy navigation** - Know where to find/add features
4. **Layer isolation** - Clear boundaries between components
5. **Testability** - Easy to test services independently
6. **Scalability** - Easy to add new features in right place

---

## 📝 Naming Conventions

### Files
- `*_manager.py` - Stateful orchestrator (e.g., `time_manager.py`)
- `*_service.py` - Stateless utility (e.g., `gap_detection_service.py`)
- `*_repository.py` - Database access (e.g., `bar_repository.py`)
- `*_client.py` - External API (e.g., `alpaca_client.py`)
- `*_thread.py` - Background worker (optional suffix)

### Classes
- `*Manager` - Orchestrator (e.g., `TimeManager`)
- `*Service` - Utility (e.g., `GapDetectionService`)
- `*Repository` - Data access (e.g., `BarRepository`)
- `*Client` - External API (e.g., `AlpacaClient`)
- `*Coordinator`, `*Processor`, `*Engine` - Threads (e.g., `SessionCoordinator`)

### Directories
- Lowercase with underscores: `market_data/`, `time_manager/`
- Grouped by domain/feature: `services/market_data/`, `integrations/alpaca/`

---

## ❓ Decision Points for You

1. **Should we do this refactor now or after getting system working?**
   - Option A: Do it now (clean slate before pushing forward)
   - Option B: Get system working first, refactor later

2. **Should we keep `analysis_engine` in both places?**
   - Currently: `threads/analysis_engine.py` (thread) AND `managers/analysis_engine/` (package)
   - Proposal: Keep only `threads/analysis_engine.py`, delete manager package

3. **Should `session_data.py` be in `core/` or stay in `data/`?**
   - Proposal: Move to `core/` (it's a fundamental primitive)

4. **Should we rename files now or keep backward compatibility?**
   - Example: `alpaca_client.py` → `integrations/alpaca/client.py`
   - Can keep old files as thin wrappers temporarily

**Your call! What approach do you prefer?** 🤔
