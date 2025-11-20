# MisMartera System Architecture

**Version:** 1.0  
**Last Updated:** 2025-11-18

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
│                    TOP-LEVEL MODULE APIs                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐     │
│  │  📊 DataManager │  │ 📈 ExecutionMgr  │  │ 🧠 AnalysisEngine │     │
│  │                 │  │                  │  │                   │     │
│  │ • get_time()    │  │ • place_order()  │  │ • analyze()       │     │
│  │ • get_bars()    │  │ • cancel_order() │  │ • optimize()      │     │
│  │ • get_ticks()   │  │ • get_orders()   │  │ • evaluate()      │     │
│  │ • trading_hrs() │  │ • get_balance()  │  │ • decide()        │     │
│  │ • get_holidays()│  │ • get_pnl()      │  │                   │     │
│  │ • import_data() │  │                  │  │                   │     │
│  │                 │  │                  │  │                   │     │
│  │ Modes:          │  │ Modes:           │  │ Modes:            │     │
│  │ • Real          │  │ • Real           │  │ • Real            │     │
│  │ • Backtest      │  │ • Backtest       │  │ • Backtest        │     │
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

✅ **Correct:**
```python
# CLI command
data_manager = DataManager()
bars = await data_manager.get_bars(session, symbol, start, end)
```

❌ **Incorrect:**
```python
# CLI command - NEVER do this!
bars = await MarketDataRepository.get_bars_by_symbol(...)
```

### 2. **Strict Layering**
```
CLI/API Routes → Manager APIs → Repositories/Integrations → Database/External APIs
```

Each layer can only call the layer directly below it.

### 3. **Single Source of Truth**
- **DataManager** is the single source for ALL data (time, bars, ticks, holidays)
- **ExecutionManager** is the single source for ALL order/account operations
- **AnalysisEngine** consumes data from DataManager and executes via ExecutionManager

### 4. **Operating Modes**
All three core modules support two modes:
- **Real Mode:** Live trading with real data and actual brokers
- **Backtest Mode:** Historical simulation with database data

## 📊 DataManager

**Responsibility:** Single source of truth for all datasets.

### Key Methods
```python
# Time & Status
get_current_time() -> datetime
is_market_open(timestamp) -> bool
get_trading_hours(date) -> TradingHours
get_holidays(start_date, end_date) -> List[Holiday]

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
# 1. Initialize managers
data_manager = DataManager(mode="real")
execution_manager = ExecutionManager(mode="real", brokerage="schwab")
analysis_engine = AnalysisEngine(data_manager, execution_manager, mode="real")

# 2. Get current bar from DataManager
current_bar = await data_manager.get_latest_bar(session, "AAPL")

# 3. Get recent bars for context
start_time = current_bar.timestamp - timedelta(minutes=50)
recent_bars = await data_manager.get_bars(session, "AAPL", start_time, current_bar.timestamp)

# 4. Analyze with AnalysisEngine
analysis = await analysis_engine.analyze_bar(session, "AAPL", current_bar, recent_bars)

# 5. If decision is BUY, place order via ExecutionManager
if analysis["decision"]["action"] == "BUY":
    order = await execution_manager.place_order(
        session=session,
        account_id="default",
        symbol="AAPL",
        quantity=10,
        side="BUY",
        order_type="MARKET"
    )
```

## 🎛️ Operating Modes

### Real Mode
- Time: `datetime.now()`
- Data: Live streams from data providers
- Orders: Submitted to actual brokerage

### Backtest Mode
- Time: From 1-minute bar timestamp being processed
- Data: Historical bars from database
- Orders: Simulated with configurable execution logic

### Switching Modes
```python
# Initialize in backtest mode
data_manager = DataManager(mode="backtest")

# Set backtest time for each bar
for bar in historical_bars:
    data_manager.time_provider.set_backtest_time(bar.timestamp)
    # Process bar...
```

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
