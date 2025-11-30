# MisMartera System Architecture

**Version:** 2.0  
**Last Updated:** 2025-11-29  
**Status:** Complete Architectural Reference

---

## 📋 Table of Contents

1. [Overview & Quick Start](#overview--quick-start)
2. [Architecture Principles](#architecture-principles)
3. [Directory Organization](#directory-organization)
4. [Component Decision Guide](#component-decision-guide)
5. [Synchronous Thread Pool Model](#synchronous-thread-pool-model)
6. [Layer Communication Rules](#layer-communication-rules)
7. [Core Components](#core-components)
8. [Session Architecture](#session-architecture)
9. [Code Patterns & Examples](#code-patterns--examples)
10. [CLI & API](#cli--api)
11. [Testing Strategy](#testing-strategy)

---

## Overview & Quick Start

### What is MisMartera?

MisMartera is a day trading application built on a **synchronous thread pool architecture** with clear separation of concerns. The system emphasizes:

- ✅ **Simplicity**: No async/await complexity (except FastAPI routes)
- ✅ **Clarity**: Each component has a single, well-defined purpose
- ✅ **Testability**: Pure services, stateful managers, isolated threads
- ✅ **Performance**: Thread pool for parallel processing, zero-copy data flow

### 5-Minute Quick Start

```python
from app.managers.system_manager import get_system_manager
from app.models.database import SessionLocal

# 1. Get system manager (singleton)
system_mgr = get_system_manager()

# 2. Start system with session config
system_mgr.start("session_configs/example_session.json")

# 3. Access managers
time_mgr = system_mgr.get_time_manager()
data_mgr = system_mgr.get_data_manager()

# 4. Use managers
current_time = time_mgr.get_current_time()
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, current_time.date())
    print(f"Market: {session.regular_open} - {session.regular_close}")
```

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                                  │
│                                                                  │
│  ┌─────────────────┐              ┌─────────────────────────┐   │
│  │  CLI Interface  │              │   FastAPI REST API      │   │
│  │  (Interactive)  │              │   (HTTP/JSON)           │   │
│  └────────┬────────┘              └───────────┬─────────────┘   │
└───────────┼─────────────────────────────────────┼──────────────┘
            │                                     │
            │   All access via SystemManager     │
            └──────────────┬──────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SYSTEM MANAGER                                 │
│          (Orchestrator & Service Locator)                        │
│                                                                  │
│  • Creates and manages all components                           │
│  • Provides access to managers (singleton)                      │
│  • Controls system state (STOPPED → RUNNING → STOPPED)          │
│  • Wires 4-thread pool together                                 │
└─────────┬───────────────────────────────────┬───────────────────┘
          │ Creates                           │ Creates & Manages
          ▼                                   ▼
┌──────────────────────────┐     ┌────────────────────────────────┐
│    MANAGERS              │     │    4-THREAD POOL                │
│  (Passive Facades)       │     │  (Active Background Workers)    │
│                          │     │                                 │
│  • TimeManager           │     │  1. SessionCoordinator          │
│  • DataManager           │     │     (Orchestrates lifecycle)    │
│  • ExecutionManager      │     │                                 │
│                          │     │  2. DataProcessor               │
│  Provide APIs for:       │     │     (Derived bars + indicators) │
│  - Time operations       │     │                                 │
│  - Data access           │     │  3. DataQualityManager          │
│  - Order management      │     │     (Quality + gap filling)     │
└────────┬─────────────────┘     │                                 │
         │ Uses                  │  4. AnalysisEngine              │
         ▼                       │     (Strategy execution)        │
┌──────────────────────────┐     └────────────┬───────────────────┘
│    SERVICES              │                  │ Communicate via
│  (Stateless Utilities)   │                  │ Queues & Events
│                          │                  ▼
│  • GapDetectionService   │     ┌────────────────────────────────┐
│  • BarAggregationService │     │  CORE PRIMITIVES                │
│  • QualityScoringService │     │                                 │
│  • IndicatorServices     │     │  • SessionData (unified store)  │
└────────┬─────────────────┘     │  • Bar, Quote, Tick             │
         │ Uses                  │  • SystemState, OperationMode   │
         ▼                       └─────────────────────────────────┘
┌──────────────────────────┐
│    REPOSITORIES          │
│  (Database Access)       │
│                          │
│  • BarRepository         │
│  • CalendarRepository    │
│  • OrderRepository       │
└────────┬─────────────────┘
         │ Queries
         ▼
┌──────────────────────────┐
│    DATABASES             │
│  • MarketData (bars)     │
│  • TradingCalendar       │
│  • Orders & Positions    │
│  • Analysis Logs         │
└──────────────────────────┘
```

---

## Architecture Principles

### 1. **Synchronous Thread Pool (NO ASYNCIO)**

**Critical Decision:** We use `threading.Thread`, NOT `asyncio`.

- ✅ **Use `threading.Thread`** for all background workers
- ✅ **Use `SessionLocal`** (synchronous) for database access
- ✅ **Use `time.sleep()`** for delays
- ✅ **Use `with` context managers**
- ❌ **NO `async def` / `await`** anywhere (except FastAPI routes)
- ❌ **NO `AsyncSessionLocal`**
- ❌ **NO `asyncio.Queue` or coroutines**

**Why?**
- Simpler mental model (no async/await complexity)
- Better for I/O-bound workloads with blocking operations
- Easier debugging (standard threading tools)
- Avoids mixing threading and asyncio (causes runtime errors)

**Exception:** FastAPI REST API handlers in `app/api/routes/` may use async (FastAPI requirement only).

### 2. **Single Source of Truth**

- **Time Operations**: ALL via `TimeManager` (NEVER `datetime.now()`)
- **Trading Hours**: Query from `TimeManager.get_trading_session()` (NEVER hardcode 9:30/16:00)
- **Holidays**: Managed by `TimeManager` (NEVER manual checks)
- **System State**: Owned by `SystemManager` (NEVER duplicate state)
- **Operation Mode**: Owned by `SystemManager` (NEVER distributed mode checks)

### 3. **Zero-Copy Data Flow**

Bar/tick/quote objects exist **once** in memory:

```
┌──────────────┐    reference    ┌──────────────┐    reference    ┌──────────────┐
│ Coordinator  │  ──────────────>│ SessionData  │<──────────────  │   Analysis   │
│    Queue     │                 │   (store)    │                 │    Engine    │
└──────────────┘                 └──────────────┘                 └──────────────┘
        │                                                                  │
        └──────────────────────> Same Bar object <───────────────────────┘
                                 (no copies made)
```

### 4. **Configuration Philosophy**

- **No Settings Defaults**: Session config fields MUST NOT have defaults in `settings.py`
- **Source Code Defaults**: All defaults defined at point of use
- **Safe Defaults**: Either invalid (force explicit config) or safe fallback values
- **Explicit Over Implicit**: Critical configurations require explicit values

### 5. **Timezone Handling (CRITICAL)**

**Principle:** Work in market timezone everywhere, convert only at boundaries.

#### Storage (Internal)

- **TimeManager**: Stores all times in UTC internally
- **Database**: All timestamps stored in UTC
- **DataManager**: Queries/stores in UTC

#### Return Values (External)

- **TimeManager**: Returns times in `system_manager.timezone` (market timezone)
- **DataManager**: Returns times in `system_manager.timezone` (market timezone)
- **Never specify timezone explicitly** - Always use system default for consistency

#### Timezone Derivation

```python
# system_manager.timezone is derived from exchange_group + asset_class
exchange_group = "US_EQUITY"   # From session config
asset_class = "EQUITY"          # From session config
timezone = "America/New_York"   # Derived from MarketHours database
```

**Query:**
```sql
SELECT timezone FROM market_hours 
WHERE exchange_group = 'US_EQUITY' AND asset_class = 'EQUITY'
```

#### Boundary Conversion

**ONLY TimeManager and DataManager perform timezone conversions.**

```
┌─────────────────────────────────────────────────────────────┐
│  APPLICATION CODE (Works in Market Timezone)                │
│  • Never specify timezone                                   │
│  • Always use defaults                                      │
│  • current_time = time_mgr.get_current_time()              │
│  • bar.timestamp is already in market timezone              │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │ BOUNDARY      │ BOUNDARY      │
        ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ TimeManager  │  │ DataManager  │  │  Database    │
│              │  │              │  │              │
│ Converts:    │  │ Converts:    │  │ Stores:      │
│ UTC → Market │  │ UTC → Market │  │ UTC only     │
│ Market → UTC │  │ Market → UTC │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

#### Time Objects with Timezone

TimeManager stores `time` objects (e.g., market open/close) with timezone metadata:

```python
# MarketHours table stores:
regular_open = time(9, 30)      # Not timezone-aware
timezone = "America/New_York"    # Separate field

# When returning, TimeManager combines:
trading_session.regular_open = time(9, 30)
trading_session.timezone = "America/New_York"

# Application code uses:
open_time = session.regular_open  # time(9, 30)
# Knows it's in market timezone (system_manager.timezone)
```

#### Rules

1. ✅ **DO**: Use `time_mgr.get_current_time()` (returns market timezone)
2. ✅ **DO**: Use `bar.timestamp` as-is (already market timezone)
3. ✅ **DO**: Use `session.regular_open` as-is (already market timezone)
4. ❌ **DON'T**: Call `.astimezone()` outside TimeManager/DataManager
5. ❌ **DON'T**: Specify timezone explicitly (breaks consistency)
6. ❌ **DON'T**: Convert timezones in application code

#### Example: Correct Usage

```python
# ✅ CORRECT - Work in market timezone
time_mgr = system_mgr.get_time_manager()

# Get current time (in market timezone)
current_time = time_mgr.get_current_time()  # Already in market TZ

# Get trading session
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, current_time.date())
    
    # Times are in market timezone
    open_time = session.regular_open   # time(9, 30) in market TZ
    close_time = session.regular_close  # time(16, 0) in market TZ
    
    # Combine with date (market timezone implied)
    market_open_dt = datetime.combine(
        current_time.date(),
        open_time
    )  # Still in market timezone

# Get bars (timestamps already in market timezone)
bars = data_mgr.get_bars(symbol, interval, start_date, end_date)
for bar in bars:
    # bar.timestamp is already in market timezone
    print(f"Bar at {bar.timestamp}")  # No conversion needed!
```

#### Example: Wrong Usage

```python
# ❌ WRONG - Don't convert timezones manually
current_time = time_mgr.get_current_time()
utc_time = current_time.astimezone(pytz.UTC)  # ❌ Don't do this!

# ❌ WRONG - Don't specify timezone explicitly
current_time = time_mgr.get_current_time("UTC")  # ❌ Breaks consistency!

# ❌ WRONG - Don't do timezone arithmetic
eastern = pytz.timezone("America/New_York")  # ❌ Don't do this!
local_time = eastern.localize(datetime.now())  # ❌ Use TimeManager!
```

#### Why This Matters

1. **Consistency**: All code sees times in same timezone (market)
2. **Simplicity**: No timezone conversions in application code
3. **Correctness**: TimeManager/DataManager Boundary conversion prevents timezone bugs
4. **Clarity**: Always work in market timezone (where trading happens)
5. **UTC Day Boundaries**: Extended hours can cross UTC midnight - handled at boundaries

### 6. **Layer Isolation**

```
API/CLI → Managers → Threads/Services → Repositories → Database
  ↑         ↑           ↑                 ↑
  │         │           │                 │
  └─────────┴───────────┴─────────────────┘
         Downward dependencies only
         (no upward dependencies)
```

---

## Directory Organization

### Complete Structure

```
backend/
├── app/
│   ├── core/                      # ⭐ Fundamental primitives
│   │   ├── __init__.py
│   │   ├── session_data.py        # Unified data store (singleton)
│   │   ├── enums.py               # SystemState, OperationMode
│   │   ├── exceptions.py          # Custom exceptions
│   │   └── data_structures/       # Bar, Quote, Tick classes
│   │
│   ├── models/                    # Database models (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── database.py            # SessionLocal, engine
│   │   ├── session_config.py      # SessionConfig (Pydantic)
│   │   ├── trading_calendar.py    # TradingSession, MarketHours
│   │   ├── account.py
│   │   ├── orders.py
│   │   └── user.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py            # Global settings (NOT session config)
│   │
│   ├── repositories/              # Database access layer (CRUD)
│   │   ├── __init__.py
│   │   ├── bar_repository.py
│   │   ├── calendar_repository.py
│   │   ├── order_repository.py
│   │   └── user_repository.py
│   │
│   ├── services/                  # Stateless business logic
│   │   ├── __init__.py
│   │   ├── market_data/
│   │   │   ├── gap_detection.py
│   │   │   ├── bar_aggregation.py
│   │   │   ├── quality_scoring.py
│   │   │   └── parquet_storage.py
│   │   ├── indicators/
│   │   │   ├── moving_averages.py
│   │   │   ├── rsi.py
│   │   │   └── ...
│   │   ├── analysis/
│   │   │   └── probability_engine.py
│   │   └── auth/
│   │       └── auth_service.py
│   │
│   ├── integrations/              # External API clients
│   │   ├── __init__.py
│   │   ├── alpaca/
│   │   │   ├── __init__.py
│   │   │   └── client.py
│   │   ├── schwab/
│   │   │   ├── __init__.py
│   │   │   └── client.py
│   │   └── claude/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       └── usage_tracker.py
│   │
│   ├── managers/                  # Stateful orchestrators (facades)
│   │   ├── __init__.py
│   │   ├── system_manager/
│   │   │   ├── __init__.py
│   │   │   └── api.py             # SystemManager class
│   │   ├── time_manager/
│   │   │   ├── __init__.py
│   │   │   ├── api.py             # TimeManager class
│   │   │   ├── models.py
│   │   │   └── repositories/
│   │   ├── data_manager/
│   │   │   ├── __init__.py
│   │   │   ├── api.py             # DataManager class
│   │   │   ├── stream_manager.py
│   │   │   └── repositories/
│   │   └── execution_manager/
│   │       ├── __init__.py
│   │       ├── api.py             # ExecutionManager class
│   │       └── repositories/
│   │
│   ├── threads/                   # Background worker threads
│   │   ├── __init__.py
│   │   ├── session_coordinator.py # Phase 3: Session orchestrator
│   │   ├── data_processor.py      # Phase 4: Derived bars + indicators
│   │   ├── data_quality_manager.py # Phase 5: Quality + gap filling
│   │   ├── analysis_engine.py     # Phase 7: Strategy execution
│   │   └── sync/                  # Thread synchronization
│   │       ├── __init__.py
│   │       └── stream_subscription.py
│   │
│   ├── monitoring/
│   │   ├── __init__.py
│   │   └── performance_metrics.py
│   │
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   └── ...
│   │
│   ├── api/                       # REST API
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── middleware/
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── market_data.py
│   │       ├── system.py
│   │       └── ...
│   │
│   ├── cli/                       # CLI interface
│   │   ├── __init__.py
│   │   ├── interactive.py
│   │   └── commands/
│   │       ├── system_commands.py
│   │       ├── data_commands.py
│   │       ├── time_commands.py
│   │       └── ...
│   │
│   └── utils/
│       ├── __init__.py
│       └── ...
│
├── session_configs/               # Session configuration files
├── validation/                    # CSV validation tools
├── tests/                         # Test suite
└── docs/                          # Additional documentation
```

---

## Component Decision Guide

### Decision Tables

#### Q1: Should my code be a Thread or Manager?

| Question | Thread | Manager |
|----------|--------|---------|
| Does it run continuously in background? | ✅ Yes | ❌ No |
| Does it have a `run()` method with event loop? | ✅ Yes | ❌ No |
| Does it consume from queues? | ✅ Yes | ❌ No |
| Is it **active** (pulls data)? | ✅ Yes | ❌ No |
| Is it **passive** (responds to API calls)? | ❌ No | ✅ Yes |
| Does it provide a facade over subsystem? | ❌ No | ✅ Yes |

**Examples:**
- ✅ **Thread**: `SessionCoordinator`, `DataProcessor`, `AnalysisEngine`
- ✅ **Manager**: `TimeManager`, `DataManager`, `SystemManager`

#### Q2: Should my code be a Service or Manager?

| Characteristic | Service | Manager |
|----------------|---------|---------|
| Has state (caches, connections, config)? | ❌ No | ✅ Yes |
| Is it stateless (pure functions)? | ✅ Yes | ❌ No |
| Is it a singleton? | ❌ No | ✅ Yes |
| Does it depend on many other components? | ❌ No | ✅ Yes |
| Is it utility/helper logic? | ✅ Yes | ❌ No |

**Examples:**
- ✅ **Service**: `GapDetectionService`, `BarAggregationService`
- ✅ **Manager**: `TimeManager`, `DataManager`

#### Q3: Where does my new code go?

| I'm building... | Location | Why |
|----------------|----------|-----|
| Background worker that processes data continuously | `app/threads/` | Active worker with `run()` loop |
| High-level API facade over subsystem | `app/managers/` | Stateful orchestrator |
| Pure utility function | `app/services/` | Stateless business logic |
| Database CRUD operations | `app/repositories/` | Data access layer |
| External API client | `app/integrations/` | Third-party integration |
| SQLAlchemy model | `app/models/` | Database schema |
| Pydantic validation model | `app/models/` | Config/request validation |
| Fundamental data structure | `app/core/` | Primitive used everywhere |
| REST API endpoint | `app/api/routes/` | HTTP handler |
| CLI command | `app/cli/commands/` | Interactive command |

#### Q4: Naming Conventions

| Component Type | File Naming | Class Naming | Example |
|----------------|-------------|--------------|---------|
| Thread | `*_coordinator.py`, `*_processor.py`, `*_engine.py` | `*Coordinator`, `*Processor`, `*Engine` | `session_coordinator.py` → `SessionCoordinator` |
| Manager | `*/api.py` (in manager package) | `*Manager` | `time_manager/api.py` → `TimeManager` |
| Service | `*_service.py` or domain name | `*Service` or domain class | `gap_detection.py` → `GapDetectionService` |
| Repository | `*_repository.py` | `*Repository` | `bar_repository.py` → `BarRepository` |
| Integration | `client.py` (in provider package) | `*Client` | `alpaca/client.py` → `AlpacaClient` |

---

## Synchronous Thread Pool Model

### Thread Communication

#### 1. Queues (Producer → Consumer)

```python
import queue
import threading

# Producer thread
class SessionCoordinator(threading.Thread):
    def __init__(self, output_queue: queue.Queue):
        super().__init__(name="SessionCoordinator", daemon=True)
        self._output_queue = output_queue
    
    def run(self):
        while not self._stop_event.is_set():
            bar = self._get_next_bar()
            self._output_queue.put(bar)  # ✅ Thread-safe

# Consumer thread
class DataProcessor(threading.Thread):
    def __init__(self, input_queue: queue.Queue):
        super().__init__(name="DataProcessor", daemon=True)
        self._input_queue = input_queue
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                bar = self._input_queue.get(timeout=1.0)  # ✅ Blocks with timeout
                self._process(bar)
                self._input_queue.task_done()
            except queue.Empty:
                continue
```

#### 2. Events (Signals)

```python
import threading

class DataProcessor(threading.Thread):
    def __init__(self):
        super().__init__(name="DataProcessor", daemon=True)
        self._stop_event = threading.Event()
    
    def run(self):
        while not self._stop_event.is_set():  # ✅ Check signal
            self._process_data()
    
    def stop(self):
        self._stop_event.set()  # ✅ Signal to stop
```

#### 3. StreamSubscription (Custom Notifications)

```python
from app.threads.sync.stream_subscription import StreamSubscription

# Create subscription
subscription = StreamSubscription("processor")

# Producer notifies
subscription.notify({"type": "bar", "data": bar})

# Consumer waits
message = subscription.wait_for_notification(timeout=1.0)
```

### Database Access Pattern

**Always synchronous with `SessionLocal`:**

```python
from app.models.database import SessionLocal

# ✅ CORRECT - Synchronous
with SessionLocal() as session:
    trading_session = time_mgr.get_trading_session(session, date)
    bars = session.query(Bar).filter(...).all()
    session.commit()

# ❌ WRONG - Async (DON'T DO THIS)
async with AsyncSessionLocal() as session:  # ❌
    result = await session.execute(query)   # ❌
```

### Thread Lifecycle

```python
# 1. Create thread
coordinator = SessionCoordinator(
    system_manager=system_mgr,
    data_manager=data_mgr,
    session_config=config,
    mode="backtest"
)

# 2. Start thread (begins run() loop)
coordinator.start()

# 3. Thread runs continuously...
# (processes data, manages session, etc.)

# 4. Stop thread
coordinator.stop()  # Sets stop event
coordinator.join(timeout=5.0)  # Wait for clean shutdown
```

---

## Layer Communication Rules

### Dependency Flow

```
┌────────────────────────────────────────────────┐
│  Layer 1: Entry Points (API / CLI)             │  ← User interaction
└───────────────────┬────────────────────────────┘
                    │ calls
                    ▼
┌────────────────────────────────────────────────┐
│  Layer 2: System Manager                       │  ← Orchestration
└───────────────────┬────────────────────────────┘
                    │ creates & provides access
         ┌──────────┼──────────┐
         ▼          ▼          ▼
┌────────────┐ ┌──────────┐ ┌──────────────┐
│  Managers  │ │  Threads │ │ Monitoring   │  ← Components
└─────┬──────┘ └────┬─────┘ └──────┬───────┘
      │ uses        │ uses         │ uses
      ▼             ▼              ▼
┌────────────────────────────────────────────────┐
│  Layer 3: Services (Business Logic)            │  ← Stateless utilities
└───────────────────┬────────────────────────────┘
                    │ uses
                    ▼
┌────────────────────────────────────────────────┐
│  Layer 4: Integrations (External APIs)         │  ← Third-party
└───────────────────┬────────────────────────────┘
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
┌────────────┐ ┌──────────┐ ┌──────────┐
│Repositories│ │ Databases│ │ External │  ← Data sources
└────────────┘ └──────────┘ └─ APIs────┘
         │          │          │
         └──────────┼──────────┘
                    ▼
┌────────────────────────────────────────────────┐
│  Layer 5: Core (Primitives)                    │  ← Fundamental types
│  SessionData, Bar, Quote, Enums                │
└────────────────────────────────────────────────┘
```

### Rules

1. ✅ **Downward dependencies only** - Upper layers depend on lower layers
2. ❌ **No upward dependencies** - Repositories can't call managers
3. ✅ **Threads communicate via queues/events** - No direct method calls between threads
4. ✅ **Services are pure/stateless** - Can be called from any layer
5. ✅ **Managers provide facades** - Hide complexity from upper layers
6. ✅ **Core is universal** - Can be imported anywhere

### Communication Patterns

| From → To | Allowed? | Pattern |
|-----------|----------|---------|
| API/CLI → SystemManager | ✅ Yes | Direct method call |
| SystemManager → Managers | ✅ Yes | Create & store reference |
| Manager → Service | ✅ Yes | Direct function call |
| Manager → Repository | ✅ Yes | Direct method call |
| Thread → Manager | ✅ Yes | Store reference in `__init__` |
| Thread → Thread | ✅ Yes | Via queue/event/subscription |
| Service → Repository | ✅ Yes | Pass as parameter |
| Repository → Manager | ❌ No | Upward dependency |
| Thread → Thread (direct) | ❌ No | Use queue/event |
| Any → Core | ✅ Yes | Import and use |

---

## Core Components

### SystemManager

**Role:** Orchestrator and service locator

**Responsibilities:**
1. Create and initialize all managers (TimeManager, DataManager, etc.)
2. Load and validate session configuration
3. Create and wire 4-thread pool
4. Provide singleton access to managers
5. Track system state (STOPPED, RUNNING)
6. Handle `start()` and `stop()` lifecycle

**Location:** `app/managers/system_manager/api.py`

**Usage:**
```python
from app.managers.system_manager import get_system_manager

# Get singleton
system_mgr = get_system_manager()

# Start system
system_mgr.start("session_configs/example_session.json")

# Access managers
time_mgr = system_mgr.get_time_manager()
data_mgr = system_mgr.get_data_manager()

# Stop system
system_mgr.stop()
```

**Key Attributes:**
- `_state: SystemState` - STOPPED, RUNNING
- `_session_config: SessionConfig` - Active configuration
- `_time_manager: TimeManager` - Time/calendar singleton
- `_data_manager: DataManager` - Market data singleton
- `_coordinator: SessionCoordinator` - Main orchestrator thread
- `_data_processor: DataProcessor` - Derived data thread
- `_quality_manager: DataQualityManager` - Quality monitoring thread
- `_analysis_engine: AnalysisEngine` - Strategy execution thread

**Architecture:**
```
SystemManager (Singleton)
    │
    ├─ Manages TimeManager (singleton)
    ├─ Manages DataManager (singleton)
    ├─ Manages ExecutionManager (singleton)
    │
    └─ Creates & Controls 4-Thread Pool:
        ├─ SessionCoordinator
        ├─ DataProcessor
        ├─ DataQualityManager
        └─ AnalysisEngine
```

---

### TimeManager

**Role:** Single source of truth for ALL time and calendar operations

**Responsibilities:**
1. Provide current time (live or backtest mode)
2. Query trading sessions (hours, holidays, early closes)
3. Navigate calendar (next/previous trading dates)
4. Manage backtest time control
5. Handle timezone conversions

**Location:** `app/managers/time_manager/api.py`

**Core Principle:** **Always Query, Never Store**

```python
# ❌ WRONG - Storing time
self.current_time = datetime.now()
self.market_open = time(9, 30)

# ✅ CORRECT - Querying TimeManager
current_time = time_mgr.get_current_time()
session = time_mgr.get_trading_session(db, date)
```

**Key APIs:**

```python
# Time Operations
current_time = time_mgr.get_current_time()  # Returns datetime
current_time = time_mgr.get_current_time("UTC")  # Specific timezone

# Trading Sessions
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, date)
    # session.regular_open, session.regular_close
    # session.is_trading_day, session.is_holiday
    
    is_open = time_mgr.is_market_open(db, timestamp)
    session_type = time_mgr.get_market_session(db, timestamp)
    # Returns: "pre_market", "regular", "post_market", or "closed"

# Calendar Navigation
next_date = time_mgr.get_next_trading_date(db, from_date)
prev_date = time_mgr.get_previous_trading_date(db, from_date)
num_days = time_mgr.count_trading_days(db, start_date, end_date)

# Holidays
is_holiday, name = time_mgr.is_holiday(db, date)
is_early, close_time = time_mgr.is_early_close(db, date)

# Backtest Control
time_mgr.set_backtest_time(datetime(2025, 7, 2, 9, 30))
time_mgr.init_backtest(db)  # Initialize window from config
time_mgr.advance_to_market_open(db)  # Advance to next day
```

**Architecture:**
```
TimeManager (Singleton)
    │
    ├─ Manages Backtest Time (_backtest_time)
    ├─ Manages Mode (_mode: "live" or "backtest")
    ├─ Manages Timezone (_timezone)
    ├─ Manages Cache (_cache: trading sessions)
    │
    └─ Uses:
        ├─ CalendarRepository (trading calendar queries)
        └─ MarketHours Database (hours by exchange/asset class)
```

---

### DataManager

**Role:** Facade for market data operations

**Responsibilities:**
1. Manage data streams (start/stop)
2. Query historical bars from database
3. Import data from external sources
4. Manage parquet storage

**Location:** `app/managers/data_manager/api.py`

**Key APIs:**

```python
# Stream Management
stream_id = data_mgr.start_bar_stream(symbol, interval)
data_mgr.stop_stream(stream_id)
data_mgr.stop_all_streams()

# Historical Data
bars = data_mgr.get_bars(symbol, interval, start_date, end_date)
ticks = data_mgr.get_ticks(symbol, date)
quotes = data_mgr.get_quotes(symbol, date)

# Import Data
data_mgr.import_from_csv(file_path)
data_mgr.import_from_api(source, symbols, date_range)

# Current Time (delegates to TimeManager)
current_time = data_mgr.get_current_time()
```

**Architecture:**
```
DataManager (Singleton)
    │
    ├─ Manages Active Streams (_streams)
    ├─ References SessionData (unified store)
    │
    └─ Uses:
        ├─ BarRepository (database queries)
        ├─ StreamManager (stream lifecycle)
        ├─ ParquetStorage (efficient storage)
        └─ External API Integrations (Alpaca, Schwab, etc.)
```

---

### 4-Thread Pool

The system uses 4 specialized background worker threads:

```
┌────────────────────────────────────────────────────────────────┐
│                   4-THREAD POOL                                 │
│                                                                 │
│  1. SessionCoordinator (Orchestrator)                          │
│     • Manages session lifecycle                                │
│     • Loads historical data before EVERY session              │
│     • Loads stream queues (backtest: prefetch, live: API)     │
│     • Marks STREAMED vs GENERATED data                        │
│     • Advances time in backtest mode                          │
│     • Signals session active/ended                            │
│                                                                 │
│  2. DataProcessor (Derived Bars + Indicators)                 │
│     • Generates derived intervals (1m → 5m, 15m, etc.)        │
│     • Calculates real-time indicators                         │
│     • Event-driven (notified by coordinator)                  │
│     • Writes to SessionData                                    │
│                                                                 │
│  3. DataQualityManager (Quality + Gap Filling)                │
│     • Measures bar quality (% completeness)                   │
│     • Publishes quality metrics                               │
│     • Fills gaps in LIVE MODE ONLY                           │
│     • Propagates quality to derived bars                      │
│     • Non-blocking background operation                       │
│                                                                 │
│  4. AnalysisEngine (Strategy Execution)                       │
│     • Consumes processed data                                 │
│     • Runs trading strategies                                 │
│     • Generates trading signals                               │
│     • Manages positions                                       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

#### Thread Communication

```
SessionCoordinator
    │
    ├── (Queue) ──> DataProcessor ──> (Queue) ──> AnalysisEngine
    │                      │
    └── (Subscription) ────┘
    │
    └── (Subscription) ──> DataQualityManager
```

**Data Flow:**

1. **SessionCoordinator** loads/streams bars → puts in queue
2. **DataProcessor** gets bars from queue → generates derived bars → notifies AnalysisEngine
3. **DataQualityManager** subscribes to coordinator → measures quality asynchronously
4. **AnalysisEngine** gets notifications → runs strategies → generates signals

**Thread Startup Sequence:**

```python
# In SystemManager.start()

# 1. Create SessionData (unified store)
session_data = SessionData()

# 2. Create SessionCoordinator
coordinator = SessionCoordinator(
    system_manager=self,
    data_manager=data_mgr,
    session_config=self._session_config,
    mode=self._session_config.mode
)

# 3. Create DataProcessor
processor = DataProcessor(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config
)

# 4. Create DataQualityManager
quality_mgr = DataQualityManager(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config,
    data_manager=data_mgr
)

# 5. Create AnalysisEngine
analysis = AnalysisEngine(
    session_data=session_data,
    system_manager=self,
    session_config=self._session_config
)

# 6. Wire threads together
coordinator.set_data_processor(processor, processor_subscription)
coordinator.set_quality_manager(quality_mgr)
processor.set_analysis_engine_queue(analysis_queue)

# 7. Start coordinator (orchestrates everything)
coordinator.start()
```

---

## Session Architecture

### Overview

A **session** represents a single trading day (or period in live mode). The session architecture handles:

1. **Historical Data Management** - Load trailing data before EVERY session
2. **Historical Indicators** - Calculate indicators from historical data before EVERY session
3. **Quality Assignment** - Assign quality scores to historical bars before session starts
4. **Queue Loading** - Load queues with data for streaming phase
5. **Session Activation** - Signal that session is active
6. **Streaming Phase** - Time advancement and data processing
7. **End-of-Session** - Cleanup and advance to next day

### SessionData (Unified Store)

**Critical Concept:** `SessionData` is NOT just "today's data" - it's **ALL data** needed for analysis/decisions in the current session.

**Contains:**
1. **Historical Bars** - Trailing days (e.g., last 10 days of 1m bars)
2. **Historical Indicators** - Pre-calculated indicators from historical data
3. **Current Session Bars** - Bars arriving during today's session
4. **Real-Time Indicators** - Indicators calculated during the session
5. **Derived Data** - Generated intervals (5m from 1m, etc.)
6. **Quality Metrics** - Quality % per symbol per data type

**Data Flow:**
```
Coordinator Queues → SessionData → Analysis Engine
         ↓
    (append bars)
         ↓
    DataProcessor → SessionData
         ↓       (append derived bars)
         ↓
DataQualityManager → SessionData
                (update quality metrics)
```

**Zero-Copy Principle:**
- Bar objects exist **once** in memory
- Only **references** passed between containers
- Coordinator: `bar = queue.get()` → `session_data.append(bar)` (same object)
- Analysis Engine: Accesses bars by reference, no copying

**Access Pattern:**
```python
# ✅ Analysis Engine accesses data ONLY from SessionData
bars_1m = session_data.get_bars(symbol, "1m")
bars_5m = session_data.get_bars(symbol, "5m")
indicator = session_data.get_indicator("trailing_avg_volume")

# ❌ NEVER access queues or other sources directly
```

### Session Lifecycle

#### Phase 1: Initialization

```python
def _init_session(self):
    """Initialize session (called at start of each session)."""
    # 1. Clear old session data
    self.session_data.clear_all()
    
    # 2. Determine stream vs generate
    self._mark_stream_generate()  # Mark which data is STREAMED vs GENERATED
    
    # 3. Inform DataProcessor about derived intervals
    self.data_processor.set_derived_intervals(self._generated_data)
```

**Key Concept: Stream vs Generate Decision**

```
Backtest Mode:
├─ Base intervals (1m, 1d) → GENERATED (computed from DB)
└─ Derived intervals (5m, 15m) → GENERATED (computed from 1m bars)

Live Mode:
├─ Check API capabilities for each symbol
├─ If API supports interval → STREAMED (from API)
└─ If API doesn't support → GENERATED (computed from 1m bars)
```

#### Phase 2: Historical Management

```python
def _manage_historical_data(self):
    """Load historical data before session starts."""
    # For each historical data config:
    for hist_config in historical_config.data:
        # 1. Calculate date range (trailing_days before today)
        start_date = self._get_start_date_for_trailing_days(
            end_date=yesterday,
            trailing_days=hist_config.trailing_days
        )
        
        # 2. Load bars for each symbol and interval
        for symbol in symbols:
            for interval in intervals:
                bars = self._load_historical_bars(symbol, interval, start_date, end_date)
                
                # 3. Store in SessionData
                for bar in bars:
                    self.session_data.append_bar(symbol, interval, bar)
```

```python
def _calculate_historical_indicators(self):
    """Calculate ALL historical indicators before EVERY session."""
    for indicator_name, indicator_config in indicators.items():
        if indicator_config['type'] == 'trailing_average':
            result = self._calculate_trailing_average(indicator_name, indicator_config)
            self.session_data.set_indicator(indicator_name, result)
```

```python
def _calculate_historical_quality(self):
    """Assign quality scores to historical bars."""
    # DataQualityManager handles this
    # Ensures all historical data has quality scores before session starts
```

#### Phase 3: Queue Loading

```python
def _load_queues(self):
    """Load queues with data for streaming phase."""
    if self.mode == "backtest":
        self._load_backtest_queues()  # Prefetch days of data
    else:  # live mode
        self._start_live_streams()    # Start API streams
```

**Backtest Mode:**
- Load `prefetch_days` worth of data into queues
- Data pre-sorted by timestamp from database
- Zero sorting overhead

**Live Mode:**
- Start API streams for configured symbols
- DataManager handles stream lifecycle

#### Phase 4: Session Activation

```python
def _activate_session(self):
    """Signal that session is active."""
    # Notify all threads that session is ready
    self._notify_data_processor()
    self._notify_quality_manager()
    self._notify_analysis_engine()
```

#### Phase 5: Streaming Phase

```python
def _streaming_phase(self):
    """Main streaming loop with time advancement."""
    while not self._stop_event.is_set():
        # 1. Get next data timestamp from queues
        next_timestamp = self._get_next_queue_timestamp()
        
        if next_timestamp is None:
            # No more data - end session
            break
        
        # 2. Check if beyond market close
        if next_timestamp > market_close:
            break
        
        # 3. Advance time to next timestamp
        self._time_manager.set_backtest_time(next_timestamp)
        
        # 4. Process data at this timestamp
        bars_processed = self._process_queue_data_at_timestamp(next_timestamp)
        
        # 5. Apply clock-driven delay (if speed > 0)
        if speed_multiplier > 0:
            self._apply_clock_driven_delay(speed_multiplier)
```

**Time Advancement Rules:**
1. Time must stay within trading hours: `open_time <= time <= close_time`
2. Never exceed market close (if time > close, it's an error)
3. Data exhaustion: advance to market close and end session
4. Support data-driven (speed=0) and clock-driven (speed>0) modes

#### Phase 6: End-of-Session

```python
def _end_session(self):
    """End current session and prepare for next."""
    # 1. Clear queues
    self._clear_all_queues()
    
    # 2. Clear session bars (keep historical)
    self.session_data.clear_session_bars()
    
    # 3. Advance to next trading day (backtest only)
    if self.mode == "backtest":
        self._advance_to_next_trading_day(current_date)
```

### Configuration Structure

**Session Config Fields:**

```json
{
  "session_name": "My Trading Session",
  "exchange_group": "US_EQUITY",
  "asset_class": "EQUITY",
  "mode": "backtest",
  
  "backtest_config": {
    "backtest_days": 5,
    "speed_multiplier": 0,
    "prefetch_days": 2
  },
  
  "session_data_config": {
    "symbols": ["AAPL", "RIVN"],
    "streams": ["bars_1m"],
    
    "historical": {
      "data": [
        {
          "apply_to": "all",
          "intervals": ["1m", "1d"],
          "trailing_days": 10
        }
      ],
      "indicators": {
        "trailing_avg_volume": {
          "type": "trailing_average",
          "field": "volume",
          "period": "10d",
          "granularity": "daily"
        }
      }
    },
    
    "gap_filler": {
      "max_retries": 3,
      "retry_interval_seconds": 5,
      "enable_session_quality": true
    }
  }
}
```

**Key Fields:**

- `symbols`: List of symbols to trade (applies to ALL streams)
- `streams`: List of data streams needed (e.g., `["bars_1m", "ticks", "quotes"]`)
- `historical.data`: Historical data to load before EVERY session
- `historical.indicators`: Historical indicators to calculate before EVERY session
- `gap_filler`: Quality monitoring and gap filling configuration (LIVE MODE ONLY)

**Removed Fields (Old Architecture):**
- ❌ `data_streams` - Replaced by `symbols` + `streams`
- ❌ `derived_intervals` - Coordinator determines automatically
- ❌ `auto_compute_derived` - Always true (not configurable)
- ❌ `historical_bars` - Replaced by `historical.data`

---

## Code Patterns & Examples

### Thread Pattern

```python
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

### Manager Pattern

```python
from app.models.database import SessionLocal

class TimeManager:
    """Stateful orchestrator with synchronous API."""
    
    def __init__(self):
        self._cache = {}
        self._mode = "live"
        self._backtest_time = None
    
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

### Service Pattern

```python
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

### Repository Pattern

```python
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

# ❌ WRONG - Hardcoded time operations
class BadThread:
    def run(self):
        now = datetime.now()  # ❌ Don't use datetime.now()
        market_open = time(9, 30)  # ❌ Don't hardcode hours
```

---

## CLI & API

### CLI Architecture

**Location:** `app/cli/`

**Structure:**
```
cli/
├── __init__.py
├── interactive.py           # Main CLI shell
├── command_registry.py      # Command metadata
└── commands/                # Command implementations
    ├── system_commands.py   # system start, stop, status
    ├── data_commands.py     # data import, session, validate
    ├── time_commands.py     # time now, session, advance
    └── ...
```

**Key Features:**
- Three-level context-sensitive help
- Auto-discovers commands from registries
- Interactive shell with command history
- Namespace organization (system, data, time, etc.)

**Usage:**
```bash
./start_cli.sh

system@mismartera: help
system@mismartera: help data
system@mismartera: help data import-api
system@mismartera: system start
system@mismartera: data session
system@mismartera: time now
```

### REST API Architecture

**Location:** `app/api/`

**Structure:**
```
api/
├── __init__.py
├── main.py                  # FastAPI app
├── middleware/              # Auth, CORS, etc.
└── routes/                  # API endpoints
    ├── auth.py
    ├── market_data.py
    ├── system.py
    └── ...
```

**Exception:** API routes may use `async def` (FastAPI requirement).

```python
from fastapi import APIRouter
from app.managers.system_manager import get_system_manager

router = APIRouter()

@router.post("/system/start")
async def start_system(config_file: str):  # ✅ async is OK here
    """Start trading system."""
    system_mgr = get_system_manager()
    system_mgr.start(config_file)  # But manager method is sync
    return {"status": "started"}
```

---

## Testing Strategy

### Unit Tests

**Location:** `tests/unit/`

**Strategy:**
- Test services in isolation (pure functions)
- Mock managers and repositories
- Test thread logic without actual threads

```python
def test_gap_detection_service():
    # Test stateless service
    bars = [...]
    gaps = GapDetectionService.detect_gaps(
        symbol="AAPL",
        session_start=datetime(2025, 7, 2, 9, 30),
        current_time=datetime(2025, 7, 2, 10, 30),
        existing_bars=bars
    )
    assert len(gaps) == 2
```

### Integration Tests

**Location:** `tests/integration/`

**Strategy:**
- Test manager interactions
- Use real database (test database)
- Test thread communication

```python
def test_time_manager_integration():
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    with SessionLocal() as db:
        session = time_mgr.get_trading_session(db, date(2025, 7, 2))
        assert session.regular_open == time(9, 30)
```

### End-to-End Tests

**Location:** `tests/e2e/`

**Strategy:**
- Test complete workflows
- Start/stop system
- Run backtest sessions
- Validate CSV output

```python
def test_backtest_session():
    system_mgr = get_system_manager()
    system_mgr.start("session_configs/test_session.json")
    
    # Wait for backtest to complete
    while system_mgr.is_running():
        time.sleep(1)
    
    # Validate output
    assert os.path.exists("validation/test_session.csv")
```

---

## Migration Guide

### From Old Architecture

If you have code from the old architecture (before Nov 2025), here's how to migrate:

#### 1. Time Operations

**Old:**
```python
from datetime import datetime
now = datetime.now()  # ❌
```

**New:**
```python
time_mgr = system_mgr.get_time_manager()
now = time_mgr.get_current_time()  # ✅
```

#### 2. Database Access

**Old:**
```python
async with AsyncSessionLocal() as session:  # ❌
    result = await session.execute(query)
```

**New:**
```python
with SessionLocal() as session:  # ✅
    result = session.query(...).all()
```

#### 3. Thread Communication

**Old:**
```python
# Direct method call between threads
self.data_processor.process_bar(bar)  # ❌
```

**New:**
```python
# Use queue
self._output_queue.put(bar)  # ✅
```

#### 4. Configuration Access

**Old:**
```python
config.data_streams  # ❌ Removed
config.derived_intervals  # ❌ Removed
```

**New:**
```python
config.session_data_config.symbols  # ✅
config.session_data_config.streams  # ✅
# derived_intervals determined automatically by coordinator
```

---

## Related Documentation

This document consolidates the following:

- ✅ `ARCHITECTURE_REORGANIZATION.md` - Directory organization rationale
- ✅ `SESSION_ARCHITECTURE.md` - Session handling architecture
- ✅ `app/managers/time_manager/README.md` - TimeManager documentation
- ✅ `app/managers/data_manager/README.md` - DataManager documentation
- ✅ `THREADING_ARCHITECTURE_OVERVIEW.md` - Thread pool model

**These files can now be deleted or archived.**

---

## Quick Reference

### Common Tasks

| Task | Command / Code |
|------|----------------|
| Start system | `system_mgr.start("config.json")` |
| Get current time | `time_mgr.get_current_time()` |
| Get trading session | `time_mgr.get_trading_session(db, date)` |
| Query bars | `data_mgr.get_bars(symbol, interval, start, end)` |
| Access SessionData | `session_data.get_bars(symbol, interval)` |
| Run CLI | `./start_cli.sh` |
| System help | `help`, `help data`, `help data import-api` |

### Common Mistakes

| Mistake | Correct Approach |
|---------|------------------|
| Using `datetime.now()` | Use `time_mgr.get_current_time()` |
| Using `async def` in threads | Use regular `def` |
| Using `AsyncSessionLocal` | Use `SessionLocal` |
| Direct thread-to-thread calls | Use queues/events |
| Hardcoding market hours | Query from `time_mgr.get_trading_session()` |
| Accessing `config.data_streams` | Use `config.session_data_config.symbols/streams` |
| Converting timezones manually | Let TimeManager/DataManager handle it |
| Specifying timezone explicitly | Use system default (never specify) |
| Calling `.astimezone()` in app code | Work in market timezone throughout |
| Creating timezone objects | Use `time_mgr.get_current_time()` which is already in market TZ |

---

**End of Architecture Documentation**

For questions or clarifications, please refer to the specific sections above or contact the development team.
