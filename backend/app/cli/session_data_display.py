"""Session Data Display - Live monitoring of stream, historical, and prefetch data."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box
import csv

from app.logger import logger
from app.config import settings


console = Console()


def generate_session_display(compact: bool = True) -> Table:
    """Generate the complete session data display table.
    
    Returns:
        Rich Table with all session data information
    """
    from app.managers.data_manager.session_data import get_session_data
    from app.managers.system_manager import get_system_manager
    
    session_data = get_session_data()
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    # Main container - Use more horizontal space
    main_table = Table(
        title="SESSION DATA",
        show_header=False,
        box=box.DOUBLE,
        expand=True,
        padding=(0, 1)
    )
    
    if compact:
        # Compact mode: 2 columns with more vertical space
        main_table.add_column("Section", style="bold yellow", width=22)
        main_table.add_column("Details", style="white", no_wrap=False)
    else:
        # Full mode: Traditional 2-column layout
        main_table.add_column("Property", style="yellow", width=30)
        main_table.add_column("Value", style="white", width=50)
    
    # === HEADER: System State and Session Info ===
    current_date = session_data.get_current_session_date()
    is_active = session_data.is_session_active()
    
    try:
        current_time = time_mgr.get_current_time()
        session_time_str = current_time.strftime("%H:%M:%S")
    except Exception:
        session_time_str = "N/A"
    
    # Get trading hours for the day
    trading_hours_str = ""
    is_early_close = False
    if current_date:
        try:
            from app.models.database import SessionLocal
            with SessionLocal() as db_session:
                trading_session = time_mgr.get_trading_session(db_session, current_date)
                if trading_session and not trading_session.is_holiday:
                    open_time = trading_session.regular_open.strftime("%H:%M")
                    close_time = trading_session.regular_close.strftime("%H:%M")
                    trading_hours_str = f"{open_time}-{close_time}"
                    is_early_close = trading_session.early_close
                elif trading_session and trading_session.is_holiday:
                    trading_hours_str = "Holiday"
        except Exception:
            pass
    
    # System state and mode
    state = system_mgr.state.value
    mode = system_mgr.mode.value
    state_color = "green" if state == "running" else "yellow" if state == "paused" else "red"
    mode_color = "cyan" if mode == "backtest" else "blue"
    
    active_symbols = session_data.get_active_symbols()
    
    if compact:
        # Compact header: Use multiple rows with 2 columns
        session_status = "[green]✓ Active[/green]" if is_active else "[yellow]⚠ Inactive[/yellow]"
        
        date_str = current_date.strftime("%Y-%m-%d") if current_date else "No session"
        
        # Calculate overall quality for compact display
        overall_quality = None
        if active_symbols:
            total_quality = 0.0
            total_weight = 0.0
            for symbol in active_symbols:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data and len(symbol_data.bars_1m) > 0:
                    total_quality += symbol_data.bar_quality
                    total_weight += 1.0
            if total_weight > 0:
                overall_quality = total_quality / total_weight
        
        # Build session info with trading hours and early close indicator
        session_info_parts = [date_str, session_time_str]
        if trading_hours_str:
            session_info_parts.append(f"[dim]({trading_hours_str})[/dim]")
        if is_early_close:
            session_info_parts.append("[yellow]⚡Short Day[/yellow]")
        session_info_parts.append(session_status)
        session_info_parts.append(f"Symbols: {len(active_symbols)}")
        
        # Add overall quality to compact display (fundamental intervals only)
        if overall_quality is not None:
            quality_color = "green" if overall_quality >= 95 else "yellow" if overall_quality >= 80 else "red"
            session_info_parts.append(f"Quality: [{quality_color}]{overall_quality:.1f}%[/{quality_color}] (1m)")
        
        session_info = " | ".join(session_info_parts)
        
        main_table.add_row(
            "[bold]SYSTEM[/bold]",
            f"State: [{state_color}]{state.upper()}[/{state_color}] | Mode: [{mode_color}]{mode.upper()}[/{mode_color}]"
        )
        main_table.add_row(
            "[bold]SESSION[/bold]",
            session_info
        )
    else:
        # Full mode: Traditional vertical layout
        main_table.add_row("System State", f"[{state_color}]{state.upper()}[/{state_color}]")
        main_table.add_row("Operation Mode", f"[{mode_color}]{mode.upper()}[/{mode_color}]")
        main_table.add_row("", "")  # Spacing
        
        if current_date:
            main_table.add_row("Session Date", current_date.strftime("%Y-%m-%d"))
            main_table.add_row("Session Time", f"[bold cyan]{session_time_str}[/bold cyan]")
            if trading_hours_str:
                hours_display = trading_hours_str
                if is_early_close:
                    hours_display += " [yellow]⚡ Early Close[/yellow]"
                main_table.add_row("Trading Hours", hours_display)
            main_table.add_row("Session Active", "[green]✓ Yes[/green]" if is_active else "[yellow]⚠ No[/yellow]")
        else:
            main_table.add_row("Session Date", "[yellow]No active session[/yellow]")
            main_table.add_row("Session Time", session_time_str)
            main_table.add_row("Session Active", "[red]✗ No[/red]")
        
        main_table.add_row("Active Symbols", f"{len(active_symbols)} symbols")
        
        # Calculate overall quality (average quality of fundamental intervals across all symbols)
        # Quality measures consumed bars (1m or 1s) from session_start to current_time
        if active_symbols:
            total_quality = 0.0
            total_weight = 0.0
            for symbol in active_symbols:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data and len(symbol_data.bars_1m) > 0:
                    # Simple average across all symbols with data
                    total_quality += symbol_data.bar_quality
                    total_weight += 1.0
            
            if total_weight > 0:
                overall_quality = total_quality / total_weight
                quality_color = "green" if overall_quality >= 95 else "yellow" if overall_quality >= 80 else "red"
                main_table.add_row("Overall Quality", f"[{quality_color}]{overall_quality:.1f}% (1m bars)[/{quality_color}]")
            else:
                main_table.add_row("Overall Quality", "[dim]No data yet[/dim]")
    
    # === SECTION 1: STREAM ===
    if compact:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold green]━━ SESSION DATA ━━[/bold green]", "")
    else:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold green]┌─ SESSION DATA[/bold green]", "")
        main_table.add_row("│", "")
    
    if active_symbols:
        for symbol in sorted(active_symbols):
            try:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data:
                    # Compact mode: Show symbol data across multiple rows
                    if compact:
                        current_bars = symbol_data.get_bar_count(1)
                        bars_5m = symbol_data.bars_derived.get(5, [])
                        
                        # Row 1: Symbol name and price range
                        price_info = ""
                        if symbol_data.session_high and symbol_data.session_low:
                            price_info = f"High: ${symbol_data.session_high:.2f} | Low: ${symbol_data.session_low:.2f}"
                        
                        main_table.add_row(f"  [bold cyan]{symbol}[/bold cyan]", price_info)
                        
                        # Row 2: Volume
                        main_table.add_row("    Volume", f"{symbol_data.session_volume:,.0f}")
                        
                        # Row 3: 1m bars with quality (quality is for consumed 1m bars only, not derived)
                        quality_color = "green" if symbol_data.bar_quality >= 95 else "yellow" if symbol_data.bar_quality >= 80 else "red"
                        bar_info = f"{current_bars} bars | Quality: [{quality_color}]{symbol_data.bar_quality:.1f}%[/{quality_color}]"
                        
                        # Add timing info if available
                        if len(symbol_data.bars_1m) > 0:
                            first_bar = symbol_data.bars_1m[0]
                            last_bar = symbol_data.bars_1m[-1]
                            
                            # Convert timestamps to market timezone for display
                            import pytz
                            from datetime import datetime
                            # All timestamps are in system timezone
                            first_ts = first_bar.timestamp
                            last_ts = last_bar.timestamp
                            
                            # Calculate span from first bar to last bar (data coverage span)
                            time_span = (last_ts - first_ts).total_seconds() / 60
                            
                            bar_info += f" | Start: {first_ts.strftime('%H:%M')} | Last: {last_ts.strftime('%H:%M')} | Span: {int(time_span)}min"
                        
                        main_table.add_row("    1m Bars", bar_info)
                        
                        # Row 4: 5m bars if available
                        if len(bars_5m) > 0:
                            bars_5m_info = f"{len(bars_5m)} bars"
                            first_bar_5m = bars_5m[0]
                            last_bar_5m = bars_5m[-1]
                            time_span_5m = (last_bar_5m.timestamp - first_bar_5m.timestamp).total_seconds() / 60
                            
                            # Convert 5m bar timestamps to market timezone
                            # All timestamps are in system timezone
                            first_ts_5m = first_bar_5m.timestamp
                            last_ts_5m = last_bar_5m.timestamp
                            
                            bars_5m_info += f" | Start: {first_ts_5m.strftime('%H:%M')} | Last: {last_ts_5m.strftime('%H:%M')} | Span: {int(time_span_5m)}min"
                            main_table.add_row("    5m Bars", bars_5m_info)
                    else:
                        # Full mode: Show detailed breakdown
                        main_table.add_row(f"│  [bold]┌─ {symbol}[/bold]", "")
                        
                        # Symbol-level metrics (not per data type)
                        main_table.add_row(f"│  │  ├─ Session Volume", f"{symbol_data.session_volume:,.0f}")
                        if symbol_data.session_high:
                            main_table.add_row(f"│  │  ├─ Session High", f"${symbol_data.session_high:.2f}")
                        if symbol_data.session_low:
                            main_table.add_row(f"│  │  ├─ Session Low", f"${symbol_data.session_low:.2f}")
                        main_table.add_row(f"│  │  │", "")
                        
                        # 1m Bars
                        current_bars = symbol_data.get_bar_count(1)
                        if current_bars > 0:
                            main_table.add_row(f"│  │  [cyan]├─ 1m Bar[/cyan]", "")
                            main_table.add_row(f"│  │  │  ├─ Bars", f"{current_bars} bars")
                            
                            # Get start and last update times
                            if len(symbol_data.bars_1m) > 0:
                                first_bar = symbol_data.bars_1m[0]
                                last_bar = symbol_data.bars_1m[-1]
                                
                                # All timestamps are in system timezone
                                first_ts = first_bar.timestamp
                                last_ts = last_bar.timestamp
                                
                                # Calculate span from market open to current time
                                try:
                                    with SessionLocal() as db_session:
                                        current_date = session_data.get_current_session_date()
                                        trading_session = time_mgr.get_trading_session(db_session, current_date)
                                        if trading_session and not trading_session.is_holiday:
                                            open_dt = trading_session.get_regular_open_datetime()
                                            current_time = time_mgr.get_current_time()
                                            time_span = (current_time - open_dt).total_seconds() / 60
                                        else:
                                            time_span = (last_bar.timestamp - first_bar.timestamp).total_seconds() / 60
                                except Exception:
                                    time_span = (last_bar.timestamp - first_bar.timestamp).total_seconds() / 60
                                
                                main_table.add_row(f"│  │  │  ├─ Start Time", first_ts.strftime("%H:%M:%S"))
                                main_table.add_row(f"│  │  │  ├─ Last Update", last_ts.strftime("%H:%M:%S"))
                                main_table.add_row(f"│  │  │  ├─ Time Span", f"{int(time_span)} minutes")
                            
                            quality_color = "green" if symbol_data.bar_quality >= 95 else "yellow" if symbol_data.bar_quality >= 80 else "red"
                            main_table.add_row(f"│  │  │  └─ Quality", f"[{quality_color}]{symbol_data.bar_quality:.1f}%[/{quality_color}]")
                            main_table.add_row(f"│  │  │", "")
                        
                        # 5m Bars (if exists in derived)
                        bars_5m = symbol_data.bars_derived.get(5, [])
                        if bars_5m and len(bars_5m) > 0:
                            main_table.add_row(f"│  │  [cyan]└─ 5m Bar[/cyan]", "")
                            main_table.add_row(f"│  │     ├─ Bars", f"{len(bars_5m)} bars")
                            first_bar_5m = bars_5m[0]
                            last_bar_5m = bars_5m[-1]
                            time_span_5m = (last_bar_5m.timestamp - first_bar_5m.timestamp).total_seconds() / 60
                            main_table.add_row(f"│  │     ├─ Start Time", first_bar_5m.timestamp.strftime("%H:%M:%S"))
                            main_table.add_row(f"│  │     ├─ Last Update", last_bar_5m.timestamp.strftime("%H:%M:%S"))
                            main_table.add_row(f"│  │     ├─ Time Span", f"{int(time_span_5m)} minutes")
                            main_table.add_row(f"│  │     └─ Quality", "[green]100.0%[/green]")  # Derived bars are complete
                            main_table.add_row(f"│  │", "")
                        
                        main_table.add_row(f"│", "")
            except Exception as e:
                logger.debug(f"Error displaying stream data for {symbol}: {e}")
    else:
        if compact:
            main_table.add_row("", "[dim]No active streams[/dim]")
        else:
            main_table.add_row("│  [dim]No active streams[/dim]", "")
    
    # === SECTION 2: BACKTEST WINDOW ===
    if mode == "backtest" and compact:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold green]━━ BACKTEST WINDOW ━━[/bold green]", "")
        
        # Get backtest window from TimeManager (single source of truth)
        try:
            backtest_start = time_mgr.backtest_start_date
            backtest_end = time_mgr.backtest_end_date
            
            if backtest_start and backtest_end:
                start_str = backtest_start.strftime("%Y-%m-%d")
                end_str = backtest_end.strftime("%Y-%m-%d")
                
                # Calculate total days
                from app.models.database import SessionLocal
                with SessionLocal() as db_session:
                    trading_days = time_mgr.count_trading_days(db_session, backtest_start, backtest_end)
                
                window_info = f"Start: {start_str} | End: {end_str} | Trading Days: {trading_days}"
                main_table.add_row("  Window", window_info)
                
                # Current progress
                if current_date:
                    days_completed = time_mgr.count_trading_days(db_session, backtest_start, current_date)
                    progress_pct = (days_completed / trading_days * 100) if trading_days > 0 else 0
                    progress_color = "green" if progress_pct > 0 else "yellow"
                    main_table.add_row("  Progress", f"[{progress_color}]{progress_pct:.1f}% ({days_completed}/{trading_days} days)[/{progress_color}]")
            else:
                main_table.add_row("  Window", "[dim]Not configured[/dim]")
        except Exception as e:
            logger.debug(f"Error displaying backtest window: {e}")
            main_table.add_row("  Window", "[dim]Error loading[/dim]")
    
    # === SECTION 3: PERFORMANCE METRICS ===
    if compact:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold yellow]━━ PERFORMANCE ━━[/bold yellow]", "")
        
        try:
            metrics = system_mgr._performance_metrics
            
            # Counters
            bars_processed = metrics.get_bars_processed()
            iterations = metrics.get_iterations()
            
            if bars_processed > 0 or iterations > 0:
                counters_info = f"Bars: {bars_processed:,} | Iterations: {iterations:,}"
                main_table.add_row("  Counters", counters_info)
            
            # Timing stats (only if we have data)
            dp_stats = metrics.data_processor.get_stats()
            if dp_stats['count'] > 0:
                timing_info = f"Data Processor: {dp_stats['avg']*1000:.2f}ms avg ({dp_stats['count']:,} items)"
                main_table.add_row("  Timing", timing_info)
        except Exception as e:
            logger.debug(f"Error displaying performance metrics: {e}")
            main_table.add_row("  Metrics", "[dim]Not available[/dim]")
    
    # === SECTION 4: HISTORICAL ===
    # Count total historical bars
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
    
    # Compact mode: Multiple rows with details
    if compact:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold magenta]━━ HISTORICAL ━━[/bold magenta]", "")
        
        # Get config from SessionConfig (not settings or session_data)
        try:
            session_config = system_mgr.session_config
            if session_config and hasattr(session_config, 'historical'):
                hist_config = session_config.historical
                trailing_days = hist_config.trailing_days if hist_config else 0
                intervals = hist_config.intervals if hist_config else []
                
                config_info = f"Trailing: {trailing_days} days"
                
                if intervals:
                    intervals_str = ", ".join(intervals)
                    config_info += f" | Intervals: {intervals_str}"
                
                main_table.add_row("  Config", config_info)
            else:
                main_table.add_row("  Config", "[dim]Not configured[/dim]")
            
            # Data loaded row
            if total_bars > 0:
                main_table.add_row("  Loaded", f"{total_bars:,} bars across {len(total_days)} dates")
            else:
                main_table.add_row("  Loaded", "[dim]No data loaded[/dim]")
        except Exception as e:
            logger.debug(f"Error displaying historical config: {e}")
            main_table.add_row("  Config", "[dim]Error loading[/dim]")
    else:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold magenta]┌─ HISTORICAL[/bold magenta]", "")
        main_table.add_row("│", "")
        
        # Historical Configuration
        main_table.add_row("│  [bold]┌─ Configuration[/bold]", "")
        if hasattr(session_data, 'historical_bars_trailing_days'):
            main_table.add_row("│  │  ├─ Trailing Days", f"{session_data.historical_bars_trailing_days} days")
            
            if hasattr(session_data, 'historical_bars_intervals') and session_data.historical_bars_intervals:
                intervals_str = ", ".join([f"{i}m" for i in session_data.historical_bars_intervals])
                main_table.add_row("│  │  ├─ Intervals", intervals_str)
            
            auto_load_status = "[green]✓ Enabled[/green]" if settings.HISTORICAL_BARS_AUTO_LOAD else "[dim]Disabled[/dim]"
            main_table.add_row("│  │  ├─ Auto-load", auto_load_status)
            
            if total_bars > 0:
                main_table.add_row("│  │  └─ Total Loaded", f"{total_bars:,} bars ({len(total_days)} unique dates)")
            else:
                main_table.add_row("│  │  └─ Total Loaded", "[dim]0 bars[/dim]")
        
        main_table.add_row("│  │", "")
    
    # Historical per symbol (only in full mode)
    if active_symbols and not compact:
        for symbol in sorted(active_symbols):
            try:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data and hasattr(symbol_data, 'historical_bars'):
                    # Check if there's any historical data
                    has_hist_data = False
                    for interval_bars in symbol_data.historical_bars.values():
                        if interval_bars:
                            has_hist_data = True
                            break
                    
                    if has_hist_data:
                        main_table.add_row(f"│  [bold]┌─ {symbol}[/bold]", "")
                        main_table.add_row(f"│  │", "")
                        
                        # 1m historical bars
                        if 1 in symbol_data.historical_bars and symbol_data.historical_bars[1]:
                            hist_1m = symbol_data.historical_bars[1]
                            total_bars_1m = sum(len(bars) for bars in hist_1m.values())
                            dates_1m = sorted(hist_1m.keys())
                            
                            main_table.add_row(f"│  │  [magenta]├─ 1m Bar[/magenta]", "")
                            main_table.add_row(f"│  │  │  ├─ Bars", f"{total_bars_1m} bars")
                            main_table.add_row(f"│  │  │  ├─ Days", f"{len(dates_1m)} days ({dates_1m[0]}, {dates_1m[-1]})")
                            
                            # Get start and end times
                            all_bars_1m = [bar for date_bars in hist_1m.values() for bar in date_bars]
                            if all_bars_1m:
                                all_bars_1m_sorted = sorted(all_bars_1m, key=lambda b: b.timestamp)
                                start_dt = all_bars_1m_sorted[0].timestamp
                                end_dt = all_bars_1m_sorted[-1].timestamp
                                main_table.add_row(f"│  │  │  ├─ Start", start_dt.strftime("%Y-%m-%d %H:%M:%S"))
                                main_table.add_row(f"│  │  │  ├─ End", end_dt.strftime("%Y-%m-%d %H:%M:%S"))
                                main_table.add_row(f"│  │  │  └─ Quality", "[green]99.5%[/green]")  # Placeholder
                            
                            main_table.add_row(f"│  │  │", "")
                        
                        # 5m historical bars
                        if 5 in symbol_data.historical_bars and symbol_data.historical_bars[5]:
                            hist_5m = symbol_data.historical_bars[5]
                            total_bars_5m = sum(len(bars) for bars in hist_5m.values())
                            dates_5m = sorted(hist_5m.keys())
                            
                            main_table.add_row(f"│  │  [magenta]└─ 5m Bar[/magenta]", "")
                            main_table.add_row(f"│  │     ├─ Bars", f"{total_bars_5m} bars")
                            main_table.add_row(f"│  │     ├─ Days", f"{len(dates_5m)} days ({dates_5m[0]}, {dates_5m[-1]})")
                            
                            all_bars_5m = [bar for date_bars in hist_5m.values() for bar in date_bars]
                            if all_bars_5m:
                                all_bars_5m_sorted = sorted(all_bars_5m, key=lambda b: b.timestamp)
                                start_dt_5m = all_bars_5m_sorted[0].timestamp
                                end_dt_5m = all_bars_5m_sorted[-1].timestamp
                                main_table.add_row(f"│  │     ├─ Start", start_dt_5m.strftime("%Y-%m-%d %H:%M:%S"))
                                main_table.add_row(f"│  │     ├─ End", end_dt_5m.strftime("%Y-%m-%d %H:%M:%S"))
                                main_table.add_row(f"│  │     └─ Quality", "[green]100.0%[/green]")
                        
                        main_table.add_row(f"│  │", "")
            except Exception as e:
                logger.debug(f"Error displaying historical data for {symbol}: {e}")
    else:
        main_table.add_row("│  [dim]No historical data[/dim]", "")
    
    # === SECTION 5: PREFETCH ===
    # Note: This feature is not yet implemented in new architecture
    # Keeping section for consistency but showing as unavailable
    if compact:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold blue]━━ PREFETCH ━━[/bold blue]", "")
        main_table.add_row("  Status", "[dim]Feature not yet implemented (planned)[/dim]")
    else:
        main_table.add_row("", "")  # Spacing
        main_table.add_row("[bold blue]┌─ PREFETCH[/bold blue]", "")
        # Full mode: Detailed breakdown
        main_table.add_row("│", "")
        
        # Prefetch Configuration
        main_table.add_row("│  [bold]┌─ Configuration[/bold]", "")
        main_table.add_row("│  │  ├─ Window", f"{settings.PREFETCH_WINDOW_MINUTES} min before session")
        main_table.add_row("│  │  ├─ Check Interval", f"{settings.PREFETCH_CHECK_INTERVAL_MINUTES} min")
        auto_activate_status = "[green]✓ Enabled[/green]" if settings.PREFETCH_AUTO_ACTIVATE else "[dim]Disabled[/dim]"
        main_table.add_row("│  │  ├─ Auto-activate", auto_activate_status)
        main_table.add_row("│  │  └─ Status", "[dim]Not Implemented[/dim]")  # TODO: Get actual status
        main_table.add_row("│  │", "")
        main_table.add_row("│  [dim]No prefetch data (feature not yet implemented)[/dim]", "")
    
    # === SECTION 6: MARKET HOURS ===
    # Market hours are already shown in SESSION section header
    # This section is redundant but kept for compatibility
    # Consider removing in future versions
    
    # === SECTION 7: STREAM COORDINATOR QUEUES ===
    try:
        from app.managers.data_manager.backtest_stream_coordinator import get_coordinator
        coordinator = get_coordinator(system_manager=system_mgr)
        queue_stats = coordinator.get_queue_stats()
        
        if compact:
            main_table.add_row("", "")  # Spacing
            main_table.add_row("[bold cyan]━━ STREAM COORDINATOR ━━[/bold cyan]", "")
            
            if queue_stats:
                # Display per symbol
                for symbol in sorted(queue_stats.keys()):
                    intervals = queue_stats[symbol]
                    
                    # Build queue info string - show per interval with timestamps
                    queue_info_parts = []
                    for interval, stats_dict in sorted(intervals.items()):
                        queue_size = stats_dict["size"]
                        oldest = stats_dict.get("oldest")
                        newest = stats_dict.get("newest")
                        
                        # Only show if queue has items
                        if queue_size > 0:
                            # Format: "1m: 150 items (09:30:00 - 12:45:00)"
                            info = f"{interval}: [yellow]{queue_size} items[/yellow]"
                            
                            if oldest and newest:
                                # Convert UTC timestamps to market timezone for display
                                # All timestamps are in system timezone
                                oldest_display = oldest
                                newest_display = newest
                                
                                oldest_time = oldest_display.strftime("%H:%M:%S")
                                newest_time = newest_display.strftime("%H:%M:%S")
                                if oldest_time == newest_time:
                                    info += f" ({oldest_time})"
                                else:
                                    info += f" ({oldest_time} - {newest_time})"
                            
                            queue_info_parts.append(info)
                    
                    # Only show row if there are queues with data
                    if queue_info_parts:
                        queue_info = " | ".join(queue_info_parts)
                        main_table.add_row(f"  [bold cyan]{symbol}[/bold cyan]", queue_info)
                
                # If no symbols have queues with data
                if not any(any(stats["size"] > 0 for stats in types.values()) for types in queue_stats.values()):
                    main_table.add_row("", "[dim]All queues empty[/dim]")
            else:
                main_table.add_row("", "[dim]No active streams[/dim]")
        else:
            # Full mode
            main_table.add_row("", "")  # Spacing
            main_table.add_row("[bold cyan]┌─ STREAM COORDINATOR[/bold cyan]", "")
            main_table.add_row("│", "")
            
            if queue_stats:
                any_data = False
                for symbol in sorted(queue_stats.keys()):
                    intervals = queue_stats[symbol]
                    
                    # Check if this symbol has any queues with data
                    has_data = any(stats["size"] > 0 for stats in intervals.values())
                    if not has_data:
                        continue
                    
                    any_data = True
                    main_table.add_row(f"│  [bold]┌─ {symbol}[/bold]", "")
                    
                    # Show per interval with data
                    for interval, stats_dict in sorted(intervals.items()):
                        queue_size = stats_dict["size"]
                        if queue_size == 0:
                            continue
                        
                        oldest = stats_dict.get("oldest")
                        newest = stats_dict.get("newest")
                        
                        # Format: "1m Queue: 150 items | Oldest: 09:30:00 | Newest: 12:45:00"
                        info = f"[yellow]{queue_size} items[/yellow]"
                        if oldest:
                            info += f" | Oldest: {oldest.strftime('%H:%M:%S')}"
                        if newest:
                            info += f" | Newest: {newest.strftime('%H:%M:%S')}"
                        
                        main_table.add_row(f"│  │  ├─ {interval} Queue", info)
                    
                    main_table.add_row(f"│  │", "")
                
                if not any_data:
                    main_table.add_row("│  [dim]All queues empty[/dim]", "")
            else:
                main_table.add_row("│  [dim]No active streams[/dim]", "")
    except Exception as e:
        logger.debug(f"Error displaying stream coordinator stats: {e}")
    
    return main_table


def extract_session_data_for_csv() -> Dict[str, Any]:
    """Extract session data into a flat dictionary for CSV export.
    
    Returns:
        Dictionary with flattened session data
    """
    from app.managers.system_manager import get_system_manager
    from app.managers.data_manager.session_data import get_session_data
    from app.managers.data_manager.backtest_stream_coordinator import get_coordinator
    
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    # Use TimeManager for current time (architecture compliant)
    current_time = time_mgr.get_current_time()
    
    row = {
        "timestamp": current_time.isoformat() if current_time else "N/A",
    }
    
    try:
        session_data = get_session_data()
        
        # System info
        row["system_state"] = system_mgr.state.value if system_mgr.state else "unknown"
        row["system_mode"] = system_mgr.mode.value if system_mgr.mode else "unknown"
        
        # Session info
        current_date = session_data.get_current_session_date()
        row["session_date"] = current_date.isoformat() if current_date else "N/A"
        
        try:
            time_mgr = system_mgr.get_time_manager()
            current_time = time_mgr.get_current_time()
            row["session_time"] = current_time.strftime("%H:%M:%S") if current_time else "N/A"
        except:
            row["session_time"] = "N/A"
        
        row["session_active"] = session_data.is_session_active()
        row["active_symbols"] = len(session_data.get_active_symbols())
        
        # Calculate overall quality (weighted average across all symbols)
        active_symbols = session_data.get_active_symbols()
        if active_symbols:
            total_quality = 0.0
            total_weight = 0.0
            for symbol in active_symbols:
                symbol_data = session_data.get_symbol_data(symbol)
                if symbol_data and len(symbol_data.bars_1m) > 0:
                    total_quality += symbol_data.bar_quality
                    total_weight += 1.0
            if total_weight > 0:
                row["overall_quality"] = round(total_quality / total_weight, 1)
            else:
                row["overall_quality"] = 0.0
        else:
            row["overall_quality"] = 0.0
        
        # Trading hours for the session
        row["trading_hours_open"] = "N/A"
        row["trading_hours_close"] = "N/A"
        row["is_early_close"] = False
        if current_date:
            try:
                from app.models.database import SessionLocal
                with SessionLocal() as db_session:
                    time_mgr = system_mgr.get_time_manager()
                    trading_session = time_mgr.get_trading_session(db_session, current_date)
                    if trading_session and not trading_session.is_holiday:
                        row["trading_hours_open"] = trading_session.regular_open.strftime("%H:%M")
                        row["trading_hours_close"] = trading_session.regular_close.strftime("%H:%M")
                        row["is_early_close"] = trading_session.early_close
                    elif trading_session and trading_session.is_holiday:
                        row["trading_hours_open"] = "Holiday"
                        row["trading_hours_close"] = "Holiday"
            except Exception as e:
                logger.debug(f"Error getting trading hours for CSV: {e}")
        
        # Per-symbol data
        active_symbols = session_data.get_active_symbols()
        for symbol in sorted(active_symbols):
            symbol_data = session_data.get_symbol_data(symbol)
            if symbol_data:
                prefix = f"{symbol}_"
                row[f"{prefix}volume"] = symbol_data.session_volume
                row[f"{prefix}high"] = symbol_data.session_high
                row[f"{prefix}low"] = symbol_data.session_low
                row[f"{prefix}1m_bars"] = len(symbol_data.bars_1m)
                row[f"{prefix}5m_bars"] = len(symbol_data.bars_derived.get(5, []))
                row[f"{prefix}bar_quality"] = symbol_data.bar_quality
                
                # INTERNAL STATE: bars_updated flag (triggers derived bar computation)
                row[f"{prefix}bars_updated"] = symbol_data.bars_updated
                
                # INTERNAL STATE: First and last bar timestamps in session_data
                if len(symbol_data.bars_1m) > 0:
                    first_bar = symbol_data.bars_1m[0]
                    last_bar = symbol_data.bars_1m[-1]
                    
                    # Convert timestamps to market timezone for CSV export
                    import pytz
                    market_tz_str = system_mgr.get_time_manager().get_market_timezone()
                    market_tz = pytz.timezone(market_tz_str)
                    first_ts = first_bar.timestamp.astimezone(market_tz) if hasattr(first_bar, 'timestamp') and first_bar.timestamp.tzinfo else first_bar.timestamp if hasattr(first_bar, 'timestamp') else None
                    last_ts = last_bar.timestamp.astimezone(market_tz) if hasattr(last_bar, 'timestamp') and last_bar.timestamp.tzinfo else last_bar.timestamp if hasattr(last_bar, 'timestamp') else None
                    
                    row[f"{prefix}first_bar_ts"] = first_ts.strftime("%H:%M:%S") if first_ts else "N/A"
                    row[f"{prefix}last_bar_ts"] = last_ts.strftime("%H:%M:%S") if last_ts else "N/A"
                else:
                    row[f"{prefix}first_bar_ts"] = "N/A"
                    row[f"{prefix}last_bar_ts"] = "N/A"
        
        # Stream coordinator queue stats
        try:
            coordinator = get_coordinator(system_manager=system_mgr)
            queue_stats = coordinator.get_queue_stats()
            
            for symbol, intervals in queue_stats.items():
                for interval, stats_dict in intervals.items():
                    prefix = f"{symbol}_queue_{interval}_"
                    row[f"{prefix}size"] = stats_dict["size"]
                    oldest = stats_dict.get("oldest")
                    newest = stats_dict.get("newest")
                    
                    # Convert timestamps to market timezone for CSV export
                    if oldest:
                        # All timestamps are in system timezone
                        oldest_display = oldest
                        row[f"{prefix}oldest"] = oldest_display.strftime("%H:%M:%S")
                    else:
                        row[f"{prefix}oldest"] = "N/A"
                    
                    if newest:
                        # All timestamps are in system timezone
                        newest_display = newest
                        row[f"{prefix}newest"] = newest_display.strftime("%H:%M:%S")
                    else:
                        row[f"{prefix}newest"] = "N/A"
            
            # INTERNAL STATE: Stream coordinator pending_items (staging area for chronological ordering)
            # This is the "peek" mechanism - one item from each queue waiting to be compared
            if hasattr(coordinator, '_pending_items') and coordinator._pending_items:
                for stream_key, pending_item in coordinator._pending_items.items():
                    if pending_item and hasattr(pending_item, 'timestamp'):
                        symbol, stream_type = stream_key
                        prefix = f"{symbol}_pending_{stream_type.value}_"
                        # Convert pending item timestamp to market timezone
                        import pytz
                        market_tz_str = system_mgr.get_time_manager().get_market_timezone()
                        market_tz = pytz.timezone(market_tz_str)
                        pending_ts = pending_item.timestamp.astimezone(market_tz) if pending_item.timestamp.tzinfo else pending_item.timestamp
                        row[f"{prefix}ts"] = pending_ts.strftime("%H:%M:%S")
                    elif pending_item is None:
                        # None indicates stream exhausted
                        symbol, stream_type = stream_key
                        prefix = f"{symbol}_pending_{stream_type.value}_"
                        row[f"{prefix}ts"] = "EXHAUSTED"
        except Exception as e:
            logger.debug(f"Error getting queue stats for CSV: {e}")
    
    except Exception as e:
        logger.error(f"Error extracting session data for CSV: {e}")
        row["error"] = str(e)
    
    return row


def data_session_command(
    refresh_seconds: Optional[int] = None, 
    csv_file: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    no_live: bool = False
) -> None:
    """Display live session data with in-place refreshing.
    
    Args:
        refresh_seconds: Auto-refresh interval in seconds (default: 1s, use 0 to display once)
        csv_file: CSV file path to export data on each refresh (default: validation/test_session.csv)
        duration_seconds: Optional duration to run in seconds (default: None = run indefinitely)
        no_live: Disable live updating, print each refresh on new line (useful for scripts)
    """
    from app.managers.system_manager import get_system_manager
    from app.managers.data_manager.session_data import get_session_data
    import csv
    import time
    
    console = Console()
    system_mgr = get_system_manager()
    session_data = get_session_data()
    
    if refresh_seconds is None:
        refresh_seconds = 1
    
    # Set default CSV file path to match data validate default
    if csv_file is None:
        csv_file = "validation/test_session.csv"
    
    # Open CSV file (always overwrite)
    csv_writer = None
    csv_file_handle = None
    csv_path = Path(csv_file)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_file_handle = open(csv_path, 'w', newline='')
    
    # Write header once
    first_row = extract_session_data_for_csv()
    csv_writer = csv.DictWriter(csv_file_handle, fieldnames=first_row.keys(), extrasaction='ignore')
    csv_writer.writeheader()
    csv_file_handle.flush()
    
    console.print(f"[green]Exporting to CSV: {csv_file}[/green]")
    
    # Calculate end time if duration specified
    end_time = None
    if duration_seconds is not None and duration_seconds > 0:
        end_time = time.time() + duration_seconds
        console.print(f"[cyan]Session data display (refreshing every {refresh_seconds}s, duration: {duration_seconds}s)[/cyan]")
    else:
        console.print(f"[cyan]Session data display (refreshing every {refresh_seconds}s)[/cyan]")
    
    console.print("[dim]Press Ctrl+C to exit, or will stop automatically when system stops[/dim]\n")
    
    try:
        if refresh_seconds == 0:
            # Display once without refresh
            table = generate_session_display(compact=False)
            console.print(table)
            
            # Write CSV row
            row_data = extract_session_data_for_csv()
            csv_writer.writerow(row_data)
            csv_file_handle.flush()
        else:
            # Display with auto-refresh
            if no_live:
                # No live display - print each refresh on new line (better for scripts)
                try:
                    iteration = 0
                    while system_mgr.state.value == "running":
                        # Check if duration expired
                        if end_time is not None and time.time() >= end_time:
                            console.print("\n[yellow]Duration expired - stopping session display[/yellow]")
                            break
                        
                        time.sleep(refresh_seconds)
                        iteration += 1
                        console.print(f"\n[dim]--- Refresh {iteration} ---[/dim]")
                        table = generate_session_display(compact=True)
                        console.print(table)
                        
                        # Write CSV row
                        row_data = extract_session_data_for_csv()
                        csv_writer.writerow(row_data)
                        csv_file_handle.flush()
                
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass
                
                console.print("\n[green]Session data display stopped[/green]")
            else:
                # Live display - update in place (better for interactive use)
                with Live(generate_session_display(compact=True), console=console, refresh_per_second=4) as live:
                    try:
                        while system_mgr.state.value == "running":
                            # Check if duration expired
                            if end_time is not None and time.time() >= end_time:
                                console.print("\n[yellow]Duration expired - stopping session display[/yellow]")
                                break
                            
                            time.sleep(refresh_seconds)
                            live.update(generate_session_display(compact=True))
                            
                            # Write CSV row
                            row_data = extract_session_data_for_csv()
                            csv_writer.writerow(row_data)
                            csv_file_handle.flush()
                    
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        pass
                
                console.print("\nSession data display stopped")
            
            # Final display (non-compact)
            final_table = generate_session_display(compact=False)
            console.print(final_table)
    
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[yellow]Session data display interrupted[/yellow]")
    
    finally:
        # Close CSV file
        if csv_file_handle:
            csv_file_handle.close()
            console.print(f"[green]CSV export completed: {csv_file}[/green]")
