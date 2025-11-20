# MisMartera Trading Backend

A high-performance day trading application backend with **strict layered architecture**, Charles Schwab API integration, and Claude AI analysis engine.

## Features

- 🏗️ **Layered Architecture** - Three top-level modules with strict API boundaries
- 🚀 **FastAPI REST API** - High-performance async API server
- 💻 **Rich CLI Interface** - Beautiful command-line interface with Typer and Rich
- 📊 **Charles Schwab Integration** - Trade execution and market data
- 🤖 **Claude AI Analysis** - AI-powered trading insights using Claude Opus 4.1
- 📝 **Dynamic Logging** - Runtime log level control via API or CLI
- 💾 **SQLite Database** - Local data persistence
- 🔄 **Backtest Support** - Full backtesting capabilities with historical data
- 📈 **Analysis Logging** - Comprehensive logging of all decisions and LLM interactions

## Architecture

MisMartera uses a **strictly layered architecture** with three core top-level modules:

- **📊 DataManager** - Single source of truth for all data (time, bars, ticks, holidays)
- **📈 ExecutionManager** - All order execution and account management
- **🧠 AnalysisEngine** - AI-powered trading analysis and decision making

**Key Principle:** CLI and API routes must **only** interact with these top-level module APIs. Direct database or integration access is strictly forbidden.

### High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│          CLI / REST API (Client Layer)         │
└────────────────┬────────────────────────────────┘
                 │ API Calls Only
                 ▼
┌─────────────────────────────────────────────────┐
│  📊 DataManager  │ 📈 ExecutionMgr │ 🧠 Analysis │
│                  │                 │    Engine   │
└────────────────┬─────────┬─────────┬────────────┘
                 │         │         │
                 ▼         ▼         ▼
┌─────────────────────────────────────────────────┐
│  Repositories, Integrations, Databases          │
└─────────────────────────────────────────────────┘
```

📖 **See [ARCHITECTURE.md](ARCHITECTURE.md) for comprehensive architecture documentation.**

## Project Structure

```
backend/
├── app/
│   ├── managers/          # 🔥 Top-level Modules (NEW)
│   │   ├── data_manager/       # DataManager module
│   │   ├── execution_manager/  # ExecutionManager module
│   │   └── analysis_engine/    # AnalysisEngine module
│   ├── api/              # REST API endpoints
│   ├── cli/              # CLI commands
│   ├── models/           # Database models
│   ├── services/         # Shared services (auth, etc.)
│   └── utils/            # Utilities
├── data/                 # Database and logs
├── run_api.py           # Start API server
├── run_cli.py           # Start CLI
├── ARCHITECTURE.md       # Architecture documentation
└── requirements.txt      # Dependencies
```

## Installation

> **Note:** This backend uses an embedded Python environment that is fully isolated from your system Python. See [EMBEDDED_PYTHON.md](EMBEDDED_PYTHON.md) for detailed information.

### 1. Setup Embedded Python Environment

```bash
cd backend
make setup
```

This will download a standalone Python build, create a virtual environment, and install all dependencies. Takes 2-3 minutes on first run.

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your API credentials:

```env
# Required for trading
SCHWAB_APP_KEY=your_schwab_app_key
SCHWAB_APP_SECRET=your_schwab_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/callback

# Required for AI analysis
ANTHROPIC_API_KEY=your_anthropic_api_key

# Security
SECRET_KEY=generate-a-secure-random-key-here
```

### 3. Initialize Database

```bash
make run-cli ARGS="init-db"
```

## Usage

### Start API Server

```bash
# Using Makefile (recommended)
make run-api

# Or using launcher script
./start_api.sh

# Or manually with embedded environment
source .venv/bin/activate
python run_api.py
```

The API will be available at:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### CLI Commands

#### Admin Commands

```bash
# Change log level
python run_cli.py admin log-level DEBUG

# Get current log level
python run_cli.py admin log-level-get

# Check API server status
python run_cli.py admin api-status
```

#### Account Commands

```bash
# View account balance
python run_cli.py account balance

# View positions
python run_cli.py account positions

# View account info
python run_cli.py account info
```

#### Execution Commands

```bash
# Place market order
python run_cli.py execution order AAPL 10 --side BUY

# Place limit order
python run_cli.py execution order TSLA 5 --side BUY --type LIMIT --price 250.00

# List orders
python run_cli.py execution orders --status FILLED --limit 20

# Cancel order
python run_cli.py execution cancel ORDER_123
```

#### Data Commands

```bash
# Get quotes
python run_cli.py data quote AAPL TSLA NVDA

# Get historical data
python run_cli.py data history MSFT --days 30 --interval 1d

# Stream real-time quotes
python run_cli.py data stream AAPL GOOGL
```

#### Analysis Commands

```bash
# Analyze single stock
python run_cli.py analysis analyze AAPL --type technical

# Scan market
python run_cli.py analysis scan --symbols AAPL,TSLA,NVDA --strategy momentum

# Test strategy
python run_cli.py analysis strategy my-strategy --symbol AAPL --days 30
```

#### System Commands

```bash
# Show version
python run_cli.py --version

# Show status
python run_cli.py status

# Start server
python run_cli.py server
```

## API Endpoints

### Admin Endpoints

- `POST /api/admin/log-level` - Change log level at runtime
- `GET /api/admin/log-level` - Get current log level
- `GET /api/admin/status` - Get system status

### Account Endpoints (Coming Soon)

- `GET /api/account/balance` - Get account balance
- `GET /api/account/positions` - Get current positions
- `GET /api/account/info` - Get account information

### Execution Endpoints (Coming Soon)

- `POST /api/execution/order` - Place order
- `GET /api/execution/orders` - List orders
- `DELETE /api/execution/order/{id}` - Cancel order
- `GET /api/execution/positions` - Get positions

### Data Endpoints (Coming Soon)

- `GET /api/data/quote/{symbol}` - Get quote
- `GET /api/data/history/{symbol}` - Get historical data
- `WS /api/data/stream` - WebSocket streaming

### Analysis Endpoints (Coming Soon)

- `POST /api/analysis/analyze` - Analyze stock with AI
- `POST /api/analysis/scan` - Scan market
- `GET /api/analysis/history` - Get analysis history

## Development

### Change Log Level (Runtime)

Via API:
```bash
curl -X POST http://localhost:8000/api/admin/log-level \
  -H "Content-Type: application/json" \
  -d '{"level": "DEBUG"}'
```

Via CLI:
```bash
python run_cli.py admin log-level DEBUG
```

### Database Models

The application uses SQLAlchemy with async SQLite:

- `User` - User accounts
- `AccountInfo` - Schwab account data
- `Position` - Current positions
- `Order` - Order history
- `MarketData` - OHLCV data
- `Analysis` - AI analysis results

### Adding New Features

1. **Add API Endpoint**: Create route in `app/api/routes/`
2. **Add CLI Command**: Create command in `app/cli/commands/`
3. **Add Business Logic**: Create service in `app/services/`
4. **Add Database Model**: Add to `app/models/schemas.py`

## Architecture

### Modules

1. **Account Module**: Authentication, balance, account info
2. **Execution Module**: Order placement, position management
3. **Data Module**: Historical data, real-time quotes, WebSocket streaming
4. **Analysis Engine**: Claude AI integration for trading insights

### Technology Stack

- **FastAPI** - Modern async web framework
- **SQLAlchemy** - ORM with async support
- **Typer** - CLI framework
- **Rich** - Beautiful terminal output
- **Loguru** - Advanced logging
- **Pandas** - Data processing
- **HTTPX** - Async HTTP client

## Logging

Logs are stored in `data/logs/app.log` with:
- Automatic rotation (10 MB)
- Retention (30 days)
- Compression (zip)

Console output includes:
- Colored log levels
- Timestamps
- Function names and line numbers
- Backtrace on errors

## Security

- JWT tokens for authentication (when implemented)
- Environment variables for secrets
- No hardcoded credentials
- CORS configured for Electron app

## Troubleshooting

### API Not Starting

```bash
# Check if port 8000 is available
lsof -i :8000

# Try different port
python run_cli.py server --port 8001
```

### Database Issues

```bash
# Recreate database
rm data/trading_app.db
python run_cli.py init-db
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Next Steps

1. **Configure Schwab API** - Add credentials to `.env`
2. **Configure Claude API** - Add ANTHROPIC_API_KEY to `.env`
3. **Test API Server** - Visit http://localhost:8000/docs
4. **Test CLI** - Run `python run_cli.py --help`
5. **Implement Services** - Add actual Schwab and Claude integration

## License

MIT License

## Support

For issues and questions, please check the documentation or create an issue.
