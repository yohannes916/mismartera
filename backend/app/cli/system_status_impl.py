"""Comprehensive System Status Implementation

This module contains the detailed implementation for the 'system status' command.
"""
from rich.console import Console
from rich.table import Table
from rich import box
from datetime import datetime, date
from typing import Optional

from app.managers.system_manager import get_system_manager, SystemState
from app.managers.data_manager.session_data import get_session_data
# Old backtest_stream_coordinator removed - SessionCoordinator is used now
from app.models.database import SessionLocal
from app.config import settings
from app.logger import logger


console = Console()


def show_comprehensive_status() -> None:
    """Display comprehensive system status with all details."""
    
    system_mgr = get_system_manager()
    data_mgr = system_mgr.get_data_manager() if hasattr(system_mgr, 'get_data_manager') else None
    session_data = get_session_data()
    
    # Auto-initialize backtest if in backtest mode and not initialized
    # CRITICAL: backtest_start_date is ONLY in TimeManager (single source of truth)
    if system_mgr.mode.value == "backtest":
        try:
            time_mgr = system_mgr.get_time_manager()
            if time_mgr.backtest_start_date is None:
                with SessionLocal() as session:
                    time_mgr.init_backtest(session)
                    logger.info("Auto-initialized backtest for system status display")
        except Exception as e:
            logger.warning(f"Could not auto-initialize backtest: {e}")
    
    # Title
    console.print("\n")
    console.print("═" * 73, style="cyan")
    console.print("SYSTEM STATUS".center(73), style="bold cyan")
    console.print("═" * 73, style="cyan")
    console.print()
    
    # ==================== SYSTEM MANAGER ====================
    sys_table = Table(title="System Manager", show_header=True, header_style="bold cyan", box=box.ROUNDED)
    sys_table.add_column("Property", style="cyan", width=25)
    sys_table.add_column("Value", style="white")
    
    # State
    state_color = {
        SystemState.RUNNING: "green",
        SystemState.PAUSED: "yellow",
        SystemState.STOPPED: "red",
    }.get(system_mgr.state, "white")
    sys_table.add_row("State", f"[{state_color}]{system_mgr.state.value.upper()}[/{state_color}]")
    
    # Operation mode
    mode_color = "cyan" if system_mgr.mode.value == "backtest" else "green"
    sys_table.add_row("Mode", f"[{mode_color}]{system_mgr.mode.value.upper()}[/{mode_color}]")
    
    # Initialized (check if core managers are created)
    is_initialized = (
        system_mgr._time_manager is not None and 
        system_mgr._data_manager is not None
    )
    init_status = "Yes" if is_initialized else "No"
    init_color = "green" if is_initialized else "yellow"
    sys_table.add_row("Initialized", f"[{init_color}]{init_status}[/{init_color}]")
    
    # Current time (get from TimeManager - single source of truth)
    try:
        time_mgr = system_mgr.get_time_manager()
        current_time = time_mgr.get_current_time()
        time_str = current_time.strftime("%Y-%m-%d %H:%M:%S ET")
        if system_mgr.mode.value == "backtest":
            time_str += " [dim](simulated)[/dim]"
        sys_table.add_row("System Time", time_str)
    except Exception as e:
        sys_table.add_row("System Time", "[yellow]TimeManager not available[/yellow]")
    
    console.print(sys_table)
    console.print()
    
    # ==================== MANAGERS STATUS ====================
    mgr_table = Table(title="Managers Status", show_header=True, header_style="bold magenta", box=box.ROUNDED)
    mgr_table.add_column("Manager", style="magenta", width=20)
    mgr_table.add_column("Status", style="white", width=15)
    mgr_table.add_column("Details", style="dim")
    
    # DataManager
    if system_mgr._data_manager is not None:
        # Do real-time connection check
        dm_connected = False
        if data_mgr.data_api.lower() == "alpaca":
            from app.integrations.alpaca_client import alpaca_client
            try:
                dm_connected = alpaca_client.validate_connection()
            except Exception:
                dm_connected = False
        elif data_mgr.data_api.lower() == "schwab":
            from app.integrations.schwab_client import schwab_client
            try:
                dm_connected = schwab_client.validate_connection()
            except Exception:
                dm_connected = False
        
        dm_connected_str = "Yes" if dm_connected else "No"
        mgr_table.add_row(
            "DataManager",
            "[green]✓ ACTIVE[/green]",
            f"Provider: {data_mgr.data_api}, Connected: {dm_connected_str}"
        )
    else:
        mgr_table.add_row("DataManager", "[red]✗ INACTIVE[/red]", "Not initialized")
    
    # ExecutionManager
    if system_mgr._execution_manager is not None:
        mgr_table.add_row("ExecutionManager", "[yellow]⚠ STUB[/yellow]", "Not yet implemented")
    else:
        mgr_table.add_row("ExecutionManager", "[red]✗ INACTIVE[/red]", "Not initialized")
    
    # AnalysisEngine
    if system_mgr._analysis_engine is not None:
        mgr_table.add_row("AnalysisEngine", "[yellow]⚠ STUB[/yellow]", "Not yet implemented")
    else:
        mgr_table.add_row("AnalysisEngine", "[red]✗ INACTIVE[/red]", "Not initialized")
    
    console.print(mgr_table)
    console.print()
    
    # ==================== DATA MANAGER DETAILS ====================
    if data_mgr is not None:
        _show_data_manager_details(data_mgr, system_mgr)
    
    # ==================== MARKET STATUS ====================
    _show_market_status(system_mgr)
    
    # ==================== SESSION DATA ====================
    _show_session_data(session_data)
    
    # ==================== BACKTEST COORDINATOR ====================
    if system_mgr.mode.value == "backtest" and data_mgr:
        _show_coordinator_status(system_mgr)
    
    # ==================== CONFIGURATION FLAGS ====================
    _show_configuration_flags()
    
    # ==================== HEALTH INDICATORS ====================
    _show_health_indicators(system_mgr, data_mgr, session_data)
    
    # ==================== HINTS ====================
    _show_hints(system_mgr)


def _show_data_manager_details(data_mgr, system_mgr):
    """Display Data Manager details."""
    dm_table = Table(title="Data Manager Details", show_header=True, header_style="bold blue", box=box.ROUNDED)
    dm_table.add_column("Property", style="blue", width=25)
    dm_table.add_column("Value", style="white")
    
    # Provider info
    dm_table.add_row("Data API Provider", data_mgr.data_api)
    
    # Do real-time connection check instead of relying on stale variable
    provider_connected = False
    if data_mgr.data_api.lower() == "alpaca":
        from app.integrations.alpaca_client import alpaca_client
        try:
            provider_connected = alpaca_client.validate_connection()
        except Exception:
            provider_connected = False
    elif data_mgr.data_api.lower() == "schwab":
        from app.integrations.schwab_client import schwab_client
        try:
            provider_connected = schwab_client.validate_connection()
        except Exception:
            provider_connected = False
    
    provider_status = "[green]Yes[/green]" if provider_connected else "[red]No[/red]"
    dm_table.add_row("Provider Connected", provider_status)
    dm_table.add_row("Operation Mode", system_mgr.mode.value.upper())
    
    # Current time (get from TimeManager - single source of truth)
    try:
        time_mgr = system_mgr.get_time_manager()
        current_time = time_mgr.get_current_time()
        time_str = current_time.strftime("%Y-%m-%d %H:%M:%S ET")
        if system_mgr.mode.value == "backtest":
            time_str += " [dim](simulated)[/dim]"
        dm_table.add_row("Current Time", time_str)
    except Exception as e:
        dm_table.add_row("Current Time", "[yellow]TimeManager not available[/yellow]")
    
    # Backtest configuration
    if system_mgr.mode.value == "backtest":
        dm_table.add_row("", "")  # Spacing
        dm_table.add_row("[bold]Backtest Configuration[/bold]", "")
        time_mgr = system_mgr.get_time_manager()
        if time_mgr.backtest_start_date and time_mgr.backtest_end_date:
            dm_table.add_row("  └─ Start Date", time_mgr.backtest_start_date.strftime("%Y-%m-%d"))
            dm_table.add_row("  └─ End Date", time_mgr.backtest_end_date.strftime("%Y-%m-%d"))
        else:
            dm_table.add_row("  └─ Window", "[dim]Not configured[/dim]")
        speed = system_mgr.session_config.backtest_config.speed_multiplier if system_mgr.session_config and system_mgr.session_config.backtest_config else 0.0
        dm_table.add_row("  └─ Speed Multiplier", f"{speed}x")
    
    # Active streams
    dm_table.add_row("", "")  # Spacing
    dm_table.add_row("[bold]Active Streams[/bold]", "")
    
    bar_stream_count = len(data_mgr._bar_stream_cancel_tokens)
    if bar_stream_count > 0:
        stream_list = ", ".join([k for k in data_mgr._bar_stream_cancel_tokens.keys()])
        dm_table.add_row("  └─ Bar Streams", f"{bar_stream_count} active ({stream_list})")
    else:
        dm_table.add_row("  └─ Bar Streams", "0 active")
    
    tick_stream_count = len(data_mgr._tick_stream_cancel_tokens)
    dm_table.add_row("  └─ Tick Streams", f"{tick_stream_count} active")
    
    quote_stream_count = len(data_mgr._quote_stream_cancel_tokens)
    dm_table.add_row("  └─ Quote Streams", f"{quote_stream_count} active")
    
    console.print(dm_table)
    console.print()


def _show_market_status(system_mgr):
    """Display market status."""
    try:
        time_mgr = system_mgr.get_time_manager()
        current_time = time_mgr.get_current_time()
        current_date = current_time.date()
        
        with SessionLocal() as session:
            trading_session = time_mgr.get_trading_session(session, current_date)
            is_holiday = time_mgr.is_holiday(session, current_date)
        
        market_table = Table(title="Market Status", show_header=True, header_style="bold green", box=box.ROUNDED)
        market_table.add_column("Property", style="green", width=25)
        market_table.add_column("Value", style="white")
        
        # Format time helper
        def format_time(dt_val):
            if dt_val is None:
                return "N/A"
            if isinstance(dt_val, datetime):
                return dt_val.strftime("%H:%M:%S")
            else:
                return dt_val.strftime("%H:%M:%S")
        
        market_table.add_row("Current Time", f"{current_time.strftime('%H:%M:%S')} ET")
        market_table.add_row("Date", f"{current_date.strftime('%Y-%m-%d')} ({current_date.strftime('%a')})")
        
        # Market day type
        is_weekend = current_date.weekday() >= 5
        if is_weekend:
            market_table.add_row("Today", "Weekend")
        elif is_holiday:
            holiday_name = trading_session.holiday_name if trading_session else None
            market_table.add_row("Today", f"Holiday: {holiday_name or 'Market Closed'}")
        else:
            market_table.add_row("Today", "Regular trading day")
        
        # Market hours
        if trading_session and not trading_session.is_holiday:
            open_time = format_time(trading_session.regular_open)
            close_time = format_time(trading_session.regular_close)
            market_table.add_row("Market Hours", f"{open_time} - {close_time} ET")
        
        # Market status
        with SessionLocal() as session:
            is_market_open = time_mgr.is_market_open(session, current_time)
        
        if is_market_open:
            market_table.add_row("Market Status", "[green]✓ OPEN[/green]")
        else:
            market_table.add_row("Market Status", "[red]✗ CLOSED[/red]")
        
        console.print(market_table)
        console.print()
    
    except Exception as e:
        logger.error(f"Error getting market status: {e}", exc_info=True)
        console.print(f"[red]✗ Error getting market status: {str(e)}[/red]\n")


def _show_session_data(session_data):
    """Display session data details."""
    if not session_data:
        return
    
    session_table = Table(title="Session Data", show_header=True, header_style="bold yellow", box=box.ROUNDED)
    session_table.add_column("Property", style="yellow", width=25)
    session_table.add_column("Value", style="white")
    
    # Session date and time (from TimeProvider, single source of truth)
    current_date = session_data.get_current_session_date()
    is_active = session_data.is_session_active()
    
    # Get current time from TimeManager
    try:
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        time_mgr = system_mgr.get_time_manager()
        current_time = time_mgr.get_current_time()
        session_time_str = current_time.strftime("%H:%M:%S")
    except Exception as e:
        session_time_str = "N/A"
    
    if current_date:
        session_table.add_row("Session Date", current_date.strftime("%Y-%m-%d"))
        session_table.add_row("Session Time", session_time_str)
        session_table.add_row("Session Active", "[green]Yes[/green]" if is_active else "[yellow]No[/yellow]")
    else:
        session_table.add_row("Session Date", "[yellow]No active session[/yellow]")
        session_table.add_row("Session Time", session_time_str)
        session_table.add_row("Session Active", "[red]No[/red]")
    
    # Active symbols
    active_symbols = session_data.get_active_symbols()
    session_table.add_row("Active Symbols", f"{len(active_symbols)} symbols")
    
    # Per-symbol details
    if active_symbols:
        session_table.add_row("", "")  # Spacing
        session_table.add_row("[bold]Symbol Details[/bold]", "")
        
        for symbol in sorted(active_symbols):
            try:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data:
                    session_table.add_row(f"  ┌─ {symbol}", "")
                    
                    # Current session bars (bars_1m)
                    current_bars = symbol_data.get_bar_count(1)
                    session_table.add_row(f"  │  └─ Current Session Bars", f"{current_bars} bars")
                    
                    # Historical bars count
                    hist_bar_count = 0
                    hist_days_count = 0
                    if hasattr(symbol_data, 'historical_bars') and 1 in symbol_data.historical_bars:
                        hist_days_count = len(symbol_data.historical_bars[1])
                        for date_bars in symbol_data.historical_bars[1].values():
                            hist_bar_count += len(date_bars)
                    
                    if hist_bar_count > 0:
                        session_table.add_row(f"  │  └─ Historical Bars", f"{hist_bar_count} bars ({hist_days_count} days)")
                    
                    session_table.add_row(f"  │  └─ Session Volume", f"{symbol_data.session_volume:,}")
                    
                    if symbol_data.session_high:
                        session_table.add_row(f"  │  └─ Session High", f"{symbol_data.session_high:.2f}")
                    if symbol_data.session_low:
                        session_table.add_row(f"  │  └─ Session Low", f"{symbol_data.session_low:.2f}")
                    
                    # Display quality for base interval (bar_quality is now Dict[str, float])
                    if symbol_data.bar_quality and symbol_data.base_interval in symbol_data.bar_quality:
                        quality_value = symbol_data.bar_quality[symbol_data.base_interval]
                        quality_color = "green" if quality_value >= 95 else "yellow" if quality_value >= 80 else "red"
                        session_table.add_row(f"  │  └─ Bar Quality ({symbol_data.base_interval})", f"[{quality_color}]{quality_value:.1f}%[/{quality_color}]")
                    
                    if symbol_data.last_update:
                        session_table.add_row(f"  │  └─ Last Update", symbol_data.last_update.strftime("%H:%M:%S"))
            except Exception as e:
                logger.debug(f"Error getting symbol data for {symbol}: {e}")
    
    # Historical bars configuration
    if hasattr(session_data, 'historical_bars_trailing_days'):
        session_table.add_row("", "")  # Spacing
        session_table.add_row("[bold]Historical Bars Config[/bold]", "")
        session_table.add_row("  └─ Trailing Days", f"{session_data.historical_bars_trailing_days} days")
        
        if hasattr(session_data, 'historical_bars_intervals') and session_data.historical_bars_intervals:
            intervals_str = ", ".join([f"{i}m" for i in session_data.historical_bars_intervals])
            session_table.add_row("  └─ Intervals", intervals_str)
        
        # Count total historical bars across all symbols
        total_bars = 0
        total_days = set()
        for symbol in active_symbols:
            try:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data and hasattr(symbol_data, 'historical_bars'):
                    for interval_bars in symbol_data.historical_bars.values():
                        for bar_date, date_bars in interval_bars.items():
                            total_bars += len(date_bars)
                            total_days.add(bar_date)
            except:
                pass
        
        if total_bars > 0:
            session_table.add_row("  └─ Total Loaded", f"{total_bars:,} bars ({len(total_days)} unique dates)")
    
    console.print(session_table)
    console.print()


def _show_coordinator_status(system_mgr):
    """Display backtest stream coordinator status."""
    try:
        # Get SessionCoordinator from system manager
        coordinator = system_mgr._session_coordinator if hasattr(system_mgr, '_session_coordinator') else None
        
        if not coordinator:
            return
        
        coord_table = Table(title="Backtest Stream Coordinator", show_header=True, header_style="bold purple", box=box.ROUNDED)
        coord_table.add_column("Property", style="purple", width=25)
        coord_table.add_column("Value", style="white")
        
        # Worker status
        if hasattr(coordinator, '_worker_thread') and coordinator._worker_thread and coordinator._worker_thread.is_alive():
            coord_table.add_row("Worker Thread", "[green]Running[/green]")
        else:
            coord_table.add_row("Worker Thread", "[red]Stopped[/red]")
        
        # Time advancement
        if system_mgr.is_running():
            coord_table.add_row("Time Advancement", "[green]Active (respects system state)[/green]")
        else:
            coord_table.add_row("Time Advancement", "[yellow]Paused (system not running)[/yellow]")
        
        # Data upkeep status
        if hasattr(coordinator, '_upkeep_thread') and coordinator._upkeep_thread:
            upkeep = coordinator._upkeep_thread
            if hasattr(upkeep, '_running') and upkeep._running:
                coord_table.add_row("Data Upkeep Thread", "[green]Running[/green]")
            else:
                coord_table.add_row("Data Upkeep Thread", "[red]Stopped[/red]")
        
        console.print(coord_table)
        console.print()
    
    except Exception as e:
        logger.debug(f"Error getting coordinator status: {e}")


def _show_configuration_flags():
    """Display configuration flags."""
    config_table = Table(title="Configuration Flags", show_header=True, header_style="bold white", box=box.ROUNDED)
    config_table.add_column("Category", style="white", width=25)
    config_table.add_column("Value", style="dim")
    
    # System
    config_table.add_row("[bold]System[/bold]", "")
    config_table.add_row("  └─ Operating Mode", settings.SYSTEM.operating_mode)
    config_table.add_row("  └─ Debug Mode", "True" if settings.DEBUG else "False")
    config_table.add_row("  └─ Alpaca Paper Trading", "True" if settings.ALPACA.paper_trading else "False")
    
    # Note: Session configuration now comes from session JSON files, not environment variables
    
    console.print(config_table)
    console.print()


def _show_health_indicators(system_mgr, data_mgr, session_data):
    """Display health indicators."""
    health_table = Table(title="Health Indicators", show_header=False, box=box.ROUNDED)
    health_table.add_column("Status", style="white")
    
    # Check system state
    if system_mgr.state == SystemState.RUNNING:
        health_table.add_row("[green]✓ System is running[/green]")
    elif system_mgr.state == SystemState.PAUSED:
        health_table.add_row("[yellow]⚠ System is paused[/yellow]")
    else:
        health_table.add_row("[yellow]⚠ System is stopped[/yellow]")
    
    # Check initialization (check if core managers are created)
    is_initialized = (
        system_mgr._time_manager is not None and 
        system_mgr._data_manager is not None
    )
    if is_initialized:
        health_table.add_row("[green]✓ All managers initialized[/green]")
    else:
        health_table.add_row("[yellow]⚠ Managers not fully initialized[/yellow]")
    
    # Check data provider with real-time check
    provider_connected = False
    if data_mgr:
        if data_mgr.data_api.lower() == "alpaca":
            from app.integrations.alpaca_client import alpaca_client
            try:
                provider_connected = alpaca_client.validate_connection()
            except Exception:
                provider_connected = False
        elif data_mgr.data_api.lower() == "schwab":
            from app.integrations.schwab_client import schwab_client
            try:
                provider_connected = schwab_client.validate_connection()
            except Exception:
                provider_connected = False
    
    if provider_connected:
        health_table.add_row("[green]✓ Data provider connected[/green]")
    else:
        health_table.add_row("[yellow]⚠ Data provider not connected[/yellow]")
    
    # TimeProvider is always available (singleton, single source of truth)
    # No need to check - it's always initialized
    
    # Check session data
    if session_data and session_data.is_session_active():
        health_table.add_row("[green]✓ Session active[/green]")
    else:
        health_table.add_row("[yellow]⚠ No active session[/yellow]")
    
    # Check streams
    if data_mgr and len(data_mgr._bar_stream_cancel_tokens) > 0:
        health_table.add_row("[green]✓ Streams active and flowing[/green]")
    
    console.print(health_table)
    console.print()


def _show_hints(system_mgr):
    """Display action hints based on system state."""
    console.print("[bold]Hints:[/bold]")
    
    if system_mgr.state == SystemState.STOPPED:
        console.print("  • Use [cyan]'system start'[/cyan] to start the system")
    elif system_mgr.state == SystemState.RUNNING:
        console.print("  • Use [cyan]'system pause'[/cyan] to pause streaming")
        console.print("  • Use [cyan]'system stop'[/cyan] to stop all operations")
        console.print("  • Use [cyan]'data stop-all-streams'[/cyan] to stop streams manually")
    elif system_mgr.state == SystemState.PAUSED:
        console.print("  • Use [cyan]'system resume'[/cyan] to continue operations")
        console.print("  • Use [cyan]'system stop'[/cyan] to stop completely")
    
    console.print()
