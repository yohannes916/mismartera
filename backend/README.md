# MisMartera Trading Backend

A high-performance day trading application with **clean architecture**, Charles Schwab API integration, and Claude AI analysis engine.

---

## 🚀 Quick Start

```bash
# 1. Setup
cd backend
make setup

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Initialize database
make run-cli ARGS="init-db"

# 4. Start interactive CLI
./start_cli.sh
```

---

## 📚 Documentation

**Complete architecture documentation is in the [`docs/`](docs/) directory:**

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Complete architecture reference
- **[docs/SYSTEM_MANAGER_REFACTOR.md](docs/SYSTEM_MANAGER_REFACTOR.md)** - SystemManager implementation
- **[docs/TIME_MANAGER.md](docs/TIME_MANAGER.md)** - TimeManager API and usage
- **[docs/DATA_MANAGER.md](docs/DATA_MANAGER.md)** - DataManager API and usage

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────┐
│         SystemManager (Orchestrator)            │
│  • Creates and manages all components           │
│  • Single source of truth for system state      │
│  • Provides singleton access to managers        │
└────────────────┬────────────────────────────────┘
                 │ Creates & Manages
                 ▼
┌─────────────────────────────────────────────────┐
│  MANAGERS (Stateful Facades)                    │
│  • TimeManager - All time/calendar operations   │
│  • DataManager - All data operations            │
│  • ExecutionManager - Order execution           │
└────────────────┬────────────────────────────────┘
                 │ Uses
                 ▼
┌─────────────────────────────────────────────────┐
│  4-THREAD POOL (Background Workers)             │
│  1. SessionCoordinator - Orchestrates lifecycle │
│  2. DataProcessor - Derived bars + indicators   │
│  3. DataQualityManager - Quality + gap filling  │
│  4. AnalysisEngine - Strategy execution         │
└─────────────────────────────────────────────────┘
```

### Key Principles

1. **Synchronous Thread Pool** - Uses `threading.Thread`, NOT `asyncio`
2. **Single Source of Truth** - All time via TimeManager, state via SystemManager
3. **Zero-Copy Data Flow** - Data objects referenced, not copied
4. **Timezone Handling** - Work in market timezone, convert at boundaries
5. **Layer Isolation** - Downward dependencies only

**See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete details.**

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── core/                    # ⭐ Fundamental primitives
│   │   ├── session_data.py      # Unified data store
│   │   ├── enums.py             # SystemState, OperationMode
│   │   ├── exceptions.py        # Custom exceptions
│   │   └── data_structures/     # Bar, Quote, Tick
│   │
│   ├── managers/                # Stateful orchestrators
│   │   ├── system_manager/      # SystemManager (central)
│   │   ├── time_manager/        # TimeManager (time/calendar)
│   │   ├── data_manager/        # DataManager (market data)
│   │   └── execution_manager/   # ExecutionManager (orders)
│   │
│   ├── threads/                 # Background workers
│   │   ├── session_coordinator.py
│   │   ├── data_processor.py
│   │   ├── data_quality_manager.py
│   │   └── analysis_engine.py
│   │
│   ├── services/                # Stateless business logic
│   ├── repositories/            # Database access (CRUD)
│   ├── integrations/            # External APIs
│   ├── models/                  # Database models
│   ├── api/                     # REST API
│   ├── cli/                     # CLI interface
│   └── utils/                   # Utilities
│
├── session_configs/             # Session configurations
├── tests/                       # Test suite
├── docs/                        # Documentation
└── README.md                    # This file
```

---

## 🎯 Core Concepts

### SystemManager

Central orchestrator that:
- Creates all managers (TimeManager, DataManager, etc.)
- Creates and wires 4-thread pool
- Tracks system state (STOPPED, RUNNING)
- Provides singleton access via `get_system_manager()`

```python
from app.managers import get_system_manager

system_mgr = get_system_manager()
system_mgr.start("session_configs/example_session.json")
```

### TimeManager

**Single source of truth for ALL time operations:**
- ✅ Use `time_mgr.get_current_time()` (NEVER `datetime.now()`)
- ✅ Use `time_mgr.get_trading_session()` (NEVER hardcode 9:30/16:00)
- ✅ Use `time_mgr.is_holiday()` (NEVER manual checks)

### DataManager

Manages all market data:
- Bar streaming (1m bars only, derives other intervals)
- Historical data loading
- Session data (unified store)
- Quality monitoring

### 4-Thread Pool

1. **SessionCoordinator** - Orchestrates session lifecycle
2. **DataProcessor** - Generates derived bars (5m, 15m) from 1m bars
3. **DataQualityManager** - Monitors quality, fills gaps (live only)
4. **AnalysisEngine** - Runs strategies, generates signals

---

## 💻 Usage

### Interactive CLI

```bash
# Start interactive CLI
./start_cli.sh

# In CLI:
system@mismartera: system start                    # Start system
system@mismartera: data session                    # View session data
system@mismartera: time now                        # Current time
system@mismartera: help                            # Show all commands
system@mismartera: help data                       # Show data commands
system@mismartera: help data import-api            # Detailed command help
```

### Common Commands

| Task | Command |
|------|---------|
| Start system | `system start` |
| View session | `data session` |
| Import historical data | `data import-api AAPL 30` |
| Check time | `time now` |
| View trading session | `time session` |
| Import holidays | `time import-holidays` |
| Get help | `help` or `help <namespace>` |

### Python API

```python
from app.managers import get_system_manager

# Get system manager
system_mgr = get_system_manager()

# Start system
system_mgr.start("session_configs/example_session.json")

# Access managers
time_mgr = system_mgr.get_time_manager()
data_mgr = system_mgr.get_data_manager()

# Use managers
current_time = time_mgr.get_current_time()
bars = data_mgr.get_bars("AAPL", "1m", start_date, end_date)

# Stop system
system_mgr.stop()
```

---

## ⚙️ Installation

### 1. Setup Environment

```bash
cd backend
make setup
```

This downloads an embedded Python, creates a virtual environment, and installs dependencies (~2-3 minutes).

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# Required for trading
SCHWAB_APP_KEY=your_schwab_app_key
SCHWAB_APP_SECRET=your_schwab_secret

# Required for AI analysis
ANTHROPIC_API_KEY=your_anthropic_api_key

# Security
SECRET_KEY=generate-a-secure-random-key-here
```

### 3. Initialize Database

```bash
make run-cli ARGS="init-db"
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run specific test type
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=app tests/
```

Test structure:
- `tests/unit/` - Unit tests (fast, isolated)
- `tests/integration/` - Integration tests (managers, database)
- `tests/e2e/` - End-to-end tests (full system)

---

## 📖 Development Guide

### Adding New Features

1. **Determine component type** (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):
   - Thread? Manager? Service? Repository?
   - Use decision tables in architecture doc

2. **Place in correct directory**:
   - Threads → `app/threads/`
   - Managers → `app/managers/`
   - Services → `app/services/`
   - Repositories → `app/repositories/`

3. **Follow patterns**:
   - Thread: Use `threading.Thread`, NOT `async`
   - Manager: Stateful facade, synchronous API
   - Service: Stateless utility, pure functions
   - Repository: Database access with `SessionLocal`

### Common Mistakes to Avoid

| ❌ Don't | ✅ Do |
|---------|------|
| `datetime.now()` | `time_mgr.get_current_time()` |
| Hardcode market hours (9:30, 16:00) | `time_mgr.get_trading_session()` |
| Use `async def` in threads/managers | Use regular `def` |
| Convert timezones manually | Let TimeManager handle it |
| Use `AsyncSessionLocal` | Use `SessionLocal` |

### Code Patterns

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for complete code patterns and examples.

---

## 🛠️ Technology Stack

- **Python 3.10+** - Core language
- **Threading** - Concurrency model (NO asyncio)
- **SQLAlchemy** - ORM with synchronous sessions
- **FastAPI** - REST API (async allowed in routes only)
- **Typer + Rich** - CLI framework
- **Loguru** - Advanced logging
- **Pandas** - Data processing
- **Charles Schwab API** - Market data and execution
- **Claude API** - AI analysis

---

## 🔒 Security

- Environment variables for secrets (never commit `.env`)
- JWT tokens for authentication
- No hardcoded credentials
- CORS configured for Electron app

---

## 📝 Logging

Logs stored in `data/logs/app.log`:
- Automatic rotation (10 MB)
- Retention (30 days)
- Compression (zip)

Console output includes:
- Colored log levels
- Timestamps
- Function names and line numbers
- Backtrace on errors

Change log level at runtime:
```bash
admin log-level DEBUG
```

---

## 🐛 Troubleshooting

### API Not Starting

```bash
# Check port availability
lsof -i :8000

# Use different port
python run_cli.py server --port 8001
```

### Database Issues

```bash
# Recreate database
rm data/trading_app.db
make run-cli ARGS="init-db"
```

### Import Errors

```bash
# Verify imports
python -c "from app.managers import get_system_manager; print('✅ OK')"

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

---

## 📚 Additional Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Complete architecture reference
- **[docs/SYSTEM_MANAGER_REFACTOR.md](docs/SYSTEM_MANAGER_REFACTOR.md)** - SystemManager details
- **[docs/TIME_MANAGER.md](docs/TIME_MANAGER.md)** - TimeManager API
- **[docs/DATA_MANAGER.md](docs/DATA_MANAGER.md)** - DataManager API
- **[docs/archive/](docs/archive/)** - Historical documents

---

## 🎯 Next Steps

1. **Start system**: `./start_cli.sh` → `system start`
2. **Import data**: `data import-api AAPL 30`
3. **View session**: `data session`
4. **Check docs**: Review [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
5. **Write tests**: Add tests in `tests/`

---

## 📄 License

MIT License

---

## 🤝 Support

For issues and questions:
1. Check [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. Review code patterns and examples
3. Create an issue with details

---

**Built with ❤️ for high-performance day trading**
