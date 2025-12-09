"""Session Data Display - Live monitoring based on system status JSON."""
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box

from app.logger import logger


console = Console()


def generate_session_display(compact: bool = True) -> Table:
    """Generate the complete session data display table from system status JSON.
    
    Args:
        compact: If True, use compact 2-column layout. If False, use detailed tree layout.
    
    Returns:
        Rich Table with all session data information
    """
    from app.managers.system_manager import get_system_manager
    
    # Get system status JSON (single source of truth)
    system_mgr = get_system_manager()
    status = system_mgr.system_info(complete=True)
    
    # Extract key information from status JSON
    system_info = status.get("system_info", {})
    session_data_info = status.get("session_data", {})
    time_info = status.get("time_manager", {})
    
    state = system_info.get("state", "unknown")
    mode = system_info.get("mode", "unknown")
    
    # Main container
    main_table = Table(
        title="SESSION DATA",
        show_header=False,
        box=box.DOUBLE,
        expand=True,
        padding=(0, 1)
    )
    
    if compact:
        # Compact mode: 2 columns
        main_table.add_column("Section", style="bold yellow", width=24)
        main_table.add_column("Details", style="white", no_wrap=False)
    else:
        # Full mode: Tree layout
        main_table.add_column("Property", style="yellow", width=35)
        main_table.add_column("Value", style="white", width=60)
    
    # === SYSTEM STATUS ===
    state_color = "green" if state == "running" else "yellow" if state == "paused" else "red"
    mode_color = "cyan" if mode == "backtest" else "blue"
    
    current_date_str = session_data_info.get("current_session_date", "N/A")
    is_active = session_data_info.get("session_active", False)
    active_status = "[green]✓ Active[/green]" if is_active else "[yellow]⚠ Inactive[/yellow]"
    
    # Get current time from time_manager info
    current_time_str = time_info.get("current_time", "N/A")
    if current_time_str != "N/A":
        try:
            # Parse and format as HH:MM:SS
            dt = datetime.fromisoformat(current_time_str)
            session_time_str = dt.strftime("%H:%M:%S")
        except:
            session_time_str = "N/A"
    else:
        session_time_str = "N/A"
    
    # Get symbols from session data
    symbols_data = session_data_info.get("symbols", {})
    symbol_count = len(symbols_data)
    
    # Calculate overall quality from symbols
    overall_quality = None
    if symbols_data:
        total_quality = 0.0
        total_weight = 0.0
        for symbol_info in symbols_data.values():
            bars_info = symbol_info.get("bars", {})
            base_interval = symbol_info.get("base_interval", "1m")
            base_data = bars_info.get(base_interval, {})
            quality = base_data.get("quality", 0.0)
            if quality > 0:
                total_quality += quality
                total_weight += 1.0
        if total_weight > 0:
            overall_quality = total_quality / total_weight
    
    # === BUILD DISPLAY ===
    if compact:
        # === COMPACT MODE ===
        
        # System and session header
        session_info_parts = [current_date_str, session_time_str, active_status, f"Symbols: {symbol_count}"]
        
        if overall_quality is not None:
            quality_color = "green" if overall_quality >= 95 else "yellow" if overall_quality >= 80 else "red"
            session_info_parts.append(f"Quality: [{quality_color}]{overall_quality:.1f}%[/{quality_color}]")
        
        session_info = " | ".join(session_info_parts)
        
        main_table.add_row(
            "[bold]SYSTEM[/bold]",
            f"State: [{state_color}]{state.upper()}[/{state_color}] | Mode: [{mode_color}]{mode.upper()}[/{mode_color}]"
        )
        main_table.add_row(
            "[bold]SESSION[/bold]",
            session_info
        )
        
        # === SYMBOLS ===
        if symbols_data:
            main_table.add_row("", "")
            main_table.add_row("[bold green]━━ SYMBOLS ━━[/bold green]", "")
            
            for symbol, symbol_info in sorted(symbols_data.items()):
                # Symbol header with metrics
                metrics = symbol_info.get("metrics", {})
                volume = metrics.get("volume", 0)
                high = metrics.get("high")
                low = metrics.get("low")
                
                metrics_str = f"Vol: {volume:,.0f}"
                if high and low:
                    metrics_str += f" | High: ${high:.2f} | Low: ${low:.2f}"
                
                main_table.add_row(f"[bold cyan]{symbol}[/bold cyan]", metrics_str)
                
                # Bar intervals
                bars_info = symbol_info.get("bars", {})
                base_interval = symbol_info.get("base_interval", "1m")
                
                # Sort intervals: base first, then by numeric value
                def interval_sort_key(item):
                    interval_key = item[0]
                    if interval_key == base_interval:
                        return (0, 0)  # Base goes first
                    try:
                        # Extract numeric part (e.g., "5m" -> 5)
                        num = int(interval_key[:-1]) if interval_key.endswith('m') else 999
                        return (1, num)  # Derived intervals sorted by size
                    except:
                        return (2, 999)  # Unknown format goes last
                
                for interval_key, interval_data in sorted(bars_info.items(), key=interval_sort_key):
                    # Build interval line
                    count = interval_data.get("bar_count", 0)
                    quality = interval_data.get("quality", 0.0)
                    is_derived = interval_data.get("derived", False)
                    base = interval_data.get("base")
                    first_time = interval_data.get("first_bar_time", "")
                    last_time = interval_data.get("last_bar_time", "")
                    
                    # Quality color
                    quality_color = "green" if quality >= 95 else "yellow" if quality >= 80 else "red"
                    
                    # Build display string
                    parts = [f"{count} bars"]
                    
                    if first_time and last_time:
                        # Format time range without full datetime
                        try:
                            first_t = first_time.split('T')[1][:5] if 'T' in first_time else first_time[:5]
                            last_t = last_time.split('T')[1][:5] if 'T' in last_time else last_time[:5]
                            parts.append(f"{first_t}-{last_t}")
                        except:
                            pass
                    
                    parts.append(f"Q: [{quality_color}]{quality:.1f}%[/{quality_color}]")
                    
                    if is_derived and base:
                        parts.append(f"← {base}")
                    elif not is_derived:
                        parts.append("✓ Base")
                    
                    # Check for gaps
                    gaps_info = interval_data.get("gaps", {})
                    gap_count = gaps_info.get("gap_count", 0)
                    if gap_count > 0:
                        missing = gaps_info.get("missing_bars", 0)
                        parts.append(f"[yellow]⚠{gap_count} gaps ({missing} bars)[/yellow]")
                    
                    interval_str = " | ".join(parts)
                    main_table.add_row(f"  {interval_key}", interval_str)
                
                main_table.add_row("", "")  # Spacing between symbols
        else:
            main_table.add_row("", "[dim]No symbols[/dim]")
    
    else:
        # === FULL MODE ===
        
        # System info
        main_table.add_row("System State", f"[{state_color}]{state.upper()}[/{state_color}]")
        main_table.add_row("Operation Mode", f"[{mode_color}]{mode.upper()}[/{mode_color}]")
        main_table.add_row("", "")
        
        # Session info
        main_table.add_row("Session Date", current_date_str)
        main_table.add_row("Session Time", f"[bold cyan]{session_time_str}[/bold cyan]")
        main_table.add_row("Session Active", active_status)
        main_table.add_row("Active Symbols", f"{symbol_count} symbols")
        
        if overall_quality is not None:
            quality_color = "green" if overall_quality >= 95 else "yellow" if overall_quality >= 80 else "red"
            main_table.add_row("Overall Quality", f"[{quality_color}]{overall_quality:.1f}%[/{quality_color}]")
        
        # === SYMBOLS ===
        if symbols_data:
            main_table.add_row("", "")
            main_table.add_row("[bold green]┌─ SYMBOLS[/bold green]", "")
            main_table.add_row("│", "")
            
            for idx, (symbol, symbol_info) in enumerate(sorted(symbols_data.items())):
                is_last_symbol = (idx == len(symbols_data) - 1)
                
                main_table.add_row(f"│  [bold]┌─ {symbol}[/bold]", "")
                
                # Metrics
                metrics = symbol_info.get("metrics", {})
                main_table.add_row(f"│  │  Metrics", "")
                main_table.add_row(f"│  │  ├─ Volume", f"{metrics.get('volume', 0):,.0f}")
                if metrics.get("high"):
                    main_table.add_row(f"│  │  ├─ High", f"${metrics['high']:.2f}")
                if metrics.get("low"):
                    main_table.add_row(f"│  │  └─ Low", f"${metrics['low']:.2f}")
                
                # Bars
                main_table.add_row(f"│  │", "")
                main_table.add_row(f"│  │  Bars", "")
                
                bars_info = symbol_info.get("bars", {})
                base_interval = symbol_info.get("base_interval", "1m")
                
                # Sort intervals: base first, then by numeric value
                def interval_sort_key(item):
                    interval_key = item[0]
                    if interval_key == base_interval:
                        return (0, 0)
                    try:
                        num = int(interval_key[:-1]) if interval_key.endswith('m') else 999
                        return (1, num)
                    except:
                        return (2, 999)
                
                intervals = sorted(bars_info.items(), key=interval_sort_key)
                
                for interval_idx, (interval_key, interval_data) in enumerate(intervals):
                    is_last_interval = (interval_idx == len(intervals) - 1)
                    prefix = "└─" if is_last_interval else "├─"
                    
                    # Interval header
                    is_derived = interval_data.get("derived", False)
                    base = interval_data.get("base")
                    
                    if is_derived and base:
                        header = f"{interval_key} (Derived from {base})"
                    else:
                        header = f"{interval_key} (Base)"
                    
                    main_table.add_row(f"│  │  {prefix} {header}", "")
                    
                    # Interval details
                    sub_prefix = "  │" if not is_last_interval else "   "
                    count = interval_data.get("bar_count", 0)
                    quality = interval_data.get("quality", 0.0)
                    
                    quality_color = "green" if quality >= 95 else "yellow" if quality >= 80 else "red"
                    
                    main_table.add_row(f"│  │  {sub_prefix}  ├─ Count", f"{count} bars")
                    main_table.add_row(f"│  │  {sub_prefix}  ├─ Quality", 
                                      f"[{quality_color}]{quality:.1f}%[/{quality_color}]")
                    
                    # Time range
                    first_time = interval_data.get("first_bar_time")
                    last_time = interval_data.get("last_bar_time")
                    if first_time and last_time:
                        try:
                            # Extract time portion
                            first_t = first_time.split('T')[1][:8] if 'T' in first_time else first_time[:8]
                            last_t = last_time.split('T')[1][:8] if 'T' in last_time else last_time[:8]
                            main_table.add_row(f"│  │  {sub_prefix}  ├─ Time Range", 
                                              f"{first_t} - {last_t}")
                        except:
                            pass
                    
                    # Gaps
                    gaps_info = interval_data.get("gaps", {})
                    gap_count = gaps_info.get("gap_count", 0)
                    if gap_count > 0:
                        missing = gaps_info.get("missing_bars", 0)
                        main_table.add_row(f"│  │  {sub_prefix}  ├─ Gaps", 
                                          f"[yellow]{gap_count} gaps ({missing} missing bars)[/yellow]")
                    else:
                        main_table.add_row(f"│  │  {sub_prefix}  ├─ Gaps", "[green]None[/green]")
                    
                    # Updated flag
                    updated = interval_data.get("updated", False)
                    status_text = "[green]✓ Yes[/green]" if updated else "[dim]No[/dim]"
                    main_table.add_row(f"│  │  {sub_prefix}  └─ Updated", status_text)
                
                main_table.add_row(f"│  │", "")
                main_table.add_row(f"│  └─", "")
        else:
            main_table.add_row("│  [dim]No symbols[/dim]", "")
    
    return main_table


def data_session_command(
    refresh_seconds: Optional[int] = None,
    csv_file: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    no_live: bool = False
):
    """Display session data with optional auto-refresh.
    
    Args:
        refresh_seconds: Auto-refresh interval (None or 1 = default 1s, 0 = once)
        csv_file: CSV file path for export (not yet implemented in new version)
        duration_seconds: Duration to run in seconds (not yet implemented in new version)
        no_live: If True, print each refresh instead of live updating
    """
    # Default refresh to 1 second if not specified
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
                    import time
                    time.sleep(refresh_seconds)
            else:
                # Live mode: smooth updates
                with Live(generate_session_display(compact=True), console=console, refresh_per_second=1) as live:
                    while True:
                        import time
                        time.sleep(refresh_seconds)
                        live.update(generate_session_display(compact=True))
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Display stopped by user[/yellow]")
    except Exception as e:
        logger.error(f"Error in session display: {e}", exc_info=True)
        console.print(f"\n[red]Error: {e}[/red]")
