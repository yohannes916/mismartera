"""
Interactive CLI REPL
Provides a session-based interactive command interface
"""
import sys
import os
import atexit
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box
from rich.text import Text
import getpass
import asyncio

# Command history support
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

from app.config import settings
from app.logger import logger
from app.services.auth_service import auth_service
from app.integrations.claude_client import claude_client
from app.integrations import alpaca_client
from app.services.claude_usage_tracker import usage_tracker
from app.models.database import AsyncSessionLocal
from app.services.csv_import_service import csv_import_service
from app.repositories.market_data_repository import MarketDataRepository


class CommandCompleter:
    """
    Smart tab completion for interactive CLI commands
    """
    
    def __init__(self):
        # Main commands
        self.commands = [
            'help', 'status', 'exit', 'logout', 'history',
            'data', 'list', 'info', 'quality', 'delete',
            'claude', 'ask', 'analyze', 'usage', 'llm-history',
            'alpaca',  # Alpaca integration commands
        ]
        
        # Subcommands by context
        self.data_commands = [
            'import-file', 'list', 'info', 'quality', 'delete', 'delete-all',
            'mode', 'api', 'import-api',
        ]
        self.claude_commands = ['ask', 'analyze', 'status', 'usage', 'llm-history']
        
        # Cache for symbols (loaded on first use)
        self.cached_symbols = []
    
    def get_symbols(self):
        """Get list of symbols from database (cached)"""
        if not self.cached_symbols:
            try:
                # This will be populated by the CLI when logged in
                import asyncio
                from app.managers import DataManager
                from app.models.database import AsyncSessionLocal
                
                async def _fetch():
                    data_manager = DataManager(mode="real")
                    async with AsyncSessionLocal() as session:
                        return await data_manager.get_symbols(session)
                
                self.cached_symbols = asyncio.run(_fetch())
            except Exception:
                # If we can't fetch, use empty list
                self.cached_symbols = []
        
        return self.cached_symbols
    
    def refresh_symbols(self):
        """Clear symbol cache to force refresh"""
        self.cached_symbols = []
    
    def complete(self, text, state):
        """
        Return the next possible completion for 'text'
        
        Args:
            text: The text to complete
            state: The completion state (0 for first match, 1 for second, etc.)
        """
        try:
            # Get the full line buffer
            line = readline.get_line_buffer()
            words = line.split()
            
            # If nothing typed yet, show main commands
            if not line or not words:
                matches = [cmd + ' ' for cmd in self.commands if cmd.startswith(text)]
            
            # If we're at the first word, complete main commands
            elif len(words) == 1 and not line.endswith(' '):
                matches = [cmd + ' ' for cmd in self.commands if cmd.startswith(text)]
            
            # Context-aware completion based on first word
            elif len(words) >= 1:
                first_word = words[0]
                
                # Data subcommands
                if first_word == 'data':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.data_commands if cmd.startswith(text)]
                    # After 'data info' or 'data quality', suggest symbols
                    elif words[1] in ['info', 'quality', 'analyze'] and len(words) >= 2:
                        symbols = self.get_symbols()
                        matches = [s + ' ' for s in symbols if s.startswith(text.upper())]
                    else:
                        matches = []
                
                # Claude subcommands
                elif first_word in ['claude', 'llm']:
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.claude_commands if cmd.startswith(text)]
                    # After 'claude analyze', suggest symbols
                    elif words[1] == 'analyze' and len(words) >= 2:
                        symbols = self.get_symbols()
                        matches = [s + ' ' for s in symbols if s.startswith(text.upper())]
                    else:
                        matches = []
                
                # Direct analyze command - suggest symbols
                elif first_word == 'analyze':
                    if len(words) >= 1:
                        symbols = self.get_symbols()
                        matches = [s + ' ' for s in symbols if s.startswith(text.upper())]
                    else:
                        matches = []
                
                # Import command - file path completion handled by readline default
                elif first_word == 'alpaca':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = ['connect ', 'disconnect ']  # Alpaca subcommands
                    else:
                        matches = []
                
                # General commands
                else:
                    matches = []
            
            # Return the state'th match
            if state < len(matches):
                return matches[state]
            return None
            
        except Exception as e:
            # Fail silently to not disrupt the user experience
            return None


class InteractiveCLI:
    """
    Interactive command-line interface with authentication
    """
    
    def __init__(self):
        self.console = Console()
        self.session_token: Optional[str] = None
        self.current_user: Optional[dict] = None
        self.running = False
        
        # Set up command history and tab completion
        self.history_file = os.path.expanduser("~/.mismartera_history")
        self.completer = CommandCompleter()
        self._setup_history()
        
    def _setup_history(self):
        """Set up command history and tab completion with readline"""
        if not READLINE_AVAILABLE:
            logger.warning("readline not available - command history and tab completion disabled")
            return
        
        # Set history length
        readline.set_history_length(1000)
        
        # Load existing history
        if os.path.exists(self.history_file):
            try:
                readline.read_history_file(self.history_file)
                logger.debug(f"Loaded command history from {self.history_file}")
            except Exception as e:
                logger.warning(f"Could not load history file: {e}")
        
        # Set up tab completion
        try:
            readline.set_completer(self.completer.complete)
            # Configure tab completion behavior
            # Detect whether we're using libedit or GNU readline and bind Tab appropriately
            doc = getattr(readline, "__doc__", "") or ""
            if "libedit" in doc.lower():
                # macOS / libedit style
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                # GNU readline style
                readline.parse_and_bind("tab: complete")
            # Set completer delimiters (what separates words)
            readline.set_completer_delims(' \t\n')
            logger.debug("Tab completion enabled")
        except Exception as e:
            logger.warning(f"Could not set up tab completion: {e}")
        
        # Save history on exit
        atexit.register(self._save_history)
    
    def _save_history(self):
        """Save command history to file"""
        if not READLINE_AVAILABLE:
            return
        
        try:
            readline.write_history_file(self.history_file)
            logger.debug(f"Saved command history to {self.history_file}")
        except Exception as e:
            logger.warning(f"Could not save history file: {e}")
    
    def display_banner(self):
        """Display welcome banner"""
        banner = Text()
        banner.append("╔══════════════════════════════════════════════════╗\n", style="cyan bold")
        banner.append("║                                                  ║\n", style="cyan bold")
        banner.append("║                    ", style="cyan bold")
        banner.append("MISMARTERA", style="yellow bold")
        banner.append("                    ║\n", style="cyan bold")
        banner.append("║                                                  ║\n", style="cyan bold")
        banner.append("║           ", style="cyan bold")
        banner.append("Interactive Trading Terminal", style="green")
        banner.append("           ║\n", style="cyan bold")
        banner.append("║                                                  ║\n", style="cyan bold")
        banner.append("╚══════════════════════════════════════════════════╝", style="cyan bold")
        
        self.console.print(banner)
        
        history_status = "[green]✓[/green]" if READLINE_AVAILABLE else "[dim]✗[/dim]"
        self.console.print(
            f"\n[dim]Version {settings.APP_VERSION} | Paper Trading: {settings.PAPER_TRADING} | "
            f"History: {history_status}[/dim]\n"
        )
        
    async def login(self) -> bool:
        """
        Prompt for login credentials
        
        Returns:
            True if login successful, False otherwise
        """
        self.console.print("[yellow]Please login to continue[/yellow]\n")
        
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                username = Prompt.ask("[cyan]Username[/cyan]")
                password = getpass.getpass("Password: ")
                
                # Authenticate with database
                async with AsyncSessionLocal() as db_session:
                    self.session_token = await auth_service.login(username, password, db_session)
                
                if self.session_token:
                    self.current_user = auth_service.get_current_user(self.session_token)
                    self.console.print(f"\n[green]✓[/green] Welcome, [bold]{self.current_user['username']}[/bold]!")
                    self.console.print(f"[dim]Role: {self.current_user.get('role', 'user')}[/dim]\n")
                    logger.info(f"User logged in: {username}")
                    return True
                else:
                    attempts += 1
                    remaining = max_attempts - attempts
                    if remaining > 0:
                        self.console.print(f"[red]✗[/red] Invalid credentials. {remaining} attempts remaining.\n")
                    else:
                        self.console.print("[red]✗[/red] Maximum login attempts exceeded.\n")
                        
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Login cancelled[/yellow]")
                return False
            except Exception as e:
                logger.error(f"Login error: {e}")
                self.console.print(f"[red]Login error: {e}[/red]")
                
        return False
    
    def logout(self):
        """Logout current user"""
        if self.session_token:
            auth_service.logout(self.session_token)
            username = self.current_user.get('username', 'unknown') if self.current_user else 'unknown'
            self.console.print(f"\n[yellow]Goodbye, {username}![/yellow]")
            logger.info(f"User logged out: {username}")
            self.session_token = None
            self.current_user = None
    
    def show_help(self):
        """Display available commands"""
        table = Table(title="Available Commands", box=box.ROUNDED)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        
        # General commands
        table.add_row("help", "Show this help message")
        table.add_row("history [n]", "Show command history (last n commands, default 50)")
        table.add_row("status", "Show application status")
        table.add_row("clear", "Clear the screen")
        table.add_row("whoami", "Show current user information")
        table.add_row("logout", "Logout and exit")
        table.add_row("exit", "Exit the application")
        table.add_row("quit", "Exit the application")
        
        # Admin commands
        table.add_section()
        table.add_row("[bold cyan]ADMIN COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("log-level <level>", "Change log level (DEBUG, INFO, WARNING, ERROR)")
        table.add_row("log-level-get", "Get current log level")
        table.add_row("sessions", "List active sessions (admin only)")
        
        # Account commands
        table.add_section()
        table.add_row("[bold cyan]ACCOUNT COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("account info", "Display account information")
        table.add_row("account balance", "Display account balance")
        table.add_row("account positions", "Display current positions")
        
        # Trading commands
        table.add_section()
        table.add_row("[bold cyan]TRADING COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("quote <symbol>", "Get real-time quote")
        table.add_row("buy <symbol> <qty>", "Place buy order")
        table.add_row("sell <symbol> <qty>", "Place sell order")
        table.add_row("orders", "View order history")
        
        # Data commands
        table.add_section()
        table.add_row("[bold cyan]DATA COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("data list", "List all symbols in database")
        table.add_row("data info <symbol>", "Show data info for symbol")
        table.add_row("data quality <symbol>", "Check data quality for symbol")
        table.add_row("data delete <symbol>", "Delete all data for symbol ⚠️")
        table.add_row("data delete-all", "Delete ALL data ⚠️")
        table.add_row("data mode <realtime|backtest>", "Set DataManager operating mode")
        table.add_row("data api <provider>", "Select data API provider (alpaca, schwab, etc)")
        table.add_row("data import-api <type> <symbol> <start> <end>", "Import data from external API via DataManager")
        table.add_row("data import-file <file> <symbol> \\[start] \\[end]", "Import CSV data with optional date range (YYYY-MM-DD)")
        table.add_row("holidays import <file>", "Import market holiday schedule")
        table.add_row("holidays list [YYYY]", "List market holidays for year YYYY")
        table.add_row("holidays delete [YYYY]", "Delete market holidays for year YYYY")
        table.add_row("market status", "Check market hours")
        
        # Claude AI commands
        table.add_section()
        table.add_row("[bold cyan]CLAUDE AI COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("ask <question>", "Ask Claude a question")
        table.add_row("analyze <symbol>", "Analyze a stock with Claude AI")
        table.add_row("claude status", "Check Claude API configuration")
        table.add_row("claude usage", "View your Claude API usage and costs")
        table.add_row("claude history", "View recent Claude API usage history")
        
        # Alpaca integration commands
        table.add_section()
        table.add_row("[bold cyan]ALPACA COMMANDS[/bold cyan]", "", style="cyan")
        table.add_row("alpaca connect", "Test Alpaca API connectivity")
        table.add_row("alpaca disconnect", "Show how to logically disconnect Alpaca")
        
        self.console.print(table)
    
    def show_status(self):
        """Show application status"""
        from rich.table import Table
        
        table = Table(title="System Status", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Application", settings.APP_NAME)
        table.add_row("Version", settings.APP_VERSION)
        table.add_row("User", self.current_user.get('username', 'unknown') if self.current_user else 'Not logged in')
        table.add_row("Role", self.current_user.get('role', 'N/A') if self.current_user else 'N/A')
        table.add_row("Debug Mode", str(settings.DEBUG))
        table.add_row("Paper Trading", str(settings.PAPER_TRADING))
        table.add_row("Log Level", settings.LOG_LEVEL)
        table.add_row("Session Active", str(self.session_token is not None))
        
        self.console.print(table)
    
    def show_history(self, limit: int = 50):
        """Display command history"""
        if not READLINE_AVAILABLE:
            self.console.print("[yellow]Command history not available (readline not installed)[/yellow]")
            return
        
        history_length = readline.get_current_history_length()
        
        if history_length == 0:
            self.console.print("[dim]No command history yet[/dim]")
            return
        
        # Calculate start index
        start = max(1, history_length - limit + 1)
        
        self.console.print(f"\n[cyan]Command History[/cyan] [dim](showing last {min(limit, history_length)} commands)[/dim]\n")
        
        for i in range(start, history_length + 1):
            cmd = readline.get_history_item(i)
            if cmd:
                # Show index and command
                self.console.print(f"[dim]{i:4d}[/dim]  {cmd}")
        
        self.console.print(f"\n[dim]Total commands in history: {history_length}[/dim]")
        self.console.print(f"[dim]History file: {self.history_file}[/dim]\n")
    
    async def execute_command(self, command: str) -> bool:
        """
        Execute a user command
        
        Args:
            command: Command string to execute
            
        Returns:
            True to continue running, False to exit
        """
        if not command.strip():
            return True
        
        parts = command.strip().split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        try:
            # System commands
            if cmd in ['exit', 'quit']:
                if Confirm.ask("\n[yellow]Are you sure you want to exit?[/yellow]"):
                    return False
                return True
            
            # Basic commands
            if cmd == 'help':
                self.show_help()
            
            elif cmd == 'history':
                # Show command history
                limit = int(args[0]) if args and args[0].isdigit() else 50
                self.show_history(limit)
            
            elif cmd == 'status':
                self.show_status()
            
            elif cmd == 'clear':
                self.console.clear()
                self.display_banner()
            
            elif cmd == 'whoami':
                if self.current_user:
                    self.console.print(f"\n[cyan]Username:[/cyan] {self.current_user['username']}")
                    self.console.print(f"[cyan]Role:[/cyan] {self.current_user.get('role', 'user')}")
                    self.console.print(f"[cyan]Email:[/cyan] {self.current_user.get('email', 'N/A')}\n")
                else:
                    self.console.print("[yellow]Not logged in[/yellow]")
            
            elif cmd == 'logout':
                if Confirm.ask("\n[yellow]Are you sure you want to logout?[/yellow]"):
                    return False
                return True
            
            # Admin commands
            elif cmd == 'log-level':
                if args:
                    from app.logger import logger as app_logger
                    level = args[0].upper()
                    app_logger.remove()
                    app_logger.add(sys.stderr, level=level)
                    self.console.print(f"[green]✓[/green] Log level changed to: {level}")
                    logger.success(f"Log level changed to {level}")
                else:
                    self.console.print("[red]Usage: log-level <LEVEL>[/red]")
            
            elif cmd == 'log-level-get':
                self.console.print(f"[cyan]Current log level:[/cyan] {settings.LOG_LEVEL}")
            
            elif cmd == 'sessions':
                if self.current_user and self.current_user.get('role') == 'admin':
                    sessions = auth_service.list_active_sessions()
                    if sessions:
                        table = Table(title="Active Sessions", box=box.ROUNDED)
                        table.add_column("Username", style="cyan")
                        table.add_column("Created", style="green")
                        table.add_column("Last Active", style="yellow")
                        
                        for session in sessions:
                            table.add_row(
                                session['username'],
                                session['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
                                session['last_active'].strftime("%Y-%m-%d %H:%M:%S")
                            )
                        self.console.print(table)
                    else:
                        self.console.print("[yellow]No active sessions[/yellow]")
                else:
                    self.console.print("[red]Admin access required[/red]")
            
            # Account commands
            elif cmd == 'account':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'info':
                        self.console.print("[yellow]Fetching account info...[/yellow]")
                        self.console.print("[dim]Account not connected (API not configured)[/dim]")
                    elif subcmd == 'balance':
                        self.console.print("[yellow]Fetching account balance...[/yellow]")
                        self.console.print("[dim]Account not connected (API not configured)[/dim]")
                    elif subcmd == 'positions':
                        self.console.print("[yellow]Fetching positions...[/yellow]")
                        self.console.print("[dim]No positions found (API not configured)[/dim]")
                    else:
                        self.console.print(f"[red]Unknown account command: {subcmd}[/red]")
                else:
                    self.console.print("[red]Usage: account <info|balance|positions>[/red]")
            
            # Trading commands
            elif cmd == 'quote':
                if args:
                    symbol = args[0].upper()
                    self.console.print(f"[yellow]Fetching quote for {symbol}...[/yellow]")
                    self.console.print("[dim]Market data not available (API not configured)[/dim]")
                else:
                    self.console.print("[red]Usage: quote <SYMBOL>[/red]")
            
            elif cmd in ['buy', 'sell']:
                if len(args) >= 2:
                    symbol = args[0].upper()
                    try:
                        qty = float(args[1])
                        self.console.print(f"[yellow]Placing {cmd.upper()} order: {qty} shares of {symbol}...[/yellow]")
                        if settings.PAPER_TRADING:
                            self.console.print(f"[green]✓[/green] Paper trading order placed: {cmd.upper()} {qty} {symbol}")
                        else:
                            self.console.print("[dim]Trading not available (API not configured)[/dim]")
                    except ValueError:
                        self.console.print("[red]Invalid quantity[/red]")
                else:
                    self.console.print(f"[red]Usage: {cmd} <SYMBOL> <QUANTITY>[/red]")
            
            elif cmd == 'orders':
                self.console.print("[yellow]Fetching order history...[/yellow]")
                self.console.print("[dim]No orders found (API not configured)[/dim]")
            
            # Market commands
            elif cmd == 'market':
                if args and args[0].lower() == 'status':
                    self.console.print("[yellow]Checking market status...[/yellow]")
                    self.console.print("[dim]Market data not available (API not configured)[/dim]")
                else:
                    self.console.print("[red]Usage: market status[/red]")
            
            # (watchlist command removed)
            
            # Holiday calendar commands
            elif cmd == 'holidays':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'import' and len(args) >= 2:
                        file_path = args[1]
                        from app.cli.holiday_commands import import_holidays_command
                        await import_holidays_command(file_path)
                    elif subcmd == 'list':
                        year = int(args[1]) if len(args) >= 2 else None
                        from app.cli.holiday_commands import list_holidays_command
                        await list_holidays_command(year)
                    elif subcmd == 'delete' and len(args) >= 2:
                        year = int(args[1])
                        from app.cli.holiday_commands import delete_holidays_command
                        await delete_holidays_command(year)
                    else:
                        self.console.print("[red]Usage:[/red]")
                        self.console.print("  holidays import <file>    - Import holiday schedule")
                        self.console.print("  holidays list [YYYY]      - List holidays for year YYYY (or all if omitted)")
                        self.console.print("  holidays delete [YYYY]    - Delete holidays for year YYYY")
                else:
                    self.console.print("[red]Usage: holidays <import|list|delete>[/red]")
            
            elif cmd == 'data':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'list':
                        from app.cli.data_commands import list_symbols_command
                        await list_symbols_command()
                    elif subcmd == 'info' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import data_info_command
                        await data_info_command(symbol)
                    elif subcmd == 'quality' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import data_quality_command
                        await data_quality_command(symbol)
                    elif subcmd == 'delete' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import delete_symbol_command
                        await delete_symbol_command(symbol)
                    elif subcmd == 'delete-all':
                        from app.cli.data_commands import delete_all_command
                        await delete_all_command()
                    elif subcmd == 'mode' and len(args) >= 2:
                        mode = args[1]
                        from app.cli.data_commands import set_operating_mode_command
                        await set_operating_mode_command(mode)
                    elif subcmd == 'api' and len(args) >= 2:
                        api = args[1]
                        from app.cli.data_commands import select_data_api_command
                        await select_data_api_command(api)
                    elif subcmd == 'import-api' and len(args) >= 5:
                        data_type = args[1]
                        symbol = args[2].upper()
                        start_date = args[3]
                        end_date = args[4]
                        from app.cli.data_commands import import_from_api_command
                        await import_from_api_command(data_type, symbol, start_date, end_date)
                    else:
                        self.console.print("[red]Usage:[/red]")
                        self.console.print("  data list                      - List all symbols")
                        self.console.print("  data info <symbol>             - Show symbol info")
                        self.console.print("  data quality <symbol>          - Check data quality")
                        self.console.print("  data delete <symbol>           - Delete symbol data")
                        self.console.print("  data delete-all                - Delete ALL data (⚠️ dangerous!)")
                        self.console.print("  data mode <realtime|backtest>  - Set DataManager operating mode")
                        self.console.print("  data api <provider>            - Select data API provider")
                        self.console.print("  data import-api <type> <symbol> <start> <end>")
                else:
                    self.console.print("[red]Usage: data <list|info|quality|delete|delete-all|mode|api|import-api>[/red]")
            
            # Claude AI commands
            elif cmd == 'ask':
                if args:
                    question = ' '.join(args)
                    await self.ask_claude(question)
                else:
                    self.console.print("[red]Usage: ask <your question>[/red]")
            
            elif cmd == 'analyze':
                if args:
                    symbol = args[0].upper()
                    await self.analyze_stock(symbol)
                else:
                    self.console.print("[red]Usage: analyze <SYMBOL>[/red]")
            
            elif cmd == 'claude':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'status':
                        self.show_claude_status()
                    elif subcmd == 'usage':
                        self.show_claude_usage()
                    elif subcmd == 'history':
                        self.show_claude_history()
                    else:
                        self.console.print(f"[red]Unknown claude command: {subcmd}[/red]")
                        self.console.print("[dim]Try: claude status, claude usage, claude history[/dim]")
                else:
                    self.console.print("[red]Usage: claude <status|usage|history>[/red]")
            
            # Alpaca integration commands
            elif cmd == 'alpaca':
                if not args:
                    self.console.print("[red]Usage: alpaca <connect|disconnect>[/red]")
                else:
                    subcmd = args[0].lower()
                    if subcmd == 'connect':
                        self.console.print("[yellow]Testing Alpaca API connection...[/yellow]")
                        try:
                            ok = await alpaca_client.validate_connection()
                        except Exception as e:
                            logger.error(f"Alpaca connection error: {e}")
                            ok = False
                        if ok:
                            self.console.print(
                                Panel.fit(
                                    "[green]✓ Alpaca connection successful[/green]",
                                    box=box.ROUNDED,
                                    border_style="green",
                                )
                            )
                        else:
                            self.console.print(
                                Panel.fit(
                                    "[red]✗ Alpaca connection failed[/red]\n"
                                    "[dim]Check ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, "
                                    "and ALPACA_API_BASE_URL in your environment.[/dim]",
                                    box=box.ROUNDED,
                                    border_style="red",
                                )
                            )
                    elif subcmd == 'disconnect':
                        self.console.print("[yellow]Disconnecting Alpaca (logical only)...[/yellow]")
                        self.console.print(
                            Panel.fit(
                                "[cyan]Alpaca uses stateless API keys.[/cyan]\n"
                                "[dim]To fully disconnect, remove or rotate your Alpaca API keys "
                                "from the environment (.env).[/dim]",
                                box=box.ROUNDED,
                                border_style="cyan",
                            )
                        )
                    else:
                        self.console.print(f"[red]Unknown alpaca command: {subcmd}[/red]")
                        self.console.print("[dim]Try: alpaca connect or alpaca disconnect[/dim]")
            
            else:
                self.console.print(f"[red]Unknown command: {cmd}[/red]")
                self.console.print("[dim]Type 'help' for available commands[/dim]")
        
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            self.console.print(f"[red]Error: {e}[/red]")
        
        return True
    
    def show_claude_status(self):
        """Show Claude API configuration status"""
        from rich.table import Table
        
        table = Table(title="Claude AI Configuration", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        is_configured = claude_client.client is not None
        
        table.add_row("Status", "✓ Configured" if is_configured else "✗ Not Configured")
        table.add_row("Model", claude_client.model if is_configured else "N/A")
        table.add_row("API Key", "Set" if is_configured else "Not Set")
        
        self.console.print(table)
        
        if not is_configured:
            self.console.print("\n[yellow]To configure Claude AI:[/yellow]")
            self.console.print("[dim]1. Get an API key from https://console.anthropic.com/[/dim]")
            self.console.print("[dim]2. Add it to .env: ANTHROPIC_API_KEY=sk-ant-...[/dim]")
            self.console.print("[dim]3. Restart the CLI[/dim]")
    
    async def ask_claude(self, question: str):
        """Ask Claude a question"""
        if not claude_client.client:
            self.console.print("[red]Claude API not configured[/red]")
            self.console.print("[dim]Set ANTHROPIC_API_KEY in .env file[/dim]")
            return
        
        self.console.print(f"\n[yellow]Asking Claude:[/yellow] {question}\n")
        
        try:
            with self.console.status("[cyan]Thinking...", spinner="dots"):
                response = await claude_client.client.messages.create(
                    model=claude_client.model,
                    max_tokens=2048,
                    temperature=0.7,
                    messages=[{"role": "user", "content": question}]
                )
            
            answer = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens = input_tokens + output_tokens
            
            # Track usage
            usage_tracker.record_usage(
                username=self.current_user['username'],
                operation="ask",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=claude_client.model
            )
            
            self.console.print(Panel(
                answer,
                title="[bold cyan]Claude's Response[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED
            ))
            self.console.print(f"\n[dim]Model: {claude_client.model} | Tokens: {tokens} (In: {input_tokens}, Out: {output_tokens})[/dim]\n")
            logger.info(f"Claude question answered ({tokens} tokens)")
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Claude API error: {e}")
    
    async def analyze_stock(self, symbol: str):
        """Analyze a stock with Claude"""
        if not claude_client.client:
            self.console.print("[red]Claude API not configured[/red]")
            self.console.print("[dim]Set ANTHROPIC_API_KEY in .env file[/dim]")
            return
        
        self.console.print(f"\n[yellow]Analyzing {symbol} with Claude AI...[/yellow]\n")
        
        try:
            # Use placeholder market data since we don't have real data yet
            market_data = {
                "note": "Using Claude's knowledge base and recent market context"
            }
            
            with self.console.status(f"[cyan]Analyzing {symbol}...", spinner="dots"):
                result = await claude_client.analyze_stock(
                    symbol=symbol,
                    market_data=market_data,
                    analysis_type="technical"
                )
            
            # Track usage (rough estimate of input/output split)
            usage_tracker.record_usage(
                username=self.current_user['username'],
                operation="analyze",
                input_tokens=result['tokens_used'] // 3,  # Rough estimate
                output_tokens=result['tokens_used'] * 2 // 3,
                model=claude_client.model
            )
            
            self.console.print(Panel(
                result["analysis"],
                title=f"[bold cyan]{symbol} Analysis[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED
            ))
            self.console.print(f"\n[dim]Model: {result['model']} | Tokens: {result['tokens_used']}[/dim]\n")
            logger.info(f"Stock analysis completed for {symbol} ({result['tokens_used']} tokens)")
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Stock analysis error: {e}")
    
    def show_claude_usage(self):
        """Show Claude API usage statistics for current user"""
        from rich.table import Table
        
        stats = usage_tracker.get_user_stats(self.current_user['username'])
        
        if stats['total_requests'] == 0:
            self.console.print("\n[yellow]No Claude API usage yet[/yellow]")
            self.console.print("[dim]Try: ask <question> or analyze <symbol>[/dim]\n")
            return
        
        # Summary table
        table = Table(title=f"Claude Usage - {self.current_user['username']}", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Requests", str(stats['total_requests']))
        table.add_row("Total Tokens", f"{stats['total_tokens']:,}")
        table.add_row("Input Tokens", f"{stats['total_input_tokens']:,}")
        table.add_row("Output Tokens", f"{stats['total_output_tokens']:,}")
        table.add_row("Estimated Cost", f"${stats['estimated_total_cost']:.4f} USD")
        
        self.console.print("\n")
        self.console.print(table)
        
        # Operations breakdown
        if stats['operations']:
            self.console.print("\n")
            ops_table = Table(title="Operations Breakdown", box=box.ROUNDED)
            ops_table.add_column("Operation", style="cyan")
            ops_table.add_column("Count", style="yellow", justify="right")
            ops_table.add_column("Tokens", style="blue", justify="right")
            ops_table.add_column("Cost", style="green", justify="right")
            
            for op_name, op_data in stats['operations'].items():
                ops_table.add_row(
                    op_name,
                    str(op_data['count']),
                    f"{op_data['tokens']:,}",
                    f"${op_data['cost']:.4f}"
                )
            
            self.console.print(ops_table)
        
        self.console.print("\n[dim]Costs are estimates based on Claude Opus 4 pricing[/dim]")
        self.console.print("[dim]Input: $15/M tokens | Output: $75/M tokens[/dim]\n")
    
    def show_claude_history(self):
        """Show recent Claude API usage history"""
        from rich.table import Table
        
        history = usage_tracker.get_recent_history(
            limit=10,
            username=self.current_user['username']
        )
        
        if not history:
            self.console.print("\n[yellow]No usage history yet[/yellow]\n")
            return
        
        table = Table(title="Recent Claude API Usage", box=box.ROUNDED)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Operation", style="yellow")
        table.add_column("Tokens", style="blue", justify="right")
        table.add_column("Cost", style="green", justify="right")
        
        for record in history:
            timestamp = datetime.fromisoformat(record['timestamp'])
            time_str = timestamp.strftime("%H:%M:%S")
            
            table.add_row(
                time_str,
                record['operation'],
                f"{record['total_tokens']:,}",
                f"${record['estimated_cost']:.4f}"
            )
        
        self.console.print("\n")
        self.console.print(table)
        self.console.print("\n[dim]Showing last 10 requests[/dim]\n")
    
    async def run(self):
        """
        Run the interactive CLI REPL
        """
        try:
            # Display banner
            self.display_banner()
            
            # Login
            if not await self.login():
                self.console.print("[red]Login failed. Exiting...[/red]")
                return
            
            # Show welcome and help
            self.console.print("[dim]Type 'help' for available commands, 'exit' to quit[/dim]\n")
            
            # Main command loop
            self.running = True
            while self.running:
                try:
                    # Validate session is still active
                    if not auth_service.validate_session(self.session_token):
                        self.console.print("\n[red]Session expired. Please login again.[/red]")
                        if not await self.login():
                            break
                    
                    # Get command (use input() for readline compatibility)
                    username = self.current_user['username']
                    # Readline needs \001 and \002 markers around non-printing chars
                    # \001 = start non-printing, \002 = end non-printing
                    prompt = f"\001\x1b[1;36m\002{username}@mismartera:\001\x1b[0m\002 "
                    command = input(prompt)
                    
                    # Execute command
                    if not await self.execute_command(command):
                        break
                        
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Use 'exit' to quit[/yellow]")
                    continue
                except EOFError:
                    break
        
        finally:
            # Logout and cleanup
            self.logout()
            self.console.print("\n[dim]Session ended[/dim]\n")
            logger.info("Interactive CLI session ended")


def start_interactive_cli():
    """Start the interactive CLI"""
    import asyncio
    cli = InteractiveCLI()
    asyncio.run(cli.run())
