# MisMartera System Architecture

**Version:** 1.1  
**Last Updated:** 2025-11-20

**Major Update (v1.1):** Added SystemManager as central coordinator and single source of truth for operation mode

## Overview

MisMartera is a day trading application with a **strictly layered architecture** that enforces clear separation of concerns. The system is built around three core top-level modules that provide well-defined APIs, ensuring that all interactions flow through proper channels.

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                │
│  ┌──────────────────┐              ┌──────────────────────────────┐ │
│  │   CLI Interface  │              │   FastAPI REST API           │ │
│  │  (Typer/Rich)    │              │   (JSON/HTTP)                │ │
│  └────────┬─────────┘              └──────────────┬───────────────┘ │
└───────────┼────────────────────────────────────────┼──────────────────┘
            │                                        │
            │  ┌─────────────────────────────────────┘
            │  │  API Calls ONLY (no direct DB/integration access)
            ▼  ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    SYSTEM COORDINATOR                                 │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  🎛️ SystemManager (Central Coordinator - NEW v1.1)             │  │
│  │                                                                  │  │
│  │  • Owns operation mode (live/backtest) - SINGLE SOURCE OF TRUTH │  │
│  │  • Controls system state (stopped/running/paused)               │  │
│  │  • Creates and manages all manager singletons                   │  │
│  │  • Provides inter-manager communication                         │  │
│  │  • start() / pause() / resume() / stop() / set_mode()          │  │
│  └───────────────────────────┬──────────────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │ Creates & References
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    TOP-LEVEL MODULE APIs                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │  📊 DataManager │  │ 📈 ExecutionMgr  │  │ 🧠 AnalysisEngine │     │
│  │  system_manager │  │  system_manager  │  │  system_manager   │     │
│  │       ↑         │  │       ↑          │  │       ↑           │     │
│  │ • get_time()    │  │ • place_order()  │  │ • analyze()       │     │
│  │ • get_bars()    │  │ • cancel_order() │  │ • optimize()      │     │
│  │ • get_ticks()   │  │ • get_orders()   │  │ • evaluate()      │     │
│  │ • trading_hrs() │  │ • get_balance()  │  │ • decide()        │     │
│  │ • get_holidays()│  │ • get_pnl()      │  │                   │     │
│  │ • import_data() │  │                  │  │                   │     │
│  └────────┬────────┘  └────────┬─────────┘  └─────────┬─────────┘     │
└───────────┼────────────────────┼──────────────────────┼──────────────┘
            │                    │                      │
            │                    │                      │
┌───────────┼────────────────────┼──────────────────────┼──────────────┐
│           │  INTERNAL COMPONENTS & DATA SOURCES       │              │
│           ▼                    ▼                      ▼              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐    │
│  │   Databases     │  │   Databases      │  │   Databases       │    │
│  │ • MarketData    │  │ • Orders         │  │ • Weights         │    │
│  │ • TickData      │  │ • Account        │  │ • SuccessRates    │    │
│  │ • Holidays      │  │ • Positions      │  │ • AnalysisLog     │    │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │              INTEGRATION LAYERS (Neutral Interfaces)            │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐     │ │
│  │  │ Data Sources │  │  Brokerages  │  │   LLM Providers    │     │ │
│  │  │              │  │              │  │                    │     │ │
│  │  │ • CSV/File   │  │ • Schwab API │  │ • Claude (Opus 4)  │     │ │
│  │  │ • Polygon    │  │ • Paper      │  │ • GPT-4 (future)   │     │ │
│  │  │ • AlphaVan.  │  │ • IBKR (fut) │  │ • Gemini (future)  │     │ │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

Legend:
━━━━━━━━►  API Calls (CLI/API → Managers)
─ ─ ─ ─ ►  Internal Calls (Managers → DBs/Integrations)
```

## 📁 Directory Structure

```
backend/app/
├── managers/                       # 🔥 Top-level Modules
│   ├── system_manager.py           # 🎛️ SystemManager (NEW v1.1)
│   │                               # Central coordinator, owns mode & state
│   │
│   ├── data_manager/               # 📊 DataManager
│   │   ├── api.py                  # Public API
│   │   ├── time_provider.py        # Time & trading hours
│   │   ├── repositories/           # Data access
│   │   │   ├── market_data_repo.py
│   │   │   ├── tick_data_repo.py
│   │   │   └── holiday_repo.py
│   │   └── integrations/           # Data sources
│   │       ├── base.py             # Abstract interface
│   │       ├── csv_import.py
│   │       ├── polygon_client.py
│   │       └── alphavantage_client.py
│   │
│   ├── execution_manager/          # 📈 ExecutionManager
│   │   ├── api.py                  # Public API
│   │   ├── order_engine.py         # Order logic
│   │   ├── repositories/           # Execution data
│   │   │   ├── orders_repo.py
│   │   │   └── account_repo.py
│   │   └── integrations/           # Brokerages
│   │       ├── base.py             # Abstract interface
│   │       ├── schwab_client.py
│   │       └── paper_trading.py
│   │
│   └── analysis_engine/            # 🧠 AnalysisEngine
│       ├── api.py                  # Public API
│       ├── evaluator.py            # Metrics
│       ├── optimizer.py            # Weight optimization
│       ├── decision_maker.py       # Trading decisions
│       ├── technical_indicators.py # Technical analysis
│       ├── repositories/           # Analysis data
│       │   ├── weights_repo.py
│       │   ├── success_rate_repo.py
│       │   └── analysis_log_repo.py
│       └── integrations/           # LLM providers
│           ├── base.py             # Abstract interface
│           ├── claude_client.py
│           ├── claude_analyzer.py
│           └── gpt4_client.py
│
├── api/                            # FastAPI REST API
│   └── routes/
│       ├── data.py                 # Calls DataManager API
│       ├── execution.py            # Calls ExecutionManager API
│       └── analysis.py             # Calls AnalysisEngine API
│
├── cli/                            # CLI Interface
│   └── commands/
│       ├── data.py                 # Calls DataManager API
│       ├── execution.py            # Calls ExecutionManager API
│       └── analysis.py             # Calls AnalysisEngine API
│
└── models/                         # Database Models
    ├── schemas.py                  # Market data
    ├── orders.py                   # Order models
    ├── account.py                  # Account models
    ├── weights.py                  # Weight models
    └── analysis_log.py             # Analysis logging
```

## 🎯 Architecture Principles

### 1. **API-First CLI**
The CLI must **only** execute commands by interacting with the externally exposed APIs of the top-level modules. Direct database or integration access is **strictly forbidden**.

✅ **Correct (v1.1 - SystemManager-based):**
```python
# CLI command - Use SystemManager to get managers
from app.managers import get_system_manager

system_mgr = get_system_manager()
data_manager = system_mgr.get_data_manager()
bars = data_manager.get_bars(session, symbol, start, end)
```

❌ **Incorrect:**
```python
# CLI command - NEVER do this!
bars = MarketDataRepository.get_bars_by_symbol(...)

# Also DEPRECATED (v1.0 pattern):
data_manager = DataManager()  # Don't instantiate directly
```

### 2. **Strict Layering**
```
CLI/API Routes → Manager APIs → Repositories/Integrations → Database/External APIs
```

Each layer can only call the layer directly below it.

### 3. **Single Source of Truth**
- **SystemManager** is the single source for operation mode (live/backtest) and system state (NEW v1.1)
- **DataManager** is the single source for ALL data (time, bars, ticks, holidays)
- **ExecutionManager** is the single source for ALL order/account operations
- **AnalysisEngine** consumes data from DataManager and executes via ExecutionManager
- All managers receive SystemManager reference for mode queries and inter-manager communication

### 4. **Operating Modes (Managed by SystemManager)**
SystemManager owns the operation mode state. All managers query SystemManager.mode:
- **Live Mode:** Live trading with live data and actual brokers
- **Backtest Mode:** Historical simulation with database data

Mode can only be changed when system is in STOPPED state via `system_mgr.set_mode()`

## 🎛️ SystemManager (NEW v1.1)

**Responsibility:** Central coordinator and single source of truth for operation mode and system state.

### Key Concepts

- **Singleton Pattern:** Only one SystemManager instance exists per application
- **Owns Operation Mode:** Live vs Backtest mode stored in `SystemManager.mode`
- **Manages System State:** STOPPED, RUNNING, PAUSED states
- **Creates Managers:** DataManager, ExecutionManager, AnalysisEngine created via SystemManager
- **Inter-Manager Communication:** Managers access each other via SystemManager reference

### Key Methods
```python
# System Lifecycle
start() -> None                     # Start the system (enter RUNNING state)
pause() -> None                     # Pause the system (backtest time stops advancing)
resume() -> None                    # Resume from paused state
stop() -> None                      # Stop the system (return to STOPPED state)

# Mode Management
set_mode(mode: str) -> bool        # Set mode ("live" or "backtest") - only when STOPPED
mode: OperationMode                 # Current mode (read-only property)
is_live_mode() -> bool
is_backtest_mode() -> bool

# State Management  
state: SystemState                  # Current state (read-only property)
is_running() -> bool
is_paused() -> bool
is_stopped() -> bool

# Manager Access
get_data_manager() -> DataManager
get_execution_manager() -> ExecutionManager
get_analysis_engine() -> AnalysisEngine
```

### State Transitions
```
STOPPED ──start()──> RUNNING ──pause()──> PAUSED
   ↑                    │                    │
   │                    │                    │
   └────────stop()──────┴────────resume()────┘
```

### Usage Example
```python
from app.managers import get_system_manager

# Get singleton instance
system_mgr = get_system_manager()

# Set mode (only when stopped)
system_mgr.set_mode("backtest")

# Get managers (created with SystemManager reference)
data_mgr = system_mgr.get_data_manager()
exec_mgr = system_mgr.get_execution_manager()

# Control system
system_mgr.start()   # Begin processing
system_mgr.pause()   # Pause (backtest time stops)
system_mgr.resume()  # Continue
system_mgr.stop()    # Full stop
```

## 📊 DataManager

**Responsibility:** Single source of truth for all datasets.

**Architecture:** Receives SystemManager reference. Queries mode via `system_manager.mode.value`.

### Key Methods
```python
# Time & Status (mode-aware via SystemManager)
get_current_time() -> datetime              # Live: system time | Backtest: simulated time
is_market_open(timestamp) -> bool
get_trading_hours(date) -> TradingHours
get_holidays(start_date, end_date) -> List[Holiday]

# Mode Query (delegates to SystemManager)
system_manager.mode.value -> str            # "live" or "backtest"

# Market Data (Bars)
get_bars(symbol, start, end, interval) -> List[BarData]
get_latest_bar(symbol) -> BarData
stream_bars(symbols) -> AsyncIterator[BarData]

# Tick Data
get_ticks(symbol, start, end) -> List[TickData]
stream_ticks(symbols) -> AsyncIterator[TickData]

# Data Import
import_csv(file_path, symbol, **options) -> ImportResult
import_from_api(source, symbol, **options) -> ImportResult

# Data Quality
check_data_quality(symbol) -> Dict
get_symbols() -> List[str]
get_date_range(symbol) -> Tuple[datetime, datetime]
```

### Integration Layer
All data sources implement `DataSourceInterface`:
- `csv_import.py` - CSV file import
- `polygon_client.py` - Polygon.io API (future)
- `alphavantage_client.py` - Alpha Vantage API (future)

## 📈 ExecutionManager

**Responsibility:** All order execution and account management.

**Architecture:** Receives SystemManager reference for mode queries and inter-manager access.

### Key Methods
```python
# Order Placement
place_order(account_id, symbol, quantity, side, order_type, price) -> OrderResult
cancel_order(order_id) -> CancelResult
modify_order(order_id, **changes) -> OrderResult

# Order Information
get_open_orders(account_id) -> List[Order]
get_order_history(account_id, start_date, end_date) -> List[Order]

# Account Information
get_balance(account_id) -> AccountBalance
get_trading_power(account_id) -> float
get_pnl(account_id, start_date, end_date) -> PnLReport
```

### Integration Layer
All brokerages implement `BrokerageInterface`:
- `schwab_client.py` - Charles Schwab API
- `paper_trading.py` - Paper trading simulation (future)
- `ibkr_client.py` - Interactive Brokers (future)

### Order Rules
- All orders **must** use `TimeInForce.DAY` (expire at end-of-day)
- Orders are tracked in the `orders` database table
- Executions are logged in `order_executions` table

## 🧠 AnalysisEngine

**Responsibility:** AI-powered trading analysis and decision making.

**Architecture:** Receives SystemManager reference for mode queries and accessing DataManager/ExecutionManager.

### Key Methods
```python
# Analysis
analyze_bar(symbol, bar, recent_bars) -> AnalysisResult
evaluate_metrics(symbol) -> MetricsResult
calculate_probability(symbol, direction) -> float

# Decision Making
make_decision(symbol, analysis) -> Decision

# Optimization
optimize_weights(symbol, historical_data) -> WeightSet

# LLM Consultation (internal)
_consult_llm(bar, indicators, recent_bars) -> LLMResponse
```

### Integration Layer
All LLM providers implement `LLMInterface`:
- `claude_client.py` + `claude_analyzer.py` - Claude Opus 4
- `gpt4_client.py` - GPT-4 (future)
- `gemini_client.py` - Google Gemini (future)

### Analysis Logging
Every analysis is logged with comprehensive details:

```python
class AnalysisLog:
    # Bar data at time of analysis
    bar_timestamp, bar_open, bar_high, bar_low, bar_close, bar_volume
    
    # Decision made
    decision, decision_price, decision_quantity, decision_rationale
    
    # Success score (updated later after outcome)
    success_score, actual_outcome, actual_pnl
    
    # LLM interaction details
    llm_provider, llm_model, llm_prompt, llm_response
    llm_latency_ms, llm_cost_usd
    llm_input_tokens, llm_output_tokens
    buy_probability, sell_probability, confidence
    
    # Technical indicators
    indicators_json
    detected_patterns, key_indicators, risk_factors
```

## 🔄 Data Flow Example

### Example: Analyzing a Stock and Placing an Order

```python
# 1. Get SystemManager and set mode
from app.managers import get_system_manager

system_mgr = get_system_manager()
system_mgr.set_mode("live")  # Set operation mode

# 2. Get managers from SystemManager (all have system_manager reference)
data_manager = system_mgr.get_data_manager()
execution_manager = system_mgr.get_execution_manager()
analysis_engine = system_mgr.get_analysis_engine()

# 3. Start the system
system_mgr.start()

# 4. Get current bar from DataManager
current_bar = data_manager.get_latest_bar(session, "AAPL")

# 5. Get recent bars for context
start_time = current_bar.timestamp - timedelta(minutes=50)
recent_bars = data_manager.get_bars(session, "AAPL", start_time, current_bar.timestamp)

# 6. Analyze with AnalysisEngine
analysis = analysis_engine.analyze_bar(session, "AAPL", current_bar, recent_bars)

# 7. If decision is BUY, place order via ExecutionManager
if analysis["decision"]["action"] == "BUY":
    order = execution_manager.place_order(
        session=session,
        account_id="default",
        symbol="AAPL",
        quantity=10,
        side="BUY",
        order_type="MARKET"
    )
```

## 🎛️ Operating Modes (SystemManager-Controlled)

### Live Mode
- Time: `datetime.now()` (Eastern Time)
- Data: Live streams from data providers (Alpaca, etc.)
- Orders: Submitted to actual brokerage
- State: SystemManager controls when system is running/paused

### Backtest Mode
- Time: Simulated time advanced by BacktestStreamCoordinator
- Data: Historical bars from database
- Orders: Simulated with configurable execution logic  
- State: SystemManager.pause() stops time advancement

### Switching Modes (v1.1)
```python
from app.managers import get_system_manager

# Get SystemManager singleton
system_mgr = get_system_manager()

# Mode can only be changed when STOPPED
system_mgr.stop()  # Ensure stopped
system_mgr.set_mode("backtest")  # Change mode

# Get DataManager (has system_manager reference)
data_mgr = system_mgr.get_data_manager()

# Start processing
system_mgr.start()

# Process bars (time advanced by BacktestStreamCoordinator)
for bar in historical_bars:
    # Time is automatically advanced by stream coordinator
    # System can be paused/resumed via system_mgr
    process_bar(bar)

# Control system state
system_mgr.pause()   # Pause backtest (time stops advancing)
system_mgr.resume()  # Resume
system_mgr.stop()    # Stop completely
```

### Architecture Notes (v1.1)

**Single Source of Truth:**
- `SystemManager.mode` is the ONLY source for operation mode
- `DataManager.get_mode()` delegates to SystemManager (deprecated pattern)
- `TimeProvider` requires SystemManager reference
- No direct access to `settings.SYSTEM_OPERATING_MODE` in production code

**State-Aware Streaming:**
- `BacktestStreamCoordinator` checks `SystemManager.is_running()`
- If system is paused, time advancement halts
- Allows inspection/debugging during backtest execution

## 🔒 Security & Best Practices

1. **Never bypass the API layer** - Always go through DataManager, ExecutionManager, or AnalysisEngine
2. **Use integration interfaces** - All external integrations must implement the base interface
3. **Log everything** - Use the AnalysisLog table for comprehensive audit trail
4. **Handle modes properly** - Always check/set the operating mode
5. **Validate inputs** - Managers should validate all inputs before processing

## 📝 Testing Strategy

- **Unit Tests:** Test each manager API independently with mocked dependencies
- **Integration Tests:** Test manager interactions
- **End-to-End Tests:** Test full flow from CLI/API through all layers
- **Backtest Tests:** Validate backtest mode accuracy

## 🚀 Future Enhancements

1. **Additional Data Sources:** Polygon, Alpha Vantage, Yahoo Finance
2. **Additional Brokerages:** Interactive Brokers, TD Ameritrade
3. **Additional LLMs:** GPT-4, Gemini, Llama
4. **WebSocket Streaming:** Real-time data streaming
5. **Advanced Backtesting:** Multi-symbol, portfolio-level backtesting
6. **Risk Management:** Position sizing, portfolio limits
7. **Performance Monitoring:** Real-time metrics dashboard

---

**For implementation details, see the code in `app/managers/` directory.**
