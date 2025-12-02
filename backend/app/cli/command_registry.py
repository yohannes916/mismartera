from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass(frozen=True)
class CommandMeta:
    """Metadata for a CLI command.

    This is the single source of truth for:
    - usage string
    - short description
    - examples
    - completion hints (symbol positions, enum args)
    """

    name: str  # subcommand name, e.g. "bars"
    usage: str  # full usage line, e.g. "data bars <symbol> <start> <end>"
    description: str
    examples: List[str]
    suggests_symbols_at: Optional[int] = None  # index of arg that is a symbol
    enum_args: Dict[str, List[str]] | None = None  # arg name -> allowed values


# Alias for backward compatibility
DataCommandMeta = CommandMeta


DATA_COMMANDS: List[DataCommandMeta] = [
    DataCommandMeta(
        name="list",
        usage="data list",
        description="List all symbols in database (1m bars, daily bars, ticks, quotes)",
        examples=["data list"],
    ),
    DataCommandMeta(
        name="info",
        usage="data info <symbol>",
        description="Show data info for symbol",
        examples=["data info AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="quality",
        usage="data quality <symbol>",
        description="Check data quality for symbol",
        examples=["data quality AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="delete",
        usage="data delete <symbol>",
        description="Delete all data for symbol",
        examples=["data delete AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="delete-all",
        usage="data delete-all",
        description="Delete ALL data (dangerous)",
        examples=["data delete-all"],
    ),
    DataCommandMeta(
        name="api",
        usage="data api <provider>",
        description="Select data API provider (alpaca, schwab, etc)",
        examples=["data api alpaca"],
    ),
    DataCommandMeta(
        name="import-api",
        usage="data import-api <type> <symbol> <start> <end>",
        description="Import data from external API via DataManager (1m, tick, quote)",
        examples=["data import-api 1m AAPL 2025-11-01 2025-11-19"],
        suggests_symbols_at=2,
    ),
    DataCommandMeta(
        name="import-file",
        usage="data import-file <file> <symbol> \[start] \[end]",
        description="Import CSV data with optional date range (YYYY-MM-DD)",
        examples=["data import-file data/aapl.csv AAPL"],
        suggests_symbols_at=2,
    ),
    DataCommandMeta(
        name="backtest-window",
        usage="data backtest-window <start> \[end]",
        description="Set backtest window dates (YYYY-MM-DD)",
        examples=["data backtest-window 2025-11-04 2025-11-19"],
    ),
    DataCommandMeta(
        name="backtest-speed",
        usage="data backtest-speed <multiplier>",
        description="Set backtest speed multiplier (0=max, 1.0=realtime, 2.0=2x, 0.5=half)",
        examples=["data backtest-speed 0", "data backtest-speed 1.0", "data backtest-speed 2.0"],
    ),
    DataCommandMeta(
        name="export-csv",
        usage="data export-csv <type> <symbol> <start> \[end] -f <file>",
        description="Export bars/ticks/quotes to CSV",
        examples=["data export-csv bar AAPL 2025-11-04 -f aapl.csv"],
        suggests_symbols_at=2,
    ),
    DataCommandMeta(
        name="bars",
        usage="data bars <symbol> <start> <end>",
        description="Show bars from DB (no API calls)",
        examples=["data bars AAPL 2025-11-04 2025-11-04"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="ticks",
        usage="data ticks <symbol> <start> <end>",
        description="Show ticks from DB",
        examples=["data ticks AAPL 2025-11-04 2025-11-04"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="quotes",
        usage="data quotes <symbol> <start> <end>",
        description="Show quotes from DB",
        examples=["data quotes AAPL 2025-11-04 2025-11-04"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="latest-bar",
        usage="data latest-bar <symbol>",
        description="Show latest bar for symbol",
        examples=["data latest-bar AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="latest-tick",
        usage="data latest-tick <symbol>",
        description="Show latest tick for symbol",
        examples=["data latest-tick AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="latest-quote",
        usage="data latest-quote <symbol>",
        description="Show latest bid/ask quote for a symbol",
        examples=["data latest-quote AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="session",
        usage="data session [refresh_seconds] [csv_file] [--duration/-d <seconds>] [--no-live]",
        description="Display live session data with auto-refresh and CSV export (default: 1s, exports to validation/test_session.csv)",
        examples=[
            "data session",
            "data session 5",
            "data session 1 my_output.csv",
            "data session --duration 390",
            "data session --duration 390 --no-live"
        ],
    ),
    DataCommandMeta(
        name="validate",
        usage="data validate [csv_file] [--config <config_file>] [--db-check]",
        description="Validate session data CSV dump (default: validation/test_session.csv vs session_configs/example_session.json)",
        examples=[
            "data validate",
            "data validate mytest.csv",
            "data validate --config session_configs/my_session.json",
            "data validate mytest.csv --config my_config.json --db-check"
        ],
    ),
    DataCommandMeta(
        name="stream-bars",
        usage="data stream-bars <interval> <symbol> \[file]",
        description="Start streaming bars to a CSV file (live: API, backtest: DB)",
        examples=["data stream-bars 1m AAPL"],
        suggests_symbols_at=2,
    ),
    DataCommandMeta(
        name="stream-ticks",
        usage="data stream-ticks <symbol> \[file]",
        description="Start streaming ticks to a CSV file",
        examples=["data stream-ticks AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="stream-quotes",
        usage="data stream-quotes <symbol> \[file]",
        description="Start streaming quotes to a CSV file",
        examples=["data stream-quotes AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="stop-stream-bars",
        usage="data stop-stream-bars \[id]",
        description="Stop an active bar stream (or all if id omitted)",
        examples=["data stop-stream-bars"],
    ),
    DataCommandMeta(
        name="stop-stream-ticks",
        usage="data stop-stream-ticks \[id]",
        description="Stop an active tick stream (or all if id omitted)",
        examples=["data stop-stream-ticks"],
    ),
    DataCommandMeta(
        name="stop-stream-quotes",
        usage="data stop-stream-quotes \[id]",
        description="Stop an active quote stream (or all if id omitted)",
        examples=["data stop-stream-quotes"],
    ),
    DataCommandMeta(
        name="stop-all-streams",
        usage="data stop-all-streams",
        description="Stop ALL active streams (bars, ticks, quotes) and coordinator worker",
        examples=["data stop-all-streams"],
    ),
    DataCommandMeta(
        name="snapshot",
        usage="data snapshot <symbol>",
        description="Get latest snapshot (live mode only) - trade, quote, bars",
        examples=["data snapshot AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="session-volume",
        usage="data session-volume <symbol>",
        description="Get cumulative volume for current trading session",
        examples=["data session-volume AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="session-high-low",
        usage="data session-high-low <symbol>",
        description="Get session high and low prices for current session",
        examples=["data session-high-low AAPL"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="avg-volume",
        usage="data avg-volume <symbol> <days>",
        description="Get average daily volume over specified trading days",
        examples=["data avg-volume AAPL 20"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="high-low",
        usage="data high-low <symbol> <days>",
        description="Get historical high/low prices over specified period",
        examples=["data high-low AAPL 252"],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="add-symbol",
        usage="data add-symbol <symbol> [--streams <streams>]",
        description="Add a symbol dynamically to the active session (backtest or live)",
        examples=[
            "data add-symbol TSLA",
            "data add-symbol MSFT --streams 1m,5m"
        ],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="remove-symbol",
        usage="data remove-symbol <symbol> [--immediate]",
        description="Remove a symbol from the active session",
        examples=[
            "data remove-symbol TSLA",
            "data remove-symbol MSFT --immediate"
        ],
        suggests_symbols_at=1,
    ),
    DataCommandMeta(
        name="list-dynamic",
        usage="data list-dynamic",
        description="List all dynamically added symbols in the active session",
        examples=["data list-dynamic"],
    ),
]


@dataclass(frozen=True)
class MarketCommandMeta:
    name: str
    usage: str
    description: str
    examples: List[str]


MARKET_COMMANDS: List[MarketCommandMeta] = [
    MarketCommandMeta(
        name="status",
        usage="market status",
        description="Check market hours and open/closed state",
        examples=["market status"],
    ),
]


@dataclass(frozen=True)
class SystemCommandMeta:
    name: str
    usage: str
    description: str
    examples: List[str]


SYSTEM_COMMANDS: List[SystemCommandMeta] = [
    SystemCommandMeta(
        name="start",
        usage="system start [config_file]",
        description="Start the system run (defaults to example_session.json)",
        examples=["system start", "system start session_configs/my_config.json"],
    ),
    SystemCommandMeta(
        name="pause",
        usage="system pause",
        description="Pause the system run",
        examples=["system pause"],
    ),
    SystemCommandMeta(
        name="resume",
        usage="system resume",
        description="Resume the system from paused state",
        examples=["system resume"],
    ),
    SystemCommandMeta(
        name="stop",
        usage="system stop",
        description="Stop the system run",
        examples=["system stop"],
    ),
    SystemCommandMeta(
        name="mode",
        usage="system mode <live|backtest>",
        description="Set operation mode (must be stopped)",
        examples=["system mode backtest", "system mode live"],
    ),
    SystemCommandMeta(
        name="status",
        usage="system status",
        description="Show current system status",
        examples=["system status"],
    ),
]


@dataclass(frozen=True)
class GeneralCommandMeta:
    """Metadata for general CLI commands."""
    name: str
    usage: str
    description: str
    examples: List[str]


GENERAL_COMMANDS: List[GeneralCommandMeta] = [
    GeneralCommandMeta(
        name="help",
        usage="help [namespace] [command]",
        description="Show help - all commands, specific namespace, or detailed command info",
        examples=["help", "help data", "help time holidays import", "help data import-api"],
    ),
    GeneralCommandMeta(
        name="history",
        usage="history [n]",
        description="Show command history (last n commands, default 50)",
        examples=["history", "history 20"],
    ),
    GeneralCommandMeta(
        name="run",
        usage="run <script>",
        description="Execute commands from a script file",
        examples=["run startup_script.txt", "run ~/scripts/backtest.txt"],
    ),
    GeneralCommandMeta(
        name="delay",
        usage="delay <milliseconds>",
        description="Pause execution for specified milliseconds",
        examples=["delay 1000", "delay 500", "delay 2500"],
    ),
    GeneralCommandMeta(
        name="status",
        usage="status",
        description="Show application status",
        examples=["status"],
    ),
    GeneralCommandMeta(
        name="clear",
        usage="clear",
        description="Clear the screen",
        examples=["clear"],
    ),
    GeneralCommandMeta(
        name="whoami",
        usage="whoami",
        description="Show current user information",
        examples=["whoami"],
    ),
    GeneralCommandMeta(
        name="logout",
        usage="logout",
        description="Logout and exit",
        examples=["logout"],
    ),
    GeneralCommandMeta(
        name="exit",
        usage="exit",
        description="Exit the application",
        examples=["exit"],
    ),
    GeneralCommandMeta(
        name="quit",
        usage="quit",
        description="Exit the application",
        examples=["quit"],
    ),
]


@dataclass(frozen=True)
class AdminCommandMeta:
    """Metadata for admin-only commands."""
    name: str
    usage: str
    description: str
    examples: List[str]
    admin_only: bool = True


ADMIN_COMMANDS: List[AdminCommandMeta] = [
    AdminCommandMeta(
        name="log-level",
        usage="log-level <level>",
        description="Change log level (DEBUG, INFO, WARNING, ERROR)",
        examples=["log-level DEBUG", "log-level INFO"],
    ),
    AdminCommandMeta(
        name="log-level-get",
        usage="log-level-get",
        description="Get current log level",
        examples=["log-level-get"],
    ),
    AdminCommandMeta(
        name="sessions",
        usage="sessions",
        description="List active sessions (admin only)",
        examples=["sessions"],
    ),
]


@dataclass(frozen=True)
class ClaudeCommandMeta:
    """Metadata for Claude AI integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]


CLAUDE_COMMANDS: List[ClaudeCommandMeta] = [
    ClaudeCommandMeta(
        name="ask",
        usage="ask <question>",
        description="Ask Claude a question",
        examples=["ask What is the current market trend?", "ask Explain options trading"],
    ),
    ClaudeCommandMeta(
        name="analyze",
        usage="analyze <symbol>",
        description="Analyze a stock with Claude AI",
        examples=["analyze AAPL", "analyze TSLA"],
    ),
    ClaudeCommandMeta(
        name="status",
        usage="claude status",
        description="Check Claude API configuration",
        examples=["claude status"],
    ),
    ClaudeCommandMeta(
        name="usage",
        usage="claude usage",
        description="View your Claude API usage and costs",
        examples=["claude usage"],
    ),
    ClaudeCommandMeta(
        name="history",
        usage="claude history",
        description="View recent Claude API usage history",
        examples=["claude history"],
    ),
]


@dataclass(frozen=True)
class AlpacaCommandMeta:
    """Metadata for Alpaca integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]


ALPACA_COMMANDS: List[AlpacaCommandMeta] = [
    AlpacaCommandMeta(
        name="connect",
        usage="alpaca connect",
        description="Test Alpaca API connectivity",
        examples=["alpaca connect"],
    ),
    AlpacaCommandMeta(
        name="disconnect",
        usage="alpaca disconnect",
        description="Show how to logically disconnect Alpaca",
        examples=["alpaca disconnect"],
    ),
]


# ============================================================================
# SCHWAB COMMANDS
# ============================================================================

@dataclass(frozen=True)
class SchwabCommandMeta:
    """Metadata for Charles Schwab integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]


SCHWAB_COMMANDS: List[SchwabCommandMeta] = [
    SchwabCommandMeta(
        name="connect",
        usage="schwab connect",
        description="Test Charles Schwab API connectivity",
        examples=["schwab connect"],
    ),
    SchwabCommandMeta(
        name="auth-start",
        usage="schwab auth-start",
        description="Start OAuth 2.0 authorization flow",
        examples=["schwab auth-start"],
    ),
    SchwabCommandMeta(
        name="auth-callback",
        usage="schwab auth-callback <code>",
        description="Complete OAuth flow with authorization code",
        examples=["schwab auth-callback ABC123..."],
    ),
    SchwabCommandMeta(
        name="auth-status",
        usage="schwab auth-status",
        description="Show OAuth authentication status",
        examples=["schwab auth-status"],
    ),
    SchwabCommandMeta(
        name="auth-logout",
        usage="schwab auth-logout",
        description="Clear Schwab OAuth tokens",
        examples=["schwab auth-logout"],
    ),
    SchwabCommandMeta(
        name="disconnect",
        usage="schwab disconnect",
        description="Show how to logically disconnect Schwab",
        examples=["schwab disconnect"],
    ),
]


# ============================================================================
# EXECUTION COMMANDS
# ============================================================================

@dataclass(frozen=True)
class ExecutionCommandMeta:
    """Metadata for execution/trading commands."""
    name: str
    usage: str
    description: str
    examples: List[str]


EXECUTION_COMMANDS: List[ExecutionCommandMeta] = [
    ExecutionCommandMeta(
        name="api",
        usage="execution api <provider>",
        description="Select execution/trading API provider (alpaca, schwab, mismartera)",
        examples=["execution api alpaca", "execution api schwab", "execution api mismartera"],
    ),
    ExecutionCommandMeta(
        name="balance",
        usage="execution balance [--account <id>] [--no-sync]",
        description="Show account balance information",
        examples=["execution balance", "execution balance --no-sync"],
    ),
    ExecutionCommandMeta(
        name="positions",
        usage="execution positions [--account <id>] [--no-sync]",
        description="Show current positions",
        examples=["execution positions", "execution positions --no-sync"],
    ),
    ExecutionCommandMeta(
        name="orders",
        usage="execution orders [--status <status>] [--days <n>]",
        description="Show order history",
        examples=["execution orders", "execution orders --status FILLED --days 7"],
    ),
    ExecutionCommandMeta(
        name="order",
        usage="execution order <symbol> <quantity> [--side BUY|SELL] [--type MARKET|LIMIT] [--price <price>]",
        description="Place a new order",
        examples=["execution order AAPL 100 --side BUY", "execution order TSLA 50 --type LIMIT --price 250.50"],
    ),
    ExecutionCommandMeta(
        name="cancel",
        usage="execution cancel <order_id>",
        description="Cancel an order",
        examples=["execution cancel ORD_123ABC"],
    ),
]


# Time Manager Commands
TimeCommandMeta = CommandMeta

TIME_COMMANDS: List[TimeCommandMeta] = [
    TimeCommandMeta(
        name="current",
        usage="time current [--timezone <tz>]",
        description="Get current system time (live or backtest mode)",
        examples=["time current", "time current --timezone UTC", "time current --timezone Asia/Tokyo"],
    ),
    TimeCommandMeta(
        name="market",
        usage="time market [--exchange <exch>] [--extended]",
        description="Check if market is currently open",
        examples=["time market", "time market --exchange NASDAQ", "time market --extended"],
    ),
    TimeCommandMeta(
        name="session",
        usage="time session [<date>] [--exchange <exch>]",
        description="Get trading session information for a date",
        examples=["time session", "time session 2024-11-25", "time session 2024-12-25 --exchange NASDAQ"],
    ),
    TimeCommandMeta(
        name="next",
        usage="time next [<from_date>] [--n <count>] [--exchange <exch>]",
        description="Get the next N trading dates",
        examples=["time next", "time next 2024-11-27", "time next 2024-11-27 --n 5"],
    ),
    TimeCommandMeta(
        name="days",
        usage="time days <start_date> <end_date> [--exchange <exch>]",
        description="Count trading days in a date range",
        examples=["time days 2024-11-01 2024-11-30", "time days 2024-01-01 2024-12-31 --exchange NASDAQ"],
    ),
    TimeCommandMeta(
        name="holidays",
        usage="time holidays [--year <year>] [--exchange <exch>]",
        description="List holidays for a year",
        examples=["time holidays", "time holidays --year 2024", "time holidays --year 2025 --exchange NASDAQ"],
    ),
    TimeCommandMeta(
        name="convert",
        usage="time convert <datetime> <from_tz> <to_tz>",
        description="Convert datetime between timezones",
        examples=[
            'time convert "2024-11-25 10:30:00" America/New_York UTC',
            'time convert "2024-11-25 15:30:00" UTC Asia/Tokyo'
        ],
    ),
    TimeCommandMeta(
        name="holidays import",
        usage="time holidays import <file> [--exchange <group>] [--dry-run]",
        description="Import holidays from JSON/CSV file (auto-uses configured exchange's group)",
        examples=[
            "time holidays import data/holidays/us_equity_2024.json",
            "time holidays import holidays.csv --exchange US_EQUITY",
            "time holidays import holidays.json --dry-run"
        ],
    ),
    TimeCommandMeta(
        name="list-groups",
        usage="time list-groups",
        description="List all available exchange groups for holiday management",
        examples=["time list-groups"],
    ),
    TimeCommandMeta(
        name="backtest-window",
        usage="time backtest-window <start> \[end]",
        description="Set backtest window dates (YYYY-MM-DD)",
        examples=["time backtest-window 2024-11-01 2024-11-30", "time backtest-window 2024-11-01"],
    ),
    TimeCommandMeta(
        name="advance",
        usage="time advance [--extended] [--exchange <exch>]",
        description="Advance backtest time to next market opening (backtest mode only)",
        examples=["time advance", "time advance --extended", "time advance --exchange NASDAQ"],
    ),
    TimeCommandMeta(
        name="reset",
        usage="time reset [--extended]",
        description="Reset backtest time to window start (backtest mode only)",
        examples=["time reset", "time reset --extended"],
    ),
    TimeCommandMeta(
        name="config",
        usage="time config",
        description="Show current configuration (exchange, window, mode)",
        examples=["time config"],
    ),
    TimeCommandMeta(
        name="exchange",
        usage="time exchange <exchange> [asset_class]",
        description="Set primary exchange for all time/calendar operations (live and backtest)",
        examples=["time exchange NYSE", "time exchange NASDAQ EQUITY"],
    ),
    TimeCommandMeta(
        name="holidays delete",
        usage="time holidays delete <year> [--exchange <exch>]",
        description="Delete holidays for a specific year and exchange (uses primary exchange if not specified)",
        examples=["time holidays delete 2024", "time holidays delete 2025 --exchange NASDAQ"],
    ),
]
