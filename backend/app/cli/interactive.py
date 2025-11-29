"""
Interactive CLI REPL
Provides a session-based interactive command interface
"""
import sys
import os
import atexit
from datetime import datetime
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
from app.models.database import SessionLocal
from app.services.csv_import_service import csv_import_service
from app.managers.data_manager.parquet_storage import parquet_storage
from app.cli.command_registry import (
    DATA_COMMANDS,
    MARKET_COMMANDS,
    SYSTEM_COMMANDS,
    GENERAL_COMMANDS,
    ADMIN_COMMANDS,
    CLAUDE_COMMANDS,
    ALPACA_COMMANDS,
    SCHWAB_COMMANDS,
    EXECUTION_COMMANDS,
    TIME_COMMANDS,
)


class CommandCompleter:
    """
    Smart tab completion for interactive CLI commands
    """
    
    def __init__(self):
        # Build main command list and subcommand lists from registries (single source of truth)
        self.commands = []
        
        # Add all main commands from registries
        self.commands.extend([meta.name for meta in GENERAL_COMMANDS])
        self.commands.extend([meta.name for meta in ADMIN_COMMANDS])
        
        # Add command namespaces
        self.commands.extend(['data', 'market', 'system', 'time'])
        self.commands.extend(['claude', 'alpaca', 'schwab', 'execution'])
        
        # Add standalone commands (direct shortcuts)
        self.commands.extend(['ask', 'analyze'])
        
        # Build subcommand lists from registries
        self.data_commands = [meta.name for meta in DATA_COMMANDS]
        self.market_commands = [meta.name for meta in MARKET_COMMANDS]
        self.system_commands = [meta.name for meta in SYSTEM_COMMANDS]
        self.time_commands = [meta.name for meta in TIME_COMMANDS]
        self.claude_commands = [meta.name for meta in CLAUDE_COMMANDS]
        self.alpaca_commands = [meta.name for meta in ALPACA_COMMANDS]
        self.schwab_commands = [meta.name for meta in SCHWAB_COMMANDS]
        self.execution_commands = [meta.name for meta in EXECUTION_COMMANDS]
        
        # Cache for symbols (loaded on first use)
        self.cached_symbols = []
    
    def get_symbols(self):
        """Get list of symbols from database (cached)"""
        if not self.cached_symbols:
            try:
                # This will be populated by the CLI when logged in
                import asyncio
                from app.cli.data_commands import get_data_manager
                from app.models.database import SessionLocal
                
                def _fetch():
                    data_manager = get_data_manager()
                    with SessionLocal() as session:
                        return data_manager.get_symbols(session)
                
                self.cached_symbols = _fetch()
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
                    # Enumerated value completion for certain subcommands
                    elif len(words) >= 2 and words[1] == 'backtest-speed':
                        # data backtest-speed <numeric multiplier> - suggest common values
                        choices = ['0', '0.5', '1.0', '2.0', '5.0', '10.0']
                        matches = [c + ' ' for c in choices if c.startswith(text)]
                    elif len(words) >= 2 and words[1] == 'mode':
                        # data mode <backtest|live>
                        choices = ['backtest', 'live']
                        matches = [c + ' ' for c in choices if c.startswith(text)]
                    # Use registry metadata to decide when to suggest symbols
                    elif len(words) >= 2:
                        subcmd = words[1]
                        # Find metadata for this subcommand, if any
                        meta = next((m for m in DATA_COMMANDS if m.name == subcmd), None)
                        if meta and meta.suggests_symbols_at is not None:
                            # words: ['data', subcmd, arg1, arg2, ...]
                            # arg index (0-based) = current word index - 1
                            current_arg_index = len(words) - 1
                            if current_arg_index - 1 == meta.suggests_symbols_at:
                                symbols = self.get_symbols()
                                matches = [s + ' ' for s in symbols if s.startswith(text.upper())]
                            else:
                                matches = []
                    else:
                        matches = []
                
                # System subcommands
                elif first_word == 'system':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.system_commands if cmd.startswith(text)]
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
                
                # Alpaca subcommands
                elif first_word == 'alpaca':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.alpaca_commands if cmd.startswith(text)]
                    else:
                        matches = []
                
                # Schwab subcommands
                elif first_word == 'schwab':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.schwab_commands if cmd.startswith(text)]
                    else:
                        matches = []
                
                # Execution subcommands
                elif first_word == 'execution':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.execution_commands if cmd.startswith(text)]
                    # After 'execution order', suggest symbols
                    elif words[1] == 'order' and len(words) >= 2:
                        symbols = self.get_symbols()
                        matches = [s + ' ' for s in symbols if s.startswith(text.upper())]
                    else:
                        matches = []
                
                # Market subcommands
                elif first_word == 'market':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.market_commands if cmd.startswith(text)]
                    else:
                        matches = []
                
                # Time subcommands
                elif first_word == 'time':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        matches = [cmd + ' ' for cmd in self.time_commands if cmd.startswith(text)]
                    else:
                        matches = []
                
                # Help command - suggest namespaces or commands within namespace
                elif first_word == 'help':
                    if len(words) == 1 or (len(words) == 2 and not line.endswith(' ')):
                        # Suggest namespaces
                        namespaces = ['general', 'admin', 'system', 'data', 'market', 'time', 
                                     'claude', 'alpaca', 'schwab', 'execution']
                        matches = [ns + ' ' for ns in namespaces if ns.startswith(text)]
                    elif len(words) >= 3:
                        # User typed "help <namespace> ..." - suggest commands from that namespace
                        # Join all words after namespace to handle multi-word command completion
                        namespace = words[1].lower()
                        partial_cmd = ' '.join(words[2:]) if not line.endswith(' ') else ' '.join(words[2:]) + ' '
                        partial_cmd = partial_cmd.strip()
                        
                        # Get command list for namespace
                        cmd_list = None
                        if namespace == 'data':
                            cmd_list = DATA_COMMANDS
                        elif namespace == 'time':
                            cmd_list = TIME_COMMANDS
                        elif namespace == 'system':
                            cmd_list = SYSTEM_COMMANDS
                        elif namespace == 'execution':
                            cmd_list = EXECUTION_COMMANDS
                        elif namespace == 'claude':
                            cmd_list = CLAUDE_COMMANDS
                        elif namespace == 'alpaca':
                            cmd_list = ALPACA_COMMANDS
                        elif namespace == 'schwab':
                            cmd_list = SCHWAB_COMMANDS
                        elif namespace == 'market':
                            cmd_list = MARKET_COMMANDS
                        elif namespace == 'general':
                            cmd_list = GENERAL_COMMANDS
                        elif namespace == 'admin':
                            cmd_list = ADMIN_COMMANDS
                        
                        if cmd_list:
                            # Match commands that start with the partial command
                            matches = [cmd.name + ' ' for cmd in cmd_list if cmd.name.startswith(partial_cmd)]
                        else:
                            matches = []
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
        # Use singleton DataManager to share state with all commands
        from app.cli.data_commands import get_data_manager
        self.data_manager = get_data_manager()
        
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
        
    def login(self) -> bool:
        """
        Prompt for login credentials
        
        Returns:
            True if login successful, False otherwise
        """
        # When login requirement is disabled, run as system user without prompts
        if settings.DISABLE_CLI_LOGIN_REQUIREMENT:
            self.current_user = {
                "username": "system",
                "role": "admin",
                "email": "system@mismartera.com",
            }
            # Create an in-memory session so validate_session calls succeed
            self.session_token = auth_service.create_session(
                self.current_user["username"], self.current_user
            )
            self.console.print(
                "[yellow]Authentication disabled for CLI. "
                "Running as system user.[/yellow]\n"
            )
            self.console.print(
                f"[green]✓[/green] Welcome, [bold]{self.current_user['username']}[/bold]!"
            )
            self.console.print(
                f"[dim]Role: {self.current_user.get('role', 'admin')}[/dim]\n"
            )
            logger.info("CLI started with authentication disabled (system user)")
            return True

        self.console.print("[yellow]Please login to continue[/yellow]\n")
        
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            try:
                username = Prompt.ask("[cyan]Username[/cyan]")
                password = getpass.getpass("Password: ")
                
                # Authenticate with database
                with SessionLocal() as db_session:
                    self.session_token = auth_service.login(username, password, db_session)
                
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
    
    def show_help(self, namespace: Optional[str] = None, subcommand: Optional[str] = None):
        """Display available commands (auto-generated from registries)
        
        Args:
            namespace: Optional command namespace (e.g., 'data', 'time', 'system')
            subcommand: Optional specific subcommand (e.g., 'import-api', 'session')
        """
        # Command registry mapping
        command_groups = {
            'general': ('GENERAL COMMANDS', GENERAL_COMMANDS),
            'admin': ('ADMIN COMMANDS', ADMIN_COMMANDS),
            'system': ('SYSTEM MANAGEMENT', SYSTEM_COMMANDS),
            'data': ('DATA COMMANDS', DATA_COMMANDS),
            'market': ('MARKET COMMANDS', MARKET_COMMANDS),
            'time': ('TIME COMMANDS', TIME_COMMANDS),
            'claude': ('CLAUDE AI COMMANDS', CLAUDE_COMMANDS),
            'alpaca': ('ALPACA COMMANDS', ALPACA_COMMANDS),
            'schwab': ('SCHWAB COMMANDS', SCHWAB_COMMANDS),
            'execution': ('EXECUTION COMMANDS', EXECUTION_COMMANDS),
        }
        
        # If specific subcommand requested, show detailed help
        if namespace and subcommand:
            self._show_command_detail(namespace, subcommand, command_groups)
            return
        
        # If namespace specified, show only that namespace
        if namespace:
            if namespace.lower() in command_groups:
                self._show_namespace_help(namespace.lower(), command_groups)
            else:
                self.console.print(f"[red]Unknown command namespace: {namespace}[/red]")
                self.console.print(f"[yellow]Available namespaces: {', '.join(command_groups.keys())}[/yellow]")
            return
        
        # Show all commands (default behavior)
        table = Table(title="Available Commands", box=box.ROUNDED)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        
        # Add each command group with alphabetically sorted commands
        first = True
        for group_name, (title, commands) in command_groups.items():
            if not first:
                table.add_section()
            table.add_row(f"[bold cyan]{title}[/bold cyan]", "", style="cyan")
            # Sort commands alphabetically by name
            sorted_commands = sorted(commands, key=lambda cmd: cmd.name)
            for meta in sorted_commands:
                table.add_row(meta.usage, meta.description)
            first = False
        
        self.console.print(table)
        self.console.print("\n[dim]Tip: Use 'help <namespace>' for detailed help (e.g., 'help data', 'help time')[/dim]")
        self.console.print("[dim]     Use 'help <namespace> <command>' for command examples (e.g., 'help data import-api')[/dim]")
    
    def _show_namespace_help(self, namespace: str, command_groups: dict):
        """Show help for a specific namespace"""
        title, commands = command_groups[namespace]
        
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        
        # Sort commands alphabetically by name
        sorted_commands = sorted(commands, key=lambda cmd: cmd.name)
        for meta in sorted_commands:
            table.add_row(meta.usage, meta.description)
        
        self.console.print(table)
        self.console.print(f"\n[dim]Tip: Use 'help {namespace} <command>' for detailed examples[/dim]")
    
    def _show_command_detail(self, namespace: str, subcommand: str, command_groups: dict):
        """Show detailed help for a specific command"""
        if namespace.lower() not in command_groups:
            self.console.print(f"[red]Unknown namespace: {namespace}[/red]")
            return
        
        title, commands = command_groups[namespace.lower()]
        
        # Find exact match first
        exact_match = [cmd for cmd in commands if cmd.name == subcommand]
        
        # Find commands that start with the search term (for partial matches)
        partial_matches = [cmd for cmd in commands if cmd.name.startswith(subcommand) and cmd.name != subcommand]
        
        if exact_match:
            # Show the exact match
            cmd = exact_match[0]
            
            # Display detailed information
            self.console.print(f"\n[bold cyan]Command:[/bold cyan] {cmd.usage}")
            self.console.print(f"[bold cyan]Description:[/bold cyan] {cmd.description}")
            
            if cmd.examples:
                self.console.print(f"\n[bold cyan]Examples:[/bold cyan]")
                for example in cmd.examples:
                    self.console.print(f"  [green]$[/green] {example}")
            
            # If there are related commands, show them too
            if partial_matches:
                self.console.print(f"\n[dim]Related commands:[/dim]")
                for related in partial_matches:
                    self.console.print(f"  [cyan]{namespace} {related.name}[/cyan] - {related.description}")
                self.console.print(f"\n[dim]Tip: Use 'help {namespace} <command>' to see details[/dim]")
            
            self.console.print()
        
        elif partial_matches:
            # No exact match, but found partial matches
            self.console.print(f"\n[yellow]Multiple commands found matching '{subcommand}':[/yellow]\n")
            for cmd in partial_matches:
                self.console.print(f"[bold cyan]{namespace} {cmd.name}[/bold cyan]")
                self.console.print(f"  {cmd.description}")
                self.console.print()
            self.console.print(f"[dim]Use 'help {namespace} <full-command-name>' for detailed examples[/dim]")
        
        else:
            # No matches at all
            self.console.print(f"[red]Unknown command: {namespace} {subcommand}[/red]")
            self.console.print(f"\n[yellow]Available commands in {namespace}:[/yellow]")
            for cmd in commands:
                self.console.print(f"  {cmd.name}")
            self.console.print()
    
    def show_status(self):
        """Show application status"""
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
    
    def run_script(self, script_path: str) -> None:
        """Execute commands from a script file.
        
        Args:
            script_path: Path to the script file
        """
        # Expand home directory if needed
        script_path = os.path.expanduser(script_path)
        
        # Check if file exists
        if not os.path.exists(script_path):
            self.console.print(f"[red]✗[/red] Script file not found: {script_path}")
            return
        
        if not os.path.isfile(script_path):
            self.console.print(f"[red]✗[/red] Not a file: {script_path}")
            return
        
        # Read the script file
        try:
            with open(script_path, 'r') as f:
                lines = f.readlines()
        except Exception as e:
            self.console.print(f"[red]✗[/red] Error reading script file: {e}")
            return
        
        # Display script info
        self.console.print(f"\n[cyan]Running script:[/cyan] {script_path}")
        self.console.print(f"[dim]Lines: {len(lines)}[/dim]\n")
        
        # Execute commands
        executed = 0
        skipped = 0
        errors = 0
        
        for line_num, line in enumerate(lines, 1):
            # Strip whitespace
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip comments (lines starting with #)
            if line.startswith('#'):
                skipped += 1
                self.console.print(f"[dim]{line_num:3d}:[/dim] [dim]{line}[/dim]")
                continue
            
            # Display the command being executed
            self.console.print(f"[dim]{line_num:3d}:[/dim] [yellow]{line}[/yellow]")
            
            # Execute the command
            try:
                # Check if we should exit (execute_command returns False to exit)
                should_continue = self.execute_command(line)
                if not should_continue:
                    self.console.print(f"\n[yellow]Script execution stopped by exit/logout command at line {line_num}[/yellow]")
                    break
                executed += 1
            except KeyboardInterrupt:
                self.console.print(f"\n[yellow]Script execution interrupted by user at line {line_num}[/yellow]")
                break
            except Exception as e:
                errors += 1
                self.console.print(f"[red]✗[/red] Error executing line {line_num}: {e}")
                logger.error(f"Script error at line {line_num}: {e}", exc_info=True)
        
        # Summary
        self.console.print(f"\n[cyan]Script execution completed[/cyan]")
        self.console.print(f"[green]✓[/green] Executed: {executed}")
        if skipped > 0:
            self.console.print(f"[dim]○[/dim] Skipped (comments/empty): {skipped}")
        if errors > 0:
            self.console.print(f"[red]✗[/red] Errors: {errors}")
        self.console.print()
    
    def execute_command(self, command: str) -> bool:
        """
        Execute a user command
        
        Commands are defined in command registries (single source of truth):
        - GENERAL_COMMANDS: help, history, run, status, clear, etc.
        - ADMIN_COMMANDS: log-level, sessions, etc.
        - SYSTEM_COMMANDS: system start/stop/pause/resume/mode/status
        - DATA_COMMANDS: data list/import/export/stream/etc.
        - MARKET_COMMANDS: market status
        - TIME_COMMANDS: time current/session/holidays/holidays import/holidays delete/etc.
        
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
            # ==================== GENERAL COMMANDS (from GENERAL_COMMANDS registry) ====================
            
            if cmd in ['exit', 'quit']:
                if Confirm.ask("\n[yellow]Are you sure you want to exit?[/yellow]"):
                    return False
                return True
            
            if cmd == 'help':
                # Parse arguments for context-sensitive help
                namespace = args[0] if len(args) >= 1 else None
                # Join all remaining args to handle multi-word commands like "holidays delete"
                subcommand = ' '.join(args[1:]) if len(args) >= 2 else None
                self.show_help(namespace, subcommand)
            
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
            
            elif cmd == 'run':
                # Execute commands from a script file
                if not args:
                    self.console.print("[red]Usage: run <script_file>[/red]")
                else:
                    script_file = ' '.join(args)  # Join in case of spaces in path
                    self.run_script(script_file)
            
            elif cmd == 'delay':
                # Pause execution for specified milliseconds
                if not args:
                    self.console.print("[red]Usage: delay <milliseconds>[/red]")
                elif not args[0].isdigit():
                    self.console.print("[red]Error: milliseconds must be a positive integer[/red]")
                else:
                    ms = int(args[0])
                    self.console.print(f"[dim]Pausing for {ms}ms...[/dim]")
                    asyncio.sleep(ms / 1000.0)
                    self.console.print(f"[green]✓[/green] Resumed after {ms}ms")
            
            # ==================== ADMIN COMMANDS (from ADMIN_COMMANDS registry) ====================
            
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
            
            # ==================== MARKET COMMANDS (from MARKET_COMMANDS registry) ====================
            
            elif cmd == 'market':
                if args and args[0].lower() == 'status':
                    self.console.print("[yellow]Checking market status...[/yellow]")

                    try:
                        with SessionLocal() as session:
                            # In backtest mode, ensure the backtest window and
                            # clock are initialized before reading time.
                            if self.data_manager.system_manager.mode.value == "backtest" and self.data_manager.backtest_start_date is None:
                                self.data_manager.init_backtest(session)

                            # Aggregate market info for the current date/time
                            info = self.data_manager.get_current_day_market_info(session)

                        # All DataManager times are expressed in canonical
                        # trading timezone (ET). For display, we optionally
                        # convert to the local system timezone.
                        from datetime import datetime as _dt
                        from zoneinfo import ZoneInfo as _ZoneInfo

                        trading_tz = _ZoneInfo(settings.TRADING_TIMEZONE)
                        local_tz = _ZoneInfo(settings.LOCAL_TIMEZONE)

                        def _to_display(dt_val: _dt) -> tuple[str, str]:
                            """Return (formatted_time, tz_label).

                            dt_val is a naive datetime representing Eastern
                            Time wall-clock. To get correct DST behavior, we
                            construct a new aware datetime in the trading
                            timezone rather than using replace(tzinfo=...).
                            """
                            aware_et = _dt(
                                dt_val.year,
                                dt_val.month,
                                dt_val.day,
                                dt_val.hour,
                                dt_val.minute,
                                dt_val.second,
                                dt_val.microsecond,
                                tzinfo=trading_tz,
                            )
                            if settings.DISPLAY_LOCAL_TIMEZONE and local_tz is not None:
                                local_dt = aware_et.astimezone(local_tz)
                                return local_dt.strftime("%H:%M:%S"), local_dt.tzname() or "local"
                            return aware_et.strftime("%H:%M:%S"), "ET"

                        now = info.now
                        now_str, now_tz = _to_display(now)

                        table = Table(title="Market Status", box=box.ROUNDED)
                        table.add_column("Property", style="cyan")
                        table.add_column("Value", style="green")

                        table.add_row("Mode", self.data_manager.system_manager.mode.value.upper())
                        table.add_row("Current Time", f"{now_str} {now_tz}")
                        table.add_row("Date", f"{info.date.isoformat()} ({info.date.strftime('%a')})")

                        # Day classification / holiday details
                        if info.is_holiday:
                            if info.is_early_close and info.early_close_time:
                                # For early close, convert the ET close time
                                # for display using the same rules.
                                ec_dt = _dt.combine(info.date, info.early_close_time)
                                ec_str, ec_tz = _to_display(ec_dt)
                                desc = f"Early close at {ec_str} {ec_tz}"
                            else:
                                desc = "Closed"
                            table.add_row("Today", "Holiday")
                            if info.holiday_name:
                                table.add_row("Holiday Name", info.holiday_name)
                            table.add_row("Holiday Type", desc)
                        elif info.is_weekend:
                            table.add_row("Today", "Weekend")
                        else:
                            table.add_row("Today", "Regular trading day")

                        # Trading hours for today (if any). On a full-day
                        # holiday (closed), we omit Market Hours entirely to
                        # avoid redundant "Closed all day".
                        if info.is_holiday and not info.is_early_close:
                            pass
                        elif info.trading_hours:
                            open_dt = _dt.combine(info.date, info.trading_hours.open_time)
                            close_dt = _dt.combine(info.date, info.trading_hours.close_time)
                            open_str, open_tz = _to_display(open_dt)
                            close_str, close_tz = _to_display(close_dt)
                            table.add_row("Market Open", f"{open_str} {open_tz}")
                            table.add_row("Market Close", f"{close_str} {close_tz}")
                        else:
                            table.add_row("Market Hours", "Closed all day")

                        table.add_row("Market Is Open", "YES" if info.is_market_open else "NO")

                        self.console.print(table)
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Market status error: {e}")
                        self.console.print(f"[red]✗ Error checking market status: {e}[/red]")
                else:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in MARKET_COMMANDS]
                    self.console.print(f"[red]Usage: market <{' | '.join(subcommands)}>[/red]")
            
            # (watchlist command removed)
            
            # ==================== TIME COMMANDS (from TIME_COMMANDS registry) ====================
            
            elif cmd == 'time':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'current':
                        timezone = None
                        # Parse --timezone flag
                        if '--timezone' in args:
                            tz_idx = args.index('--timezone')
                            if tz_idx + 1 < len(args):
                                timezone = args[tz_idx + 1]
                        from app.cli.time_commands import current_time_command
                        current_time_command(timezone=timezone)
                    elif subcmd == 'market':
                        exchange = "NYSE"
                        extended = False
                        if '--exchange' in args:
                            exc_idx = args.index('--exchange')
                            if exc_idx + 1 < len(args):
                                exchange = args[exc_idx + 1]
                        if '--extended' in args:
                            extended = True
                        from app.cli.time_commands import market_status_command
                        market_status_command(exchange=exchange, extended=extended)
                    elif subcmd == 'session':
                        date_str = None
                        exchange = "NYSE"
                        if len(args) >= 2 and not args[1].startswith('--'):
                            date_str = args[1]
                        if '--exchange' in args:
                            exc_idx = args.index('--exchange')
                            if exc_idx + 1 < len(args):
                                exchange = args[exc_idx + 1]
                        from app.cli.time_commands import trading_session_command
                        trading_session_command(date_str=date_str, exchange=exchange)
                    elif subcmd == 'next':
                        from_date_str = None
                        n = 1
                        exchange = "NYSE"
                        if len(args) >= 2 and not args[1].startswith('--'):
                            from_date_str = args[1]
                        if '--n' in args:
                            n_idx = args.index('--n')
                            if n_idx + 1 < len(args):
                                n = int(args[n_idx + 1])
                        if '--exchange' in args:
                            exc_idx = args.index('--exchange')
                            if exc_idx + 1 < len(args):
                                exchange = args[exc_idx + 1]
                        from app.cli.time_commands import next_trading_date_command
                        next_trading_date_command(from_date_str=from_date_str, n=n, exchange=exchange)
                    elif subcmd == 'days' and len(args) >= 3:
                        start_str = args[1]
                        end_str = args[2]
                        exchange = "NYSE"
                        if '--exchange' in args:
                            exc_idx = args.index('--exchange')
                            if exc_idx + 1 < len(args):
                                exchange = args[exc_idx + 1]
                        from app.cli.time_commands import trading_days_command
                        trading_days_command(start_str=start_str, end_str=end_str, exchange=exchange)
                    elif subcmd == 'holidays':
                        if len(args) >= 2 and args[1] == 'delete':
                            # "time holidays delete <year>"
                            if len(args) < 3:
                                self.console.print("[red]Usage: time holidays delete <year> [--exchange <exch>][/red]")
                                return True
                            year = int(args[2])
                            exchange = None
                            if '--exchange' in args:
                                exc_idx = args.index('--exchange')
                                if exc_idx + 1 < len(args):
                                    exchange = args[exc_idx + 1]
                            from app.cli.time_commands import delete_holidays_command
                            delete_holidays_command(year=year, exchange=exchange)
                        elif len(args) >= 2 and args[1] == 'import':
                            # "time holidays import <file>"
                            if len(args) < 3:
                                self.console.print("[red]Usage: time holidays import <file> [--exchange <group>] [--dry-run][/red]")
                                return True
                            file_path = args[2]
                            exchange = None
                            dry_run = False
                            if '--exchange' in args:
                                exc_idx = args.index('--exchange')
                                if exc_idx + 1 < len(args):
                                    exchange = args[exc_idx + 1]
                            if '--dry-run' in args:
                                dry_run = True
                            from app.cli.time_commands import import_holidays_command
                            import_holidays_command(file_path=file_path, exchange=exchange, dry_run=dry_run)
                        else:
                            # "time holidays" - list holidays
                            year = None
                            exchange = "NYSE"
                            if '--year' in args:
                                year_idx = args.index('--year')
                                if year_idx + 1 < len(args):
                                    year = int(args[year_idx + 1])
                            if '--exchange' in args:
                                exc_idx = args.index('--exchange')
                                if exc_idx + 1 < len(args):
                                    exchange = args[exc_idx + 1]
                            from app.cli.time_commands import holidays_command
                            holidays_command(year=year, exchange=exchange)
                    elif subcmd == 'convert' and len(args) >= 4:
                        datetime_str = args[1]
                        from_tz = args[2]
                        to_tz = args[3]
                        from app.cli.time_commands import timezone_convert_command
                        timezone_convert_command(datetime_str=datetime_str, from_tz=from_tz, to_tz=to_tz)
                    elif subcmd == 'list-groups':
                        from app.cli.time_commands import list_exchange_groups_command
                        list_exchange_groups_command()
                    elif subcmd == 'backtest-window' and len(args) >= 2:
                        start_date = args[1]
                        end_date = args[2] if len(args) >= 3 else None
                        from app.cli.time_commands import set_backtest_window_command
                        set_backtest_window_command(start_date=start_date, end_date=end_date)
                    elif subcmd == 'advance':
                        extended = False
                        exchange = "NYSE"
                        if '--extended' in args:
                            extended = True
                        if '--exchange' in args:
                            exc_idx = args.index('--exchange')
                            if exc_idx + 1 < len(args):
                                exchange = args[exc_idx + 1]
                        from app.cli.time_commands import advance_to_market_open_command
                        advance_to_market_open_command(extended=extended, exchange=exchange)
                    elif subcmd == 'reset':
                        extended = False
                        if '--extended' in args:
                            extended = True
                        from app.cli.time_commands import reset_to_backtest_start_command
                        reset_to_backtest_start_command(extended=extended)
                    elif subcmd == 'config':
                        from app.cli.time_commands import show_backtest_config_command
                        show_backtest_config_command()
                    elif subcmd == 'exchange' and len(args) >= 2:
                        exchange = args[1]
                        asset_class = args[2] if len(args) >= 3 else "EQUITY"
                        from app.cli.time_commands import set_backtest_exchange_command
                        set_backtest_exchange_command(exchange=exchange, asset_class=asset_class)
                    else:
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown time command. Available commands:[/red]\n")
                        for meta in TIME_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<50}[/cyan] {meta.description}")
                else:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in TIME_COMMANDS]
                    self.console.print(f"[red]Usage: time <{' | '.join(subcommands)}>[/red]")
            
            # ==================== SYSTEM COMMANDS (from SYSTEM_COMMANDS registry) ====================
            
            elif cmd == 'system':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'start':
                        # Use default config if not provided
                        config_path = args[1] if len(args) >= 2 else "session_configs/example_session.json"
                        from app.cli.system_commands import start_command
                        start_command(config_path)
                    elif subcmd == 'pause':
                        from app.cli.system_commands import pause_command
                        pause_command()
                    elif subcmd == 'resume':
                        from app.cli.system_commands import resume_command
                        resume_command()
                    elif subcmd == 'stop':
                        from app.cli.system_commands import stop_command
                        stop_command()
                    elif subcmd == 'mode' and len(args) >= 2:
                        mode = args[1].lower()
                        from app.cli.system_commands import mode_command
                        mode_command(mode)
                    elif subcmd == 'status':
                        from app.cli.system_commands import status_command
                        status_command()
                    else:
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown system command. Available commands:[/red]\n")
                        for meta in SYSTEM_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
                else:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in SYSTEM_COMMANDS]
                    self.console.print(f"[red]Usage: system <{' | '.join(subcommands)}>[/red]")
            
            elif cmd == 'data':
                if args:
                    subcmd = args[0].lower()
                    if subcmd == 'list':
                        from app.cli.data_commands import list_symbols_command
                        list_symbols_command()
                    elif subcmd == 'info' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import data_info_command
                        data_info_command(symbol)
                    elif subcmd == 'quality' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import data_quality_command
                        data_quality_command(symbol)
                    elif subcmd == 'delete' and len(args) >= 2:
                        symbol = args[1].upper()
                        from app.cli.data_commands import delete_symbol_command
                        delete_symbol_command(symbol)
                    elif subcmd == 'delete-all':
                        from app.cli.data_commands import delete_all_command
                        delete_all_command()
                    elif subcmd == 'api' and len(args) >= 2:
                        api = args[1]
                        from app.cli.data_commands import select_data_api_command
                        select_data_api_command(api)
                    elif subcmd == 'import-api' and len(args) >= 5:
                        data_type = args[1]
                        symbol = args[2].upper()
                        start_date = args[3]
                        end_date = args[4]
                        from app.cli.data_commands import import_from_api_command
                        import_from_api_command(data_type, symbol, start_date, end_date)
                    elif subcmd == 'import-file' and len(args) >= 3:
                        # data import-file <file> <symbol> [start] [end]
                        file_path = args[1]
                        symbol = args[2].upper()
                        start_date = args[3] if len(args) >= 4 else None
                        end_date = args[4] if len(args) >= 5 else None
                        from app.cli.data_commands import import_csv_command
                        import_csv_command(file_path, symbol, start_date, end_date)
                    elif subcmd == 'export-csv' and len(args) >= 5:
                        # data export-csv <type> <symbol> <start> <end?> -f <file>
                        data_type = args[1]
                        symbol = args[2].upper()
                        start_date = args[3]
                        end_date = args[4] if not args[4].startswith('-') else None

                        # Find -f/--file in remaining args
                        file_path = None
                        for i, a in enumerate(args[4:], start=4):
                            if a in {'-f', '--file'} and i + 1 < len(args):
                                file_path = args[i + 1]
                                break

                        if not file_path:
                            self.console.print("[red]Usage: data export-csv <type> <symbol> <start> [end] -f <file>[/red]")
                        else:
                            from app.cli.data_commands import export_csv_command
                            export_csv_command(data_type, symbol, start_date, end_date, file_path)
                    elif subcmd == 'bars' and len(args) >= 4:
                        # data bars <symbol> <start> <end> [interval]
                        symbol = args[1].upper()
                        start_date = args[2]
                        end_date = args[3]
                        interval = '1m'
                        if len(args) >= 5:
                            interval = args[4]

                        from app.cli.data_commands import on_demand_bars_command
                        on_demand_bars_command(symbol, start_date, end_date, interval)
                    elif subcmd == 'ticks' and len(args) >= 4:
                        # data ticks <symbol> <start> <end>
                        symbol = args[1].upper()
                        start_date = args[2]
                        end_date = args[3]

                        from app.cli.data_commands import on_demand_ticks_command
                        on_demand_ticks_command(symbol, start_date, end_date)
                    elif subcmd == 'quotes' and len(args) >= 4:
                        # data quotes <symbol> <start> <end>
                        symbol = args[1].upper()
                        start_date = args[2]
                        end_date = args[3]

                        from app.cli.data_commands import on_demand_quotes_command
                        on_demand_quotes_command(symbol, start_date, end_date)
                    elif subcmd == 'latest-bar' and len(args) >= 2:
                        # data latest-bar <symbol> [interval]
                        symbol = args[1].upper()
                        interval = args[2] if len(args) >= 3 else '1m'

                        with SessionLocal() as session:
                            # Ensure backtest clock is initialized if needed
                            if self.data_manager.system_manager.mode.value == "backtest" and self.data_manager.backtest_start_date is None:
                                self.data_manager.init_backtest(session)

                            bar = self.data_manager.get_latest_bar(session, symbol, interval)

                        if not bar:
                            self.console.print(f"[yellow]No bar data found for {symbol} on current date[/yellow]")
                        else:
                            table = Table(title=f"Latest bar: {symbol} ({interval})", box=box.ROUNDED)
                            table.add_column("Timestamp", style="cyan")
                            table.add_column("Open", justify="right")
                            table.add_column("High", justify="right")
                            table.add_column("Low", justify="right")
                            table.add_column("Close", justify="right")
                            table.add_column("Volume", justify="right")

                            ts = bar.timestamp.strftime("%Y-%m-%d %H:%M")
                            table.add_row(
                                ts,
                                f"{bar.open:.2f}",
                                f"{bar.high:.2f}",
                                f"{bar.low:.2f}",
                                f"{bar.close:.2f}",
                                f"{bar.volume:.0f}",
                            )

                            self.console.print(table)
                            source = "live API" if self.data_manager.system_manager.mode.value == "live" else "backtest DB"
                            self.console.print(f"[dim]Source: {source}[/dim]")

                    elif subcmd == 'latest-tick' and len(args) >= 2:
                        # data latest-tick <symbol>
                        symbol = args[1].upper()

                        with SessionLocal() as session:
                            if self.data_manager.system_manager.mode.value == "backtest" and self.data_manager.backtest_start_date is None:
                                self.data_manager.init_backtest(session)

                            tick = self.data_manager.get_latest_tick(session, symbol)

                        if not tick:
                            self.console.print(f"[yellow]No tick data found for {symbol} on current date[/yellow]")
                        else:
                            table = Table(title=f"Latest tick: {symbol}", box=box.ROUNDED)
                            table.add_column("Timestamp", style="cyan")
                            table.add_column("Price", justify="right")
                            table.add_column("Size", justify="right")

                            ts = tick.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                            table.add_row(ts, f"{tick.price:.4f}", f"{tick.size:.0f}")

                            self.console.print(table)
                            source = "live API" if self.data_manager.system_manager.mode.value == "live" else "backtest DB"
                            self.console.print(f"[dim]Source: {source}[/dim]")

                    elif subcmd == 'latest-quote' and len(args) >= 2:
                        # data latest-quote <symbol>
                        symbol = args[1].upper()

                        with SessionLocal() as session:
                            if self.data_manager.system_manager.mode.value == "backtest" and self.data_manager.backtest_start_date is None:
                                self.data_manager.init_backtest(session)

                            quote = self.data_manager.get_latest_quote(session, symbol)

                        if not quote:
                            self.console.print(f"[yellow]No quote data found for {symbol} on current date[/yellow]")
                        else:
                            table = Table(title=f"Latest quote: {symbol}", box=box.ROUNDED)
                            table.add_column("Timestamp", style="cyan")
                            table.add_column("Bid", justify="right")
                            table.add_column("Ask", justify="right")
                            table.add_column("BidSize", justify="right")
                            table.add_column("AskSize", justify="right")

                            ts = quote.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                            table.add_row(
                                ts,
                                f"{quote.bid_price:.4f}",
                                f"{quote.ask_price:.4f}",
                                f"{quote.bid_size:.0f}",
                                f"{quote.ask_size:.0f}",
                            )

                            self.console.print(table)
                            source = "live API" if self.data_manager.system_manager.mode.value == "live" else "backtest DB"
                            self.console.print(f"[dim]Source: {source}[/dim]")
                    elif subcmd == 'backtest-speed' and len(args) >= 2:
                        mode = args[1]
                        from app.cli.data_commands import set_backtest_speed_command
                        set_backtest_speed_command(mode)
                    elif subcmd == 'backtest-window' and len(args) >= 2:
                        # Parse dates and route directly to the shared
                        # DataManager instance so that the updated backtest
                        # window and clock apply to this interactive session.
                        from datetime import datetime as _dt

                        start_str = args[1]
                        end_str = args[2] if len(args) >= 3 else None

                        try:
                            start_dt = _dt.strptime(start_str, "%Y-%m-%d").date()
                        except ValueError:
                            self.console.print("[red]Start date must be in YYYY-MM-DD format[/red]")
                            return True

                        end_dt = None
                        if end_str:
                            try:
                                end_dt = _dt.strptime(end_str, "%Y-%m-%d").date()
                            except ValueError:
                                self.console.print("[red]End date must be in YYYY-MM-DD format[/red]")
                                return True

                        with SessionLocal() as session:
                            self.data_manager.set_backtest_window(session, start_dt, end_dt)

                        effective_end = self.data_manager.backtest_end_date or start_dt

                        # Show full datetime with market open/close times
                        from datetime import time as dt_time, datetime as dt
                        
                        # Use 9:30 AM and 4:00 PM as defaults (will be queried from TimeManager at runtime)
                        start_datetime = dt.combine(start_dt, dt_time(9, 30))
                        end_datetime = dt.combine(effective_end, dt_time(16, 0))

                        self.console.print("[green]✓[/green] Backtest window updated:")
                        self.console.print(f"  Start: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                        self.console.print(f"  End:   {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                    elif subcmd == 'stream-bars' and len(args) >= 3:
                        # data stream-bars <interval> <symbol> [file]
                        interval = args[1]
                        symbol = args[2].upper()
                        file_path = args[3] if len(args) >= 4 else None

                        from app.cli.data_commands import stream_bars_command
                        # Block during DB fetch, then return after starting stream
                        stream_bars_command(symbol, interval, file_path)
                    elif subcmd == 'stream-ticks' and len(args) >= 2:
                        # data stream-ticks <symbol> [file]
                        symbol = args[1].upper()
                        file_path = args[2] if len(args) >= 3 else None

                        from app.cli.data_commands import stream_ticks_command
                        # Block during DB fetch, then return after starting stream
                        stream_ticks_command(symbol, file_path)
                    elif subcmd == 'stream-quotes' and len(args) >= 2:
                        # data stream-quotes <symbol> [file]
                        symbol = args[1].upper()
                        file_path = args[2] if len(args) >= 3 else None

                        from app.cli.data_commands import stream_quotes_command
                        # Block during DB fetch, then return after starting stream
                        stream_quotes_command(symbol, file_path)
                    elif subcmd == 'stop-stream-bars':
                        # data stop-stream-bars [id]
                        stream_id = args[1] if len(args) >= 2 else None

                        from app.cli.data_commands import stop_bars_stream_command
                        stop_bars_stream_command(stream_id)
                    elif subcmd == 'stop-stream-ticks':
                        # data stop-stream-ticks [id]
                        stream_id = args[1] if len(args) >= 2 else None

                        from app.cli.data_commands import stop_ticks_stream_command
                        stop_ticks_stream_command(stream_id)
                    elif subcmd == 'stop-stream-quotes':
                        # data stop-stream-quotes [id]
                        stream_id = args[1] if len(args) >= 2 else None

                        from app.cli.data_commands import stop_quotes_stream_command
                        stop_quotes_stream_command(stream_id)
                    elif subcmd == 'stop-all-streams':
                        # data stop-all-streams
                        from app.cli.data_commands import stop_all_streams_command
                        stop_all_streams_command()
                    elif subcmd == 'snapshot' and len(args) >= 2:
                        # data snapshot <symbol>
                        symbol = args[1].upper()
                        from app.cli.data_commands import snapshot_command
                        snapshot_command(symbol)
                    elif subcmd == 'session-volume' and len(args) >= 2:
                        # data session-volume <symbol>
                        symbol = args[1].upper()
                        from app.cli.data_commands import session_volume_command
                        session_volume_command(symbol)
                    elif subcmd == 'session-high-low' and len(args) >= 2:
                        # data session-high-low <symbol>
                        symbol = args[1].upper()
                        from app.cli.data_commands import session_high_low_command
                        session_high_low_command(symbol)
                    elif subcmd == 'avg-volume' and len(args) >= 3:
                        # data avg-volume <symbol> <days>
                        symbol = args[1].upper()
                        try:
                            days = int(args[2])
                            from app.cli.data_commands import avg_volume_command
                            avg_volume_command(symbol, days)
                        except ValueError:
                            self.console.print("[red]Days must be an integer[/red]")
                    elif subcmd == 'high-low' and len(args) >= 3:
                        # data high-low <symbol> <days>
                        symbol = args[1].upper()
                        try:
                            days = int(args[2])
                            from app.cli.data_commands import high_low_command
                            high_low_command(symbol, days)
                        except ValueError:
                            self.console.print("[red]Days must be an integer[/red]")
                    elif subcmd == 'session':
                        # data session [refresh_seconds] [csv_file] [--duration/-d <seconds>] [--no-live]
                        refresh_seconds = None
                        csv_file = None
                        duration_seconds = None
                        no_live = False
                        
                        i = 1
                        while i < len(args):
                            arg = args[i]
                            
                            # Check for duration flag
                            if arg in ['--duration', '-d']:
                                if i + 1 < len(args) and args[i + 1].isdigit():
                                    duration_seconds = int(args[i + 1])
                                    i += 2
                                    continue
                                else:
                                    self.console.print("[red]Error: --duration/-d requires a number[/red]")
                                    return True
                            
                            # Check for no-live flag
                            if arg == '--no-live':
                                no_live = True
                                i += 1
                                continue
                            
                            # Parse positional args
                            if refresh_seconds is None and arg.isdigit():
                                refresh_seconds = int(arg)
                            elif csv_file is None:
                                csv_file = arg
                            
                            i += 1
                        
                        from app.cli.session_data_display import data_session_command
                        data_session_command(refresh_seconds, csv_file, duration_seconds, no_live)
                    elif subcmd == 'validate':
                        # data validate [csv_file] [--config config_file] [--db-check]
                        csv_file = None
                        config_file = None
                        db_check = False
                        
                        i = 1
                        while i < len(args):
                            if args[i] == '--config' and i + 1 < len(args):
                                config_file = args[i + 1]
                                i += 2
                            elif args[i] == '--db-check':
                                db_check = True
                                i += 1
                            elif not csv_file:
                                csv_file = args[i]
                                i += 1
                            else:
                                i += 1
                        
                        import subprocess
                        from pathlib import Path
                        
                        script_path = Path("validation/validate_session_dump.py")
                        if not script_path.exists():
                            self.console.print("[red]Error: Validation script not found[/red]")
                            return True
                        
                        cmd = ["python", str(script_path)]
                        if csv_file:
                            cmd.append(csv_file)
                        if config_file:
                            cmd.extend(["--config", config_file])
                        if db_check:
                            cmd.append("--db-check")
                        
                        subprocess.run(cmd)
                    else:
                        from app.cli.data_commands import print_data_usage
                        print_data_usage(self.console)
                else:
                    self.console.print("[red]Usage: data <subcommand>[/red]")
                    self.console.print("[dim]Run 'data' with no arguments to see all subcommands.[/dim]")
            
            # ==================== CLAUDE AI COMMANDS (from CLAUDE_COMMANDS registry) ====================
            
            elif cmd == 'ask':
                if args:
                    question = ' '.join(args)
                    self.ask_claude(question)
                else:
                    # Get usage from registry
                    cmd_meta = next((m for m in CLAUDE_COMMANDS if m.name == 'ask'), None)
                    usage = cmd_meta.usage if cmd_meta else "ask <question>"
                    self.console.print(f"[red]Usage: {usage}[/red]")
            
            elif cmd == 'analyze':
                if args:
                    symbol = args[0].upper()
                    self.analyze_stock(symbol)
                else:
                    # Get usage from registry
                    cmd_meta = next((m for m in CLAUDE_COMMANDS if m.name == 'analyze'), None)
                    usage = cmd_meta.usage if cmd_meta else "analyze <symbol>"
                    self.console.print(f"[red]Usage: {usage}[/red]")
            
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
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown claude command. Available commands:[/red]\n")
                        for meta in CLAUDE_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
                else:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in CLAUDE_COMMANDS]
                    self.console.print(f"[red]Usage: claude <{' | '.join(subcommands)}>[/red]")
            
            # ==================== ALPACA COMMANDS (from ALPACA_COMMANDS registry) ====================
            
            elif cmd == 'alpaca':
                if not args:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in ALPACA_COMMANDS]
                    self.console.print(f"[red]Usage: alpaca <{' | '.join(subcommands)}>[/red]")
                else:
                    subcmd = args[0].lower()
                    if subcmd == 'connect':
                        self.console.print("[yellow]Testing Alpaca API connection...[/yellow]")
                        try:
                            ok = alpaca_client.validate_connection()
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
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown alpaca command. Available commands:[/red]\n")
                        for meta in ALPACA_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
            
            # ==================== SCHWAB COMMANDS (from SCHWAB_COMMANDS registry) ====================
            
            elif cmd == 'schwab':
                if not args:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in SCHWAB_COMMANDS]
                    self.console.print(f"[red]Usage: schwab <{' | '.join(subcommands)}>[/red]")
                else:
                    subcmd = args[0].lower()
                    if subcmd == 'connect':
                        self.console.print("[yellow]Testing Charles Schwab API connection...[/yellow]")
                        try:
                            from app.integrations.schwab_client import schwab_client
                            ok = schwab_client.validate_connection()
                        except Exception as e:
                            logger.error(f"Schwab connection error: {e}")
                            ok = False
                        if ok:
                            self.console.print(
                                Panel.fit(
                                    "[green]✓ Schwab connection successful[/green]\n"
                                    "[dim]Configuration validated. Note: Full OAuth authentication "
                                    "requires user authorization flow.[/dim]",
                                    box=box.ROUNDED,
                                    border_style="green",
                                )
                            )
                        else:
                            self.console.print(
                                Panel.fit(
                                    "[red]✗ Schwab connection failed[/red]\n"
                                    "[dim]Check SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_API_BASE_URL, "
                                    "and SCHWAB_CALLBACK_URL in your environment.[/dim]",
                                    box=box.ROUNDED,
                                    border_style="red",
                                )
                            )
                    elif subcmd == 'auth-start':
                        from app.integrations.schwab_client import schwab_client
                        from app.cli.schwab_helpers import oauth_server
                        import webbrowser
                        
                        self.console.print("[cyan]Starting Schwab OAuth 2.0 authorization flow...[/cyan]\n")
                        
                        # Auto-start OAuth server if not running
                        if not oauth_server.is_server_running():
                            self.console.print("[dim]Starting OAuth callback server...[/dim]")
                            if oauth_server.start_server():
                                self.console.print("[green]✓ OAuth server ready[/green]\n")
                            else:
                                self.console.print("[yellow]⚠ OAuth server failed to start - manual callback required[/yellow]\n")
                        else:
                            self.console.print("[dim]OAuth server already running[/dim]\n")
                        
                        auth_url, state = schwab_client.generate_authorization_url()
                        
                        self.console.print(f"[bold]Authorization URL:[/bold]")
                        self.console.print(f"{auth_url}\n")
                        self.console.print(f"[dim]State (for verification): {state[:16]}...[/dim]\n")
                        
                        # Try to open browser
                        try:
                            webbrowser.open(auth_url)
                            self.console.print("[green]✓ Opened browser for authorization[/green]\n")
                        except:
                            self.console.print("[yellow]⚠ Could not open browser automatically[/yellow]")
                            self.console.print("[yellow]Please open the URL above in your browser[/yellow]\n")
                        
                        self.console.print("[bold]Next steps:[/bold]")
                        self.console.print("  1. Authorize the application in the browser")
                        if oauth_server.is_server_running():
                            self.console.print("  2. Authorization will complete automatically!")
                            self.console.print("  3. Check status with: schwab auth-status")
                        else:
                            self.console.print("  2. You'll be redirected to the callback URL")
                            self.console.print("  3. Copy the 'code' parameter from the URL")
                            self.console.print("  4. Run: schwab auth-callback <code>")
                    
                    elif subcmd == 'auth-callback':
                        if len(args) < 2:
                            self.console.print("[red]Usage: schwab auth-callback <authorization_code>[/red]")
                            return True
                        
                        from app.integrations.schwab_client import schwab_client
                        auth_code = args[1]
                        
                        self.console.print("[yellow]Exchanging authorization code for access token...[/yellow]")
                        try:
                            schwab_client.exchange_code_for_token(auth_code)
                            self.console.print(
                                Panel.fit(
                                    "[green]✓ Authorization successful![/green]\n"
                                    "[dim]Access token obtained and saved.[/dim]\n"
                                    "[dim]You can now use Schwab for data imports.[/dim]",
                                    box=box.ROUNDED,
                                    border_style="green",
                                )
                            )
                        except Exception as e:
                            self.console.print(f"[red]✗ Authorization failed: {e}[/red]")
                            logger.error(f"Auth callback error: {e}")
                    
                    elif subcmd == 'auth-status':
                        from app.integrations.schwab_client import schwab_client
                        from rich.table import Table
                        import json
                        from pathlib import Path
                        
                        # Reload tokens from disk in case they were saved after instance was created
                        schwab_client._load_tokens()
                        
                        table = Table(title="Schwab OAuth Status", box=box.ROUNDED)
                        table.add_column("Property", style="cyan")
                        table.add_column("Value", style="white")
                        
                        is_auth = schwab_client.is_authenticated()
                        table.add_row("Authenticated", "[green]Yes[/green]" if is_auth else "[red]No[/red]")
                        
                        if is_auth:
                            # Access Token Status
                            table.add_row("Access Token", f"{schwab_client.access_token[:20]}..." if schwab_client.access_token else "N/A")
                            if schwab_client.token_expires_at:
                                expires_in = (schwab_client.token_expires_at - datetime.now()).total_seconds()
                                if expires_in > 0:
                                    minutes = int(expires_in / 60)
                                    table.add_row("Access Token Expires", f"[green]{minutes} minutes[/green]")
                                else:
                                    table.add_row("Access Token Expires", "[yellow]Expired (will auto-refresh)[/yellow]")
                            
                            # Refresh Token Status
                            token_file = Path.home() / ".mismartera" / "schwab_tokens.json"
                            if token_file.exists():
                                try:
                                    with open(token_file) as f:
                                        data = json.load(f)
                                    saved_at = datetime.fromisoformat(data["saved_at"])
                                    age_seconds = (datetime.now() - saved_at).total_seconds()
                                    age_days = int(age_seconds / 86400)
                                    age_hours = int((age_seconds % 86400) / 3600)
                                    
                                    days_remaining = 7 - age_days
                                    
                                    if days_remaining > 1:
                                        table.add_row("Refresh Token", f"[green]Valid ({days_remaining} days remaining)[/green]")
                                    elif days_remaining == 1:
                                        table.add_row("Refresh Token", f"[yellow]Expires in {days_remaining} day[/yellow]")
                                    elif days_remaining == 0:
                                        table.add_row("Refresh Token", f"[red]Expires today! Re-authorize soon.[/red]")
                                    else:
                                        table.add_row("Refresh Token", f"[red]Expired - run 'schwab auth-start'[/red]")
                                    
                                    table.add_row("Token Age", f"{age_days}d {age_hours}h")
                                except:
                                    pass
                            
                            table.add_row("Token File", str(schwab_client._token_file))
                        else:
                            table.add_row("Status", "[yellow]Not authorized[/yellow]")
                            table.add_row("Next Step", "Run 'schwab auth-start'")
                        
                        self.console.print(table)
                    
                    elif subcmd == 'auth-logout':
                        from app.integrations.schwab_client import schwab_client
                        
                        if Confirm.ask("[yellow]Clear Schwab OAuth tokens?[/yellow]"):
                            schwab_client.clear_tokens()
                            self.console.print("[green]✓ Tokens cleared[/green]")
                        else:
                            self.console.print("[dim]Cancelled[/dim]")
                    
                    elif subcmd == 'disconnect':
                        self.console.print("[yellow]Disconnecting Schwab (logical only)...[/yellow]")
                        self.console.print(
                            Panel.fit(
                                "[cyan]Schwab uses OAuth 2.0 authentication.[/cyan]\n"
                                "[dim]To fully disconnect, use 'schwab auth-logout' to clear tokens, "
                                "or revoke authorization through Schwab's developer portal.[/dim]",
                                box=box.ROUNDED,
                                border_style="cyan",
                            )
                        )
                    else:
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown schwab command. Available commands:[/red]\n")
                        for meta in SCHWAB_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
            
            # ==================== EXECUTION COMMANDS (from EXECUTION_COMMANDS registry) ====================
            
            elif cmd == 'execution':
                if not args:
                    # Show available subcommands from registry
                    subcommands = [meta.name for meta in EXECUTION_COMMANDS]
                    self.console.print(f"[red]Usage: execution <{' | '.join(subcommands)}>[/red]")
                else:
                    subcmd = args[0].lower()
                    if subcmd == 'api' and len(args) >= 2:
                        # execution api <provider>
                        provider = args[1].lower()
                        from app.cli.execution_commands import select_execution_api_command
                        select_execution_api_command(provider)
                    
                    elif subcmd == 'balance':
                        # execution balance [--account <id>] [--no-sync]
                        account_id = "default"
                        no_sync = False
                        
                        # Parse optional flags
                        i = 1
                        while i < len(args):
                            if args[i] == '--account' and i + 1 < len(args):
                                account_id = args[i + 1]
                                i += 2
                            elif args[i] == '--no-sync':
                                no_sync = True
                                i += 1
                            else:
                                i += 1
                        
                        from app.cli.execution_commands import balance_command
                        balance_command(account_id, no_sync)
                    
                    elif subcmd == 'positions':
                        # execution positions [--account <id>] [--no-sync]
                        account_id = "default"
                        no_sync = False
                        
                        # Parse optional flags
                        i = 1
                        while i < len(args):
                            if args[i] == '--account' and i + 1 < len(args):
                                account_id = args[i + 1]
                                i += 2
                            elif args[i] == '--no-sync':
                                no_sync = True
                                i += 1
                            else:
                                i += 1
                        
                        from app.cli.execution_commands import positions_command
                        positions_command(account_id, no_sync)
                    
                    elif subcmd == 'orders':
                        # execution orders [--status <status>] [--days <n>]
                        account_id = "default"
                        status = None
                        days = 7
                        
                        # Parse optional flags
                        i = 1
                        while i < len(args):
                            if args[i] == '--account' and i + 1 < len(args):
                                account_id = args[i + 1]
                                i += 2
                            elif args[i] == '--status' and i + 1 < len(args):
                                status = args[i + 1].upper()
                                i += 2
                            elif args[i] == '--days' and i + 1 < len(args):
                                days = int(args[i + 1])
                                i += 2
                            else:
                                i += 1
                        
                        from app.cli.execution_commands import orders_command
                        orders_command(account_id, status, days)
                    
                    elif subcmd == 'order' and len(args) >= 3:
                        # execution order <symbol> <quantity> [--side BUY|SELL] [--type MARKET|LIMIT] [--price <price>]
                        symbol = args[1].upper()
                        quantity = float(args[2])
                        side = "BUY"
                        order_type = "MARKET"
                        price = None
                        account_id = "default"
                        
                        # Parse optional flags
                        i = 3
                        while i < len(args):
                            if args[i] == '--side' and i + 1 < len(args):
                                side = args[i + 1].upper()
                                i += 2
                            elif args[i] == '--type' and i + 1 < len(args):
                                order_type = args[i + 1].upper()
                                i += 2
                            elif args[i] == '--price' and i + 1 < len(args):
                                price = float(args[i + 1])
                                i += 2
                            elif args[i] == '--account' and i + 1 < len(args):
                                account_id = args[i + 1]
                                i += 2
                            else:
                                i += 1
                        
                        from app.cli.execution_commands import place_order_command
                        place_order_command(symbol, quantity, side, order_type, price, account_id)
                    
                    elif subcmd == 'cancel' and len(args) >= 2:
                        # execution cancel <order_id>
                        order_id = args[1]
                        
                        from app.cli.execution_commands import cancel_order_command
                        cancel_order_command(order_id)
                    
                    else:
                        # Show usage from registry (single source of truth)
                        self.console.print("[red]Unknown execution command. Available commands:[/red]\n")
                        for meta in EXECUTION_COMMANDS:
                            self.console.print(f"  [cyan]{meta.usage:<60}[/cyan] {meta.description}")
            
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
    
    def ask_claude(self, question: str):
        """Ask Claude a question"""
        if not claude_client.client:
            self.console.print("[red]Claude API not configured[/red]")
            self.console.print("[dim]Set ANTHROPIC_API_KEY in .env file[/dim]")
            return
        
        self.console.print(f"\n[yellow]Asking Claude:[/yellow] {question}\n")
        
        try:
            with self.console.status("[cyan]Thinking...", spinner="dots"):
                response = claude_client.client.messages.create(
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
    
    def analyze_stock(self, symbol: str):
        """Analyze a stock with Claude"""
        if not claude_client.client:
            self.console.print("[red]Claude API not configured[/red]")
            self.console.print("[dim]Set ANTHROPIC_API_KEY in .env file[/dim]")
            return
        
        self.console.print(f"\n[yellow]Analyzing {symbol} with Claude AI...[/yellow]\n")
        
        try:
            # Use placeholder market data since we don't have live data yet
            market_data = {
                "note": "Using Claude's knowledge base and recent market context"
            }
            
            with self.console.status(f"[cyan]Analyzing {symbol}...", spinner="dots"):
                result = claude_client.analyze_stock(
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
    
    def run(self):
        """
        Run the interactive CLI REPL
        """
        try:
            # Display banner
            self.display_banner()
            
            # Login
            if not self.login():
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
                        if not self.login():
                            break
                    
                    # Get command (use input() for readline compatibility)
                    username = self.current_user['username']
                    # Readline needs \001 and \002 markers around non-printing chars
                    # \001 = start non-printing, \002 = end non-printing
                    prompt = f"\001\x1b[1;36m\002{username}@mismartera:\001\x1b[0m\002 "
                    command = input(prompt)
                    
                    # Execute command
                    if not self.execute_command(command):
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
    cli = InteractiveCLI()
    cli.run()
