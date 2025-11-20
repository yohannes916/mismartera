# Migration Guide: New Architecture

**Date:** 2025-11-18  
**Version:** 1.0 → 2.0

This guide helps you migrate existing code to the new strictly layered architecture.

## 🎯 What Changed

### Before (Old Structure)
```python
# CLI commands directly accessing repositories
from app.repositories.market_data_repository import MarketDataRepository

async def import_data(file_path, symbol):
    async with AsyncSessionLocal() as session:
        bars = await MarketDataRepository.get_bars_by_symbol(...)
```

### After (New Structure)
```python
# CLI commands using manager APIs
from app.managers.data_manager.api import DataManager

async def import_data(file_path, symbol):
    data_manager = DataManager(mode="real")
    async with AsyncSessionLocal() as session:
        result = await data_manager.import_csv(session, file_path, symbol)
```

## 📦 New Module Structure

### 1. DataManager (`app/managers/data_manager/`)

**Old Locations → New Locations:**
- `app/repositories/market_data_repository.py` → `app/managers/data_manager/repositories/market_data_repo.py`
- `app/repositories/trading_calendar_repository.py` → `app/managers/data_manager/repositories/holiday_repo.py`
- `app/services/csv_import_service.py` → `app/managers/data_manager/integrations/csv_import.py`
- `app/services/holiday_import_service.py` → `app/managers/data_manager/integrations/` (to be moved)

**Usage:**
```python
from app.managers import DataManager

# Initialize
data_manager = DataManager(mode="real")

# Get data
bars = await data_manager.get_bars(session, "AAPL", start, end)
current_time = data_manager.get_current_time()
is_open = await data_manager.is_market_open(session)
```

### 2. ExecutionManager (`app/managers/execution_manager/`)

**Old Locations → New Locations:**
- `app/integrations/schwab_client.py` → `app/managers/execution_manager/integrations/schwab_client.py`

**New Models:**
- `app/models/orders.py` - Order and OrderExecution
- `app/models/account.py` - Account, AccountTransaction, Position

**Usage:**
```python
from app.managers import ExecutionManager

# Initialize
execution_manager = ExecutionManager(mode="real", brokerage="schwab")

# Place order
order = await execution_manager.place_order(
    session=session,
    account_id="default",
    symbol="AAPL",
    quantity=10,
    side="BUY",
    order_type="MARKET"
)

# Get balance
balance = await execution_manager.get_balance(session)
```

### 3. AnalysisEngine (`app/managers/analysis_engine/`)

**Old Locations → New Locations:**
- `app/services/technical_indicators.py` → `app/managers/analysis_engine/technical_indicators.py`
- `app/services/claude_probability.py` → `app/managers/analysis_engine/integrations/claude_analyzer.py`
- `app/integrations/claude_client.py` → `app/managers/analysis_engine/integrations/claude_client.py`

**New Models:**
- `app/models/weights.py` - WeightSet, WeightPerformance
- `app/models/analysis_log.py` - AnalysisLog, AnalysisMetrics

**Usage:**
```python
from app.managers import DataManager, ExecutionManager, AnalysisEngine

# Initialize (note: depends on other managers)
data_manager = DataManager(mode="real")
execution_manager = ExecutionManager(mode="real")
analysis_engine = AnalysisEngine(data_manager, execution_manager, mode="real")

# Analyze
analysis = await analysis_engine.analyze_bar(session, "AAPL", current_bar, recent_bars)

# Get probability
prob = await analysis_engine.calculate_probability(session, "AAPL", "BUY")
```

## 🔄 Updating CLI Commands

### Old CLI Command Pattern
```python
# app/cli/commands/data.py (OLD)
from app.services.csv_import_service import csv_import_service
from app.repositories.market_data_repository import MarketDataRepository

async def list_symbols():
    async with AsyncSessionLocal() as session:
        # Direct repository access - WRONG!
        symbols = await MarketDataRepository.get_symbols(session)
```

### New CLI Command Pattern
```python
# app/cli/commands/data.py (NEW)
from app.managers import DataManager

async def list_symbols():
    data_manager = DataManager(mode="real")
    async with AsyncSessionLocal() as session:
        # Via manager API - CORRECT!
        symbols = await data_manager.get_symbols(session)
```

### Migration Checklist for CLI Commands

- [ ] Replace direct repository imports with manager imports
- [ ] Initialize appropriate manager(s)
- [ ] Call manager API methods instead of repository methods
- [ ] Remove direct integration access

## 🌐 Updating API Routes

### Old API Route Pattern
```python
# app/api/routes/data.py (OLD)
from app.repositories.market_data_repository import MarketDataRepository

@router.get("/bars/{symbol}")
async def get_bars(symbol: str, session: AsyncSession = Depends(get_db)):
    # Direct repository access - WRONG!
    bars = await MarketDataRepository.get_bars_by_symbol(session, symbol)
    return bars
```

### New API Route Pattern
```python
# app/api/routes/data.py (NEW)
from app.managers import DataManager

# Initialize manager (could be done at module level)
data_manager = DataManager(mode="real")

@router.get("/bars/{symbol}")
async def get_bars(symbol: str, session: AsyncSession = Depends(get_db)):
    # Via manager API - CORRECT!
    bars = await data_manager.get_bars(session, symbol, start, end)
    return [bar.__dict__ for bar in bars]
```

### Migration Checklist for API Routes

- [ ] Replace direct repository imports with manager imports
- [ ] Initialize manager(s) at module level or per-request
- [ ] Call manager API methods instead of repository/service methods
- [ ] Remove direct integration access

## 🆕 New Database Models

Run database migration to create new tables:

```bash
make run-cli ARGS="init-db"
```

New tables created:
- `orders` - Order tracking
- `order_executions` - Order fill details
- `accounts` - Account information
- `account_transactions` - Transaction history
- `positions` - Current positions
- `weight_sets` - Optimized weights
- `weight_performance` - Weight performance history
- `analysis_logs` - Comprehensive analysis logging
- `analysis_metrics` - Aggregated metrics per symbol

## 📝 Updated Imports

### Before
```python
from app.repositories.market_data_repository import MarketDataRepository
from app.services.csv_import_service import csv_import_service
from app.services.claude_probability import ClaudeProbabilityAnalyzer
from app.integrations.schwab_client import schwab_client
```

### After
```python
from app.managers import DataManager, ExecutionManager, AnalysisEngine
from app.models.orders import Order, OrderExecution
from app.models.account import Account, Position
from app.models.analysis_log import AnalysisLog
```

## 🚫 What NOT to Do

### ❌ Don't Bypass Manager APIs
```python
# WRONG - Direct repository access from CLI/API
from app.managers.data_manager.repositories.market_data_repo import MarketDataRepository
bars = await MarketDataRepository.get_bars_by_symbol(...)
```

### ❌ Don't Access Integrations Directly
```python
# WRONG - Direct integration access from CLI/API
from app.managers.execution_manager.integrations.schwab_client import SchwabClient
client = SchwabClient()
await client.place_order(...)
```

### ✅ Always Use Manager APIs
```python
# CORRECT - Via manager API
from app.managers import ExecutionManager
execution_manager = ExecutionManager(mode="real", brokerage="schwab")
await execution_manager.place_order(...)
```

## 🔧 Backtest Mode

The new architecture fully supports backtest mode:

```python
# Initialize in backtest mode
data_manager = DataManager(mode="backtest")
execution_manager = ExecutionManager(mode="backtest")
analysis_engine = AnalysisEngine(
    data_manager, 
    execution_manager, 
    mode="backtest"
)

# Process historical bars
for bar in historical_bars:
    # Set backtest time
    data_manager.time_provider.set_backtest_time(bar.timestamp)
    
    # Analyze
    analysis = await analysis_engine.analyze_bar(session, symbol, bar, recent_bars)
    
    # Execute if decision is made
    if analysis["decision"]["action"] == "BUY":
        order = await execution_manager.place_order(...)
```

## 📊 Analysis Logging

All analysis is now automatically logged with comprehensive details:

```python
# When you call analyze_bar, it automatically logs:
analysis = await analysis_engine.analyze_bar(session, "AAPL", bar, recent_bars)

# This creates an AnalysisLog entry with:
# - Bar data (OHLCV)
# - Decision made (BUY/SELL/HOLD)
# - LLM details (prompt, response, cost, latency, tokens)
# - Technical indicators
# - Success score (updated later)
```

Query analysis logs:
```python
from app.models.analysis_log import AnalysisLog
from sqlalchemy import select

# Get recent analyses for a symbol
result = await session.execute(
    select(AnalysisLog)
    .where(AnalysisLog.symbol == "AAPL")
    .order_by(AnalysisLog.timestamp.desc())
    .limit(100)
)
logs = result.scalars().all()

# Check LLM costs
total_cost = sum(log.llm_cost_usd for log in logs if log.llm_cost_usd)
print(f"Total LLM cost: ${total_cost:.2f}")
```

## 🧪 Testing

Test your migration with a simple script:

```python
# test_migration.py
import asyncio
from app.managers import DataManager, ExecutionManager, AnalysisEngine
from app.models.database import AsyncSessionLocal

async def test():
    data_manager = DataManager(mode="real")
    execution_manager = ExecutionManager(mode="real")
    analysis_engine = AnalysisEngine(data_manager, execution_manager)
    
    async with AsyncSessionLocal() as session:
        # Test DataManager
        symbols = await data_manager.get_symbols(session)
        print(f"✓ DataManager: Found {len(symbols)} symbols")
        
        # Test ExecutionManager
        balance = await execution_manager.get_balance(session)
        print(f"✓ ExecutionManager: Balance ${balance['cash_balance']:.2f}")
        
        # Test AnalysisEngine
        metrics = await analysis_engine.evaluate_metrics(session, "AAPL")
        print(f"✓ AnalysisEngine: Metrics loaded")

if __name__ == "__main__":
    asyncio.run(test())
```

## 📚 Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Comprehensive architecture documentation
- [README.md](README.md) - Updated project overview
- Manager source code:
  - `app/managers/data_manager/api.py`
  - `app/managers/execution_manager/api.py`
  - `app/managers/analysis_engine/api.py`

## ❓ Common Questions

**Q: Can I still use the old repositories directly?**  
A: The old files still exist for now, but CLI/API code should ONLY use manager APIs.

**Q: What if I need functionality not exposed by manager APIs?**  
A: Add the method to the appropriate manager's API. Never bypass the API layer.

**Q: How do I add a new data source?**  
A: Implement `DataSourceInterface` in `app/managers/data_manager/integrations/`.

**Q: How do I add a new brokerage?**  
A: Implement `BrokerageInterface` in `app/managers/execution_manager/integrations/`.

**Q: How do I add a new LLM provider?**  
A: Implement `LLMInterface` in `app/managers/analysis_engine/integrations/`.

---

**Need help with migration? Check the architecture documentation or examine the manager API source code for examples.**
