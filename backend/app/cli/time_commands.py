"""
Time Manager CLI Commands
Commands for interacting with the TimeManager
"""
import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from app.managers import get_system_manager
from app.models.database import SessionLocal
from app.logger import logger


console = Console()


def format_datetime_with_tz(dt: datetime) -> str:
    """Format datetime with timezone information
    
    Args:
        dt: Datetime to format
        
    Returns:
        Formatted string with timezone
    """
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    tz_name = dt.tzinfo.tzname(dt)
    offset = dt.strftime("%z")
    offset_formatted = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return dt.strftime(f"%Y-%m-%d %H:%M:%S {tz_name} ({offset_formatted})")


def current_time_command(timezone: str = None):
    """Get current system time
    
    Usage:
        time current
        time current --timezone UTC
        time current --timezone Asia/Tokyo
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        mode = time_mgr.get_current_mode()
        
        # Get current time (in system timezone)
        # (auto-initializes backtest window if needed)
        if timezone:
            current = time_mgr.get_current_time(timezone=timezone)
            display_tz = timezone
        else:
            current = time_mgr.get_current_time()
            display_tz = time_mgr.default_timezone
        
        mode_display = mode.upper()
        
        # Create display table
        table = Table(title=f"Current Time ({mode_display} Mode)", show_header=True)
        table.add_column("Timezone", style="cyan")
        table.add_column("Current Time", style="green")
        
        # Show in requested timezone
        table.add_row(display_tz, format_datetime_with_tz(current))
        
        # Show UTC for reference if not already UTC
        if timezone != "UTC":
            utc = time_mgr.to_utc(current)
            table.add_row("UTC", format_datetime_with_tz(utc))
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error getting current time: {e}[/red]")
        logger.error(f"Error in current_time_command: {e}", exc_info=True)


def market_status_command(exchange: str = "NYSE", extended: bool = False):
    """Check if market is currently open
    
    Usage:
        time market
        time market --exchange NASDAQ
        time market --extended
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Get current time (auto-initializes backtest window if needed)
        current = time_mgr.get_current_time()
        
        with SessionLocal() as session:
            is_open = time_mgr.is_market_open(
                session, current, exchange=exchange, include_extended=extended
            )
            
            session_type = time_mgr.get_session_type(
                session, current, exchange=exchange
            )
            
            # Status display
            status_color = "green" if is_open else "red"
            status_text = "OPEN" if is_open else "CLOSED"
            
            table = Table(title=f"{exchange} Market Status", show_header=True)
            table.add_column("Property", style="cyan")
            table.add_column("Value")
            
            table.add_row("Current Time", format_datetime_with_tz(current))
            table.add_row("Market Status", f"[{status_color}]{status_text}[/{status_color}]")
            table.add_row("Session Type", session_type.upper())
            table.add_row("Extended Hours", "Included" if extended else "Regular only")
            
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error checking market status: {e}[/red]")
        logger.error(f"Error in market_status_command: {e}", exc_info=True)


def trading_session_command(date_str: str = None, exchange: str = "NYSE"):
    """Get trading session information for a date
    
    Usage:
        time session
        time session 2024-11-25
        time session 2024-12-25 --exchange NASDAQ
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Parse date or use today
        if date_str:
            query_date = date.fromisoformat(date_str)
        else:
            query_date = datetime.now().date()
        
        with SessionLocal() as session:
            trading_session = time_mgr.get_trading_session(
                session, query_date, exchange=exchange
            )
            
            if trading_session is None:
                console.print(f"[red]No session information available for {query_date}[/red]")
                return
            
            # Create display table
            table = Table(title=f"Trading Session: {query_date} ({exchange})", show_header=True)
            table.add_column("Property", style="cyan")
            table.add_column("Value")
            
            # Basic info
            table.add_row("Date", str(trading_session.date))
            table.add_row("Exchange", trading_session.exchange)
            table.add_row("Asset Class", trading_session.asset_class)
            table.add_row("Timezone", trading_session.timezone)
            
            # Trading status
            status_color = "green" if trading_session.is_trading_day else "red"
            table.add_row("Trading Day", f"[{status_color}]{'Yes' if trading_session.is_trading_day else 'No'}[/{status_color}]")
            
            if trading_session.is_holiday:
                table.add_row("Holiday", f"[yellow]{trading_session.holiday_name}[/yellow]")
            
            if trading_session.is_early_close:
                table.add_row("Early Close", "[yellow]Yes[/yellow]")
            
            # Regular hours
            if trading_session.regular_open:
                table.add_row("Regular Open", str(trading_session.regular_open))
                table.add_row("Regular Close", str(trading_session.regular_close))
            
            # Extended hours
            if trading_session.pre_market_open:
                table.add_row("Pre-Market Open", str(trading_session.pre_market_open))
                table.add_row("Pre-Market Close", str(trading_session.pre_market_close))
            
            if trading_session.post_market_open:
                table.add_row("Post-Market Open", str(trading_session.post_market_open))
                table.add_row("Post-Market Close", str(trading_session.post_market_close))
            
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error getting trading session: {e}[/red]")
        logger.error(f"Error in trading_session_command: {e}", exc_info=True)


def next_trading_date_command(from_date_str: str = None, n: int = 1, exchange: str = "NYSE"):
    """Get the next N trading dates
    
    Usage:
        time next
        time next 2024-11-27
        time next 2024-11-27 --n 5
        time next 2024-11-27 --n 5 --exchange NASDAQ
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Parse date or use today
        if from_date_str:
            from_date = date.fromisoformat(from_date_str)
        else:
            from_date = datetime.now().date()
        
        with SessionLocal() as session:
            # Get next N trading dates
            table = Table(title=f"Next {n} Trading Date(s) from {from_date} ({exchange})", show_header=True)
            table.add_column("#", style="cyan")
            table.add_column("Date", style="green")
            table.add_column("Day of Week")
            
            current_date = from_date
            for i in range(1, n + 1):
                next_date = time_mgr.get_next_trading_date(
                    session, current_date, n=1, exchange=exchange
                )
                
                if next_date is None:
                    console.print(f"[yellow]Could not find {i}th next trading date[/yellow]")
                    break
                
                day_name = next_date.strftime("%A")
                table.add_row(str(i), str(next_date), day_name)
                current_date = next_date
            
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error getting next trading date: {e}[/red]")
        logger.error(f"Error in next_trading_date_command: {e}", exc_info=True)


def trading_days_command(start_str: str, end_str: str, exchange: str = "NYSE"):
    """Count trading days in a date range
    
    Usage:
        time days 2024-11-01 2024-11-30
        time days 2024-01-01 2024-12-31 --exchange NASDAQ
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
        
        with SessionLocal() as session:
            # Count trading days
            count = time_mgr.count_trading_days(
                session, start_date, end_date, exchange=exchange
            )
            
            # Get list of trading dates
            dates = time_mgr.get_trading_dates_in_range(
                session, start_date, end_date, exchange=exchange
            )
            
            # Display summary
            table = Table(title=f"Trading Days: {start_date} to {end_date} ({exchange})", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            total_days = (end_date - start_date).days + 1
            table.add_row("Total Days", str(total_days))
            table.add_row("Trading Days", str(count))
            table.add_row("Non-Trading Days", str(total_days - count))
            table.add_row("Percentage Trading", f"{(count / total_days * 100):.1f}%")
            
            console.print(table)
            
            # Show first/last few dates if many
            if len(dates) > 10:
                console.print(f"\n[cyan]First 5 trading dates:[/cyan]")
                for d in dates[:5]:
                    console.print(f"  {d} ({d.strftime('%A')})")
                console.print("  ...")
                console.print(f"[cyan]Last 5 trading dates:[/cyan]")
                for d in dates[-5:]:
                    console.print(f"  {d} ({d.strftime('%A')})")
            else:
                console.print(f"\n[cyan]Trading dates:[/cyan]")
                for d in dates:
                    console.print(f"  {d} ({d.strftime('%A')})")
            
    except Exception as e:
        console.print(f"[red]Error counting trading days: {e}[/red]")
        logger.error(f"Error in trading_days_command: {e}", exc_info=True)


def holidays_command(year: int = None, exchange: str = None):
    """List holidays for a year and exchange group
    
    Accepts either exchange groups (US_EQUITY) or individual exchanges (NYSE).
    Individual exchanges are auto-mapped to their groups.
    
    Usage:
        time holidays
        time holidays 2025
        time holidays 2024 --exchange US_EQUITY
        time holidays 2024 --exchange NYSE  (auto-maps to US_EQUITY)
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Use current year if not specified
        if year is None:
            year = datetime.now().year
        
        # Default to configured exchange group or auto-map
        if exchange is None:
            exchange_group = time_mgr.default_exchange_group
        else:
            # Auto-map exchange → group (NYSE → US_EQUITY)
            exchange_group = time_mgr.get_exchange_group(exchange)
        
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        
        with SessionLocal() as session:
            holidays = time_mgr.get_holidays_in_range(
                session, start_date, end_date, exchange=exchange_group
            )
            
            if not holidays:
                console.print(f"[yellow]No holidays found for {year} ({exchange_group})[/yellow]")
                return
            
            # Display holidays table
            table = Table(title=f"Holidays {year} ({exchange_group})", show_header=True)
            table.add_column("Date", style="cyan")
            table.add_column("Day", style="yellow")
            table.add_column("Holiday Name", style="green")
            table.add_column("Status")
            
            for holiday in holidays:
                day_name = holiday['date'].strftime("%A")
                
                if holiday['is_closed']:
                    status = "[red]Closed[/red]"
                else:
                    status = f"[yellow]Early Close ({holiday['early_close_time']})[/yellow]"
                
                table.add_row(
                    str(holiday['date']),
                    day_name,
                    holiday['holiday_name'],
                    status
                )
            
            console.print(table)
            console.print(f"\n[cyan]Total: {len(holidays)} holidays[/cyan]")
            
    except Exception as e:
        console.print(f"[red]Error listing holidays: {e}[/red]")
        logger.error(f"Error in holidays_command: {e}", exc_info=True)


def timezone_convert_command(datetime_str: str, from_tz: str, to_tz: str):
    """Convert datetime between timezones
    
    Usage:
        time convert "2024-11-25 10:30:00" America/New_York UTC
        time convert "2024-11-25 15:30:00" UTC Asia/Tokyo
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Parse datetime and add timezone
        dt_naive = datetime.fromisoformat(datetime_str)
        dt_source = dt_naive.replace(tzinfo=ZoneInfo(from_tz))
        
        # Convert to target timezone
        dt_target = time_mgr.convert_timezone(dt_source, to_tz)
        
        # Display conversion
        table = Table(title="Timezone Conversion", show_header=True)
        table.add_column("Timezone", style="cyan")
        table.add_column("Datetime", style="green")
        
        table.add_row(from_tz, format_datetime_with_tz(dt_source))
        table.add_row(to_tz, format_datetime_with_tz(dt_target))
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error converting timezone: {e}[/red]")
        logger.error(f"Error in timezone_convert_command: {e}", exc_info=True)


def import_holidays_command(
    file_path: str,
    exchange: str = None,
    dry_run: bool = False
):
    """Import holidays from JSON or CSV file with exchange awareness
    
    Uses configured primary exchange's group by default (e.g., NYSE → US_EQUITY).
    
    Usage:
        time import-holidays data/holidays/us_equity_2024.json
        time import-holidays data/holidays/2024.csv --exchange US_EQUITY
        time import-holidays holidays.json --dry-run
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        from app.managers.time_manager.holiday_import_service import HolidayImportService
        
        # Auto-detect exchange group from configured exchange
        if exchange is None:
            exchange = time_mgr.get_exchange_group()
            console.print(f"[dim]Using exchange group from configuration: {exchange}[/dim]\n")
        
        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
        
        console.print(f"[cyan]Importing holidays from:[/cyan] {file_path}")
        console.print(f"[cyan]Exchange/Group:[/cyan] {exchange}")
        console.print()
        
        with SessionLocal() as session:
            result = HolidayImportService.import_from_file(
                session, file_path, exchange_override=exchange, dry_run=dry_run
            )
            
            if result['success']:
                if dry_run:
                    console.print(f"[green]✓ Validation successful![/green]")
                    console.print(f"  Would import: {result['holidays_count']} holidays")
                    console.print(f"  Would affect: {', '.join(result['exchanges'])}")
                    console.print(f"  Total DB entries: {result.get('would_insert', 0)}")
                else:
                    console.print(f"[green]✓ Successfully imported {result['holidays_count']} holidays[/green]")
                    console.print(f"  Exchanges: {', '.join(result['exchanges'])}")
                    console.print(f"  Total DB entries: {result['inserted']}")
                
                if 'country' in result:
                    console.print(f"  Country: {result['country']}")
                if 'timezone' in result:
                    console.print(f"  Timezone: {result['timezone']}")
                if 'description' in result and result['description']:
                    console.print(f"  Description: {result['description']}")
            else:
                console.print(f"[red]✗ Import failed: {result.get('error')}[/red]")
                
    except Exception as e:
        console.print(f"[red]✗ Error importing holidays: {e}[/red]")
        logger.error(f"Import holidays command error: {e}", exc_info=True)


def list_exchange_groups_command():
    """List all available exchange groups
    
    Usage:
        time list-groups
    """
    try:
        from app.managers.time_manager.exchange_groups import (
            EXCHANGE_GROUPS,
            GROUP_METADATA
        )
        
        table = Table(title="Exchange Groups for Holiday Management", show_header=True)
        table.add_column("Group", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Exchanges", style="yellow")
        table.add_column("Count", style="magenta")
        
        for group, exchanges in EXCHANGE_GROUPS.items():
            metadata = GROUP_METADATA.get(group, {})
            group_name = metadata.get('name', group)
            exchange_list = ", ".join(exchanges)
            
            table.add_row(
                group,
                group_name,
                exchange_list,
                str(len(exchanges))
            )
        
        console.print(table)
        console.print(f"\n[cyan]Total groups:[/cyan] {len(EXCHANGE_GROUPS)}")
        console.print(f"[cyan]Total exchanges:[/cyan] {sum(len(e) for e in EXCHANGE_GROUPS.values())}")
        
    except Exception as e:
        console.print(f"[red]Error listing exchange groups: {e}[/red]")
        logger.error(f"Error in list_exchange_groups_command: {e}", exc_info=True)


def set_backtest_window_command(
    start_date: str,
    end_date: str = None
):
    """Set backtest window dates
    
    Usage:
        time backtest-window 2024-11-01 2024-11-30
        time backtest-window 2024-11-01
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Parse dates
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date) if end_date else None
        
        console.print(f"[cyan]Setting backtest window:[/cyan]")
        console.print(f"  Start: {start_dt}")
        console.print(f"  End: {end_dt or '(auto-calculated)'}")
        console.print()
        
        with SessionLocal() as session:
            time_mgr.set_backtest_window(session, start_dt, end_dt)
            
            # Show effective window
            effective_end = time_mgr.backtest_end_date or start_dt
            console.print(f"[green]✓ Backtest window set successfully[/green]")
            console.print(f"  Start date: {time_mgr.backtest_start_date}")
            console.print(f"  End date: {time_mgr.backtest_end_date}")
            console.print(f"  Backtest time reset to: {time_mgr._backtest_time}")
            
    except ValueError as e:
        console.print(f"[red]✗ Invalid date format: {e}[/red]")
        console.print("[yellow]Use format: YYYY-MM-DD[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Error setting backtest window: {e}[/red]")
        logger.error(f"Error in set_backtest_window_command: {e}", exc_info=True)


def advance_to_market_open_command(
    extended: bool = False,
    exchange: str = "NYSE"
):
    """Advance backtest time to next market opening
    
    Usage:
        time advance
        time advance --extended
        time advance --exchange NASDAQ
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Check mode
        mode = time_mgr.get_current_mode()
        if mode != "backtest":
            console.print("[yellow]⚠ This command only works in BACKTEST mode[/yellow]")
            console.print(f"[yellow]  Current mode: {mode.upper()}[/yellow]")
            return
        
        # Show current time
        current_before = time_mgr.get_current_time()
        console.print(f"[cyan]Current time:[/cyan] {format_datetime_with_tz(current_before)}")
        console.print(f"[cyan]Advancing to next {'extended' if extended else 'regular'} market open...[/cyan]\n")
        
        with SessionLocal() as session:
            new_time = time_mgr.advance_to_market_open(
                session,
                exchange=exchange,
                include_extended=extended
            )
            
            console.print(f"[green]✓ Advanced to market open[/green]")
            console.print(f"  New time: {format_datetime_with_tz(new_time)}")
            console.print(f"  Market: {exchange}")
            console.print(f"  Session: {'Pre-market (extended)' if extended else 'Regular'}")
            
    except Exception as e:
        console.print(f"[red]✗ Error advancing time: {e}[/red]")
        logger.error(f"Error in advance_to_market_open_command: {e}", exc_info=True)


def reset_to_backtest_start_command(extended: bool = False):
    """Reset backtest time to window start
    
    Usage:
        time reset
        time reset --extended
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Check mode
        mode = time_mgr.get_current_mode()
        if mode != "backtest":
            console.print("[yellow]⚠ This command only works in BACKTEST mode[/yellow]")
            console.print(f"[yellow]  Current mode: {mode.upper()}[/yellow]")
            return
        
        # Show current time
        current_before = time_mgr.get_current_time()
        console.print(f"[cyan]Current time:[/cyan] {format_datetime_with_tz(current_before)}")
        console.print(f"[cyan]Resetting to backtest window start...[/cyan]\n")
        
        with SessionLocal() as session:
            new_time = time_mgr.reset_to_backtest_start(
                session,
                include_extended=extended
            )
            
            console.print(f"[green]✓ Reset to backtest start[/green]")
            console.print(f"  New time: {format_datetime_with_tz(new_time)}")
            console.print(f"  Window start: {time_mgr.backtest_start_date}")
            console.print(f"  Session: {'Pre-market (extended)' if extended else 'Regular'}")
            
    except Exception as e:
        console.print(f"[red]✗ Error resetting time: {e}[/red]")
        logger.error(f"Error in reset_to_backtest_start_command: {e}", exc_info=True)


def show_backtest_config_command():
    """Show current configuration for all time/calendar operations
    
    Usage:
        time config
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        table = Table(title="Time Manager Configuration", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        # Exchange configuration
        table.add_row("Exchange Group", time_mgr.default_exchange_group)
        table.add_row("Asset Class", time_mgr.default_asset_class)
        
        table.add_section()
        
        # Window configuration
        table.add_row("Start Date", str(time_mgr.backtest_start_date or "Not set"))
        table.add_row("End Date", str(time_mgr.backtest_end_date or "Not set"))
        
        table.add_section()
        
        # Current state
        mode = time_mgr.get_current_mode()
        table.add_row("Mode", mode.upper())
        if mode == "backtest":
            current = time_mgr.get_current_time()
            table.add_row("Current Time", format_datetime_with_tz(current))
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error showing config: {e}[/red]")
        logger.error(f"Error in show_backtest_config_command: {e}", exc_info=True)


def set_backtest_exchange_command(
    exchange: str,
    asset_class: str = "EQUITY"
):
    """Set the primary exchange for all time/calendar operations
    
    Applies to both live and backtest modes.
    
    Usage:
        time exchange NYSE
        time exchange NASDAQ EQUITY
    """
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Validate exchange exists in market configs
        market_config = time_mgr._market_configs.get((exchange, asset_class))
        if not market_config:
            console.print(f"[yellow]⚠ Warning: No market configuration found for {exchange} {asset_class}[/yellow]")
            console.print(f"[yellow]  Time/calendar operations may use default hours[/yellow]\n")
        
        time_mgr.set_exchange(exchange, asset_class)
        
        console.print(f"[green]✓ Exchange configured[/green]")
        console.print(f"  Exchange Group: {time_mgr.default_exchange_group}")
        console.print(f"  Asset Class: {time_mgr.default_asset_class}")
        console.print(f"\n[dim]This configuration applies to all time/calendar operations (live and backtest)[/dim]")
        
    except Exception as e:
        console.print(f"[red]✗ Error setting exchange: {e}[/red]")
        logger.error(f"Error in set_backtest_exchange_command: {e}", exc_info=True)


def delete_holidays_command(
    year: int,
    exchange: str = None
):
    """Delete holidays for a specific year and exchange group
    
    Usage:
        time holidays delete 2024
        time holidays delete 2025 --exchange US_EQUITY
        time holidays delete 2025 --exchange NYSE  (auto-maps to US_EQUITY)
    """
    from rich.prompt import Confirm
    
    system_mgr = get_system_manager()
    time_mgr = system_mgr.get_time_manager()
    
    try:
        # Default to configured exchange group
        if exchange is None:
            exchange_group = time_mgr.default_exchange_group
            console.print(f"[dim]Using configured exchange group: {exchange_group}[/dim]\n")
        else:
            # Auto-map exchange → group (NYSE → US_EQUITY)
            exchange_group = time_mgr.get_exchange_group(exchange)
            if exchange_group != exchange:
                console.print(f"[dim]Mapped {exchange} → {exchange_group}[/dim]\n")
            else:
                console.print(f"[dim]Using exchange group: {exchange_group}[/dim]\n")
        
        # Confirm deletion
        if not Confirm.ask(f"[yellow]Delete all holidays for {exchange_group} year {year}?[/yellow]"):
            console.print("[dim]Cancelled[/dim]")
            return
        
        with SessionLocal() as session:
            from app.managers.time_manager.repositories import TradingCalendarRepository
            
            deleted = TradingCalendarRepository.delete_holidays_for_year(
                session, year, exchange_group
            )
        
        if deleted > 0:
            console.print(f"[green]✓ Deleted {deleted} holidays for {exchange_group} year {year}[/green]")
        else:
            console.print(f"[yellow]No holidays found for {exchange_group} year {year}[/yellow]")
            
    except Exception as e:
        console.print(f"[red]✗ Error deleting holidays: {e}[/red]")
        logger.error(f"Error in delete_holidays_command: {e}", exc_info=True)
