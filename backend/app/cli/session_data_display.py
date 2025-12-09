"""Session Data Display - Live monitoring based on system_info() API."""
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box

from app.logger import logger


console = Console()


def generate_session_display(compact: bool = True) -> Table:
    """Generate session data display from system_info() API.
    
    Args:
        compact: If True, use compact layout. If False, use detailed layout.
    
    Returns:
        Rich Table with session data
    """
    from app.managers.system_manager import get_system_manager
    
    # Get system status (single source of truth)
    system_mgr = get_system_manager()
    status = system_mgr.system_info(complete=True)
    
    if compact:
        return _build_compact_view(status)
    else:
        return _build_detailed_view(status)


def _build_compact_view(status: Dict[str, Any]) -> Table:
    """Build compact 1-line-per-section view."""
    
    # Extract data sections
    system_mgr_info = status.get("system_manager", {})
    time_info = status.get("time_manager", {})
    perf_info = status.get("performance_metrics", {})
    threads_info = status.get("threads", {})
    session_data_info = status.get("session_data", {})
    
    # Main table
    table = Table(
        title="SESSION DATA",
        show_header=False,
        box=box.DOUBLE,
        expand=True,
        padding=(0, 1)
    )
    table.add_column("Section", style="bold cyan", width=12)
    table.add_column("Details", style="white", no_wrap=False)
    
    # === SYSTEM ===
    state = system_mgr_info.get("_state", "unknown").upper()
    mode = system_mgr_info.get("_mode", "unknown").upper()
    exchange = system_mgr_info.get("exchange_group", "N/A")
    asset_class = system_mgr_info.get("asset_class", "N/A")
    timezone = system_mgr_info.get("timezone", "N/A")
    
    state_color = "green" if state == "RUNNING" else "yellow" if state == "PAUSED" else "red"
    mode_color = "cyan" if mode == "BACKTEST" else "blue"
    
    system_line = (
        f"State: [{state_color}]{state}[/{state_color}] | "
        f"Mode: [{mode_color}]{mode}[/{mode_color}] | "
        f"Exchange: {exchange}/{asset_class} | "
        f"TZ: {timezone}"
    )
    table.add_row("[bold]SYSTEM[/bold]", system_line)
    
    # === SESSION ===
    current_session = time_info.get("current_session", {})
    session_date = current_session.get("date", "N/A")
    session_time = current_session.get("time", "N/A")
    is_trading_day = current_session.get("is_trading_day", False)
    is_holiday = current_session.get("is_holiday", False)
    is_early_close = current_session.get("is_early_close", False)
    regular_open = current_session.get("regular_open", "N/A")
    regular_close = current_session.get("regular_close", "N/A")
    
    session_active = session_data_info.get("_session_active", False)
    active_symbols = session_data_info.get("_active_symbols", [])
    symbol_count = len(active_symbols)
    
    active_str = "[green]✓ Active[/green]" if session_active else "[yellow]⚠ Inactive[/yellow]"
    trading_str = "[green]✓ Trading[/green]" if is_trading_day else "[red]✗ Not Trading[/red]"
    holiday_str = "[red]✗ Holiday[/red]" if is_holiday else "[green]✓ Regular[/green]"
    
    session_line1 = (
        f"{session_date} | {session_time} | {active_str} | {trading_str} | {holiday_str}"
    )
    session_line2 = (
        f"Hours: {regular_open} - {regular_close} | "
        f"Early Close: {'✓' if is_early_close else '✗'} | "
        f"Symbols: {symbol_count}"
    )
    
    table.add_row("[bold]SESSION[/bold]", session_line1)
    table.add_row("", session_line2)
    
    # === BACKTEST (only if backtest mode) ===
    if mode == "BACKTEST":
        backtest_window = system_mgr_info.get("backtest_window", {})
        start_date = backtest_window.get("start_date", "N/A")
        end_date = backtest_window.get("end_date", "N/A")
        
        # Calculate progress (simplified - would need more logic)
        backtest_line = f"{start_date} → {end_date} | Speed: N/A | Progress: N/A"
        table.add_row("[bold]BACKTEST[/bold]", backtest_line)
    
    # === PERFORMANCE ===
    bars_processed = perf_info.get("bars_processed", 0)
    iterations = perf_info.get("iterations", 0)
    trading_days = perf_info.get("trading_days", 0)
    bp_coord_proc = perf_info.get("backpressure_coordinator_to_processor", 0)
    bp_proc_anal = perf_info.get("backpressure_processor_to_analysis", 0)
    
    perf_line = (
        f"Bars: {bars_processed} | Iterations: {iterations} | "
        f"Trading Days: {trading_days} | "
        f"Backpressure: Coord→Proc: {bp_coord_proc} | Proc→Anal: {bp_proc_anal}"
    )
    table.add_row("[bold]PERF[/bold]", perf_line)
    
    # === THREADS ===
    thread_status = []
    for thread_name, thread_data in threads_info.items():
        is_running = thread_data.get("_running", False)
        status_icon = "[green]✓[/green]" if is_running else "[red]✗[/red]"
        # Shorten thread names
        short_name = thread_name.replace("_", "").replace("data", "D").replace("processor", "Proc").replace("manager", "Mgr")
        thread_status.append(f"{short_name}: {status_icon}")
    
    threads_line = " | ".join(thread_status) if thread_status else "[dim]No threads[/dim]"
    table.add_row("[bold]THREADS[/bold]", threads_line)
    
    # === SYMBOLS ===
    symbols_data = session_data_info.get("symbols", {})
    
    if symbols_data:
        table.add_row("", "")  # Spacing
        table.add_row("[bold green]━━━ SYMBOLS ━━━[/bold green]", "")
        
        for symbol_name in sorted(symbols_data.keys()):
            symbol_info = symbols_data[symbol_name]
            _add_symbol_compact(table, symbol_name, symbol_info)
            table.add_row("", "")  # Spacing between symbols
    elif session_active:
        table.add_row("", "")
        table.add_row("[bold green]━━━ SYMBOLS ━━━[/bold green]", "")
        table.add_row("", "[dim]Loading symbols...[/dim]")
    else:
        table.add_row("", "")
        table.add_row("", "[dim]No symbols (session inactive)[/dim]")
    
    return table


def _add_symbol_compact(table: Table, symbol_name: str, symbol_info: Dict[str, Any]):
    """Add symbol information in compact format."""
    
    # Symbol header
    table.add_row(f"[bold cyan]{symbol_name}[/bold cyan]", "")
    
    # === METRICS ===
    metrics = symbol_info.get("metrics", {})
    volume = metrics.get("volume", 0)
    high = metrics.get("high")
    low = metrics.get("low")
    last_update = metrics.get("last_update") or "N/A"
    
    # Format last_update time only (no date)
    if last_update != "N/A" and isinstance(last_update, str) and "T" in last_update:
        try:
            dt = datetime.fromisoformat(last_update)
            last_update = dt.strftime("%H:%M:%S")
        except Exception:
            pass
    
    metrics_line = f"Vol: {volume:,.0f}"
    if high and low:
        metrics_line += f" | High: ${high:.2f} | Low: ${low:.2f}"
    metrics_line += f" | Last: {last_update}"
    
    table.add_row("  [dim]Metrics[/dim]", metrics_line)
    
    # === SESSION BARS/TICKS/QUOTES ===
    table.add_row("  [dim]Session[/dim]", "")
    
    # Bars
    bars_data = symbol_info.get("bars", {})
    if bars_data:
        for interval, interval_data in sorted(bars_data.items()):
            _add_data_type_line(table, interval, interval_data, "bars")
    else:
        table.add_row("    [dim]--[/dim]", "[dim]No bar data[/dim]")
    
    # Ticks
    ticks_data = symbol_info.get("ticks", {})
    if ticks_data:
        count = ticks_data.get("count", 0)
        if count > 0:
            table.add_row("    [yellow]Ticks[/yellow]", f"{count} items")
    
    # Quotes
    quotes_data = symbol_info.get("quotes", {})
    if quotes_data:
        count = quotes_data.get("count", 0)
        if count > 0:
            table.add_row("    [yellow]Quotes[/yellow]", f"{count} items")
    
    # === HISTORICAL ===
    historical = symbol_info.get("historical", {})
    if historical.get("loaded", False):
        table.add_row("  [dim]Historical[/dim]", "")
        
        hist_bars = historical.get("bars", {})
        for interval, interval_data in sorted(hist_bars.items()):
            count = interval_data.get("count", 0)
            quality = interval_data.get("quality", 0.0)
            date_range = interval_data.get("date_range", {})
            gaps_info = interval_data.get("gaps", {})
            
            if count > 0:
                start_date = date_range.get("start_date", "")
                end_date = date_range.get("end_date", "")
                days = date_range.get("days", 0)
                
                # Format dates (abbreviate)
                date_str = ""
                if start_date and end_date:
                    try:
                        start_dt = datetime.fromisoformat(start_date)
                        end_dt = datetime.fromisoformat(end_date)
                        date_str = f"{start_dt.strftime('%b %d')}-{end_dt.strftime('%b %d')} ({days}d)"
                    except:
                        date_str = f"{start_date} - {end_date} ({days}d)"
                
                # Build historical line with quality and gaps
                parts = [f"{count:,} bars"]
                
                if date_str:
                    parts.append(date_str)
                
                # Quality (color coded)
                if quality >= 95:
                    parts.append(f"[green]Q: {quality:.1f}%[/green]")
                elif quality >= 80:
                    parts.append(f"[yellow]Q: {quality:.1f}%[/yellow]")
                elif quality > 0:
                    parts.append(f"[red]Q: {quality:.1f}%[/red]")
                
                # Gaps
                gap_count = gaps_info.get("gap_count", 0)
                if gap_count > 0:
                    missing_bars = gaps_info.get("missing_bars", 0)
                    parts.append(f"[yellow]{gap_count} gap{'s' if gap_count > 1 else ''} ({missing_bars} missing)[/yellow]")
                
                hist_line = " | ".join(parts)
                table.add_row(f"    [yellow]{interval}[/yellow]", hist_line)


def _add_data_type_line(table: Table, interval: str, data: Dict[str, Any], data_type: str):
    """Add a single data type line (bars/ticks/quotes) with time window."""
    
    count = data.get("count", 0)
    quality = data.get("quality", 0.0)
    
    # Get time window from data array (timestamps are in the data rows)
    time_window = ""
    data_array = data.get("data", [])
    
    if data_array and len(data_array) > 0:
        try:
            # First timestamp is in the first row, first column
            first_time = data_array[0][0] if isinstance(data_array[0], list) else None
            # Last timestamp is in the last row, first column
            last_time = data_array[-1][0] if isinstance(data_array[-1], list) else None
            
            if first_time and last_time:
                # Format times (extract HH:MM if they contain more)
                if isinstance(first_time, str):
                    if "T" in first_time:
                        first_t = first_time.split("T")[1][:5]  # HH:MM from ISO
                    else:
                        first_t = first_time[:5]  # Already HH:MM:SS -> take HH:MM
                else:
                    first_t = str(first_time)[:5]
                
                if isinstance(last_time, str):
                    if "T" in last_time:
                        last_t = last_time.split("T")[1][:5]  # HH:MM from ISO
                    else:
                        last_t = last_time[:5]  # Already HH:MM:SS -> take HH:MM
                else:
                    last_t = str(last_time)[:5]
                
                time_window = f"{first_t}-{last_t}"
        except Exception as e:
            # If anything goes wrong, just don't show time window
            pass
    
    # Build line
    parts = [f"{count} {data_type}"]
    
    # Quality (color coded)
    if quality >= 95:
        quality_str = f"[green]Q: {quality:.1f}%[/green]"
    elif quality >= 80:
        quality_str = f"[yellow]Q: {quality:.1f}%[/yellow]"
    else:
        quality_str = f"[red]Q: {quality:.1f}%[/red]"
    parts.append(quality_str)
    
    # Time window
    if time_window:
        parts.append(time_window)
    
    # Gaps
    gaps_info = data.get("gaps", {})
    gap_count = gaps_info.get("gap_count", 0)
    if gap_count > 0:
        missing_bars = gaps_info.get("missing_bars", 0)
        parts.append(f"[yellow]{gap_count} gap{'s' if gap_count > 1 else ''} ({missing_bars} missing)[/yellow]")
    
    line_text = " | ".join(parts)
    table.add_row(f"    [yellow]{interval}[/yellow]", line_text)


def _build_detailed_view(status: Dict[str, Any]) -> Table:
    """Build detailed tree view (placeholder for now)."""
    # For now, just return compact view
    # TODO: Implement full detailed tree structure
    return _build_compact_view(status)


def data_session_command(
    refresh_seconds: Optional[int] = None,
    csv_file: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    no_live: bool = False
):
    """Display session data with optional auto-refresh.
    
    Args:
        refresh_seconds: Auto-refresh interval (None/1 = 1s, 0 = once)
        csv_file: CSV file path (not yet implemented in new version)
        duration_seconds: Duration to run in seconds (not yet implemented)
        no_live: If True, print each refresh instead of live updating
    """
    # Default refresh to 1 second
    if refresh_seconds is None:
        refresh_seconds = 1
    
    # CSV and duration not yet implemented in new version
    if csv_file is not None:
        console.print("[yellow]Note: CSV export not yet implemented in new display version[/yellow]")
    if duration_seconds is not None:
        console.print("[yellow]Note: Duration limit not yet implemented in new display version[/yellow]")
    
    try:
        if refresh_seconds == 0:
            # Display once
            table = generate_session_display(compact=True)
            console.print(table)
        else:
            # Live refresh mode
            if no_live:
                # Print mode: clear and reprint
                import os
                while True:
                    os.system('clear' if os.name == 'posix' else 'cls')
                    table = generate_session_display(compact=True)
                    console.print(table)
                    time.sleep(refresh_seconds)
            else:
                # Live mode: smooth updates
                with Live(generate_session_display(compact=True), 
                         console=console, refresh_per_second=1) as live:
                    while True:
                        time.sleep(refresh_seconds)
                        live.update(generate_session_display(compact=True))
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Display stopped by user[/yellow]")
    except Exception as e:
        logger.error(f"Error in session display: {e}", exc_info=True)
        console.print(f"\n[red]Error: {e}[/red]")
