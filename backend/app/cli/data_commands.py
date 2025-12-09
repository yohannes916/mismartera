"""
CLI commands for market data management
"""
from pathlib import Path
from typing import Optional
from datetime import datetime, date
import threading
import math

import typer
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from app.services.market_data.csv_import_service import csv_import_service
from app.models.database import SessionLocal
from app.managers import DataManager
from app.logger import logger
from app.cli.command_registry import DATA_COMMANDS
from app.config import settings


console = Console()

# Background task registry to prevent garbage collection
_background_tasks: set = set()


def format_timestamp(dt: datetime, include_seconds: bool = True, show_tz: bool = True) -> str:
    """
    Format timestamp with timezone information.
    
    Args:
        dt: Datetime object to format
        include_seconds: Include seconds in output
        show_tz: Show timezone information
        
    Formatted timestamp string with timezone
    """
    if dt is None:
        return "N/A"
    
    # Assume all timestamps are in system timezone
    # Format the datetime
    if include_seconds:
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        time_str = dt.strftime("%Y-%m-%d %H:%M")
    
    # Add timezone info if requested
    if show_tz and dt.tzinfo:
        # Get timezone abbreviation (EST/EDT)
        tz_abbr = dt.strftime("%Z")
        time_str = f"{time_str} {tz_abbr}"
    
    return time_str


def get_data_manager() -> DataManager:
    """Get DataManager instance via SystemManager.
    
    The SystemManager ensures all managers are singletons and can
    communicate with each other.
    """
    from app.managers.system_manager import get_system_manager
    system_mgr = get_system_manager()
    return system_mgr.get_data_manager()


def register_background_task(task: threading.Thread) -> None:
    """Register a background thread to prevent garbage collection.
    
    Keeps a reference to the thread.
    """
    _background_tasks.add(task)


def parse_start_date(date_str: str) -> datetime:
    """Parse a date string and return datetime at start of day (00:00:00) in ET.
    
    Market data dates are interpreted as Eastern Time (US/Eastern timezone).
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        datetime object at 00:00:00 ET (timezone-aware)
        
    Raises:
        ValueError: If date format is invalid
    """
    from app.managers.system_manager import get_system_manager
    from zoneinfo import ZoneInfo
    
    system_mgr = get_system_manager()
    system_tz = ZoneInfo(system_mgr.timezone)
    
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Interpret as system timezone
    dt_aware = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=system_tz)
    return dt_aware


def parse_end_date(date_str: str) -> datetime:
    """Parse a date string and return datetime at end of day (23:59:59) in ET.
    
    Market data dates are interpreted as Eastern Time (US/Eastern timezone).
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        datetime object at 23:59:59 ET (timezone-aware)
        
    Raises:
        ValueError: If date format is invalid
    """
    from app.managers.system_manager import get_system_manager
    from zoneinfo import ZoneInfo
    
    system_mgr = get_system_manager()
    system_tz = ZoneInfo(system_mgr.timezone)
    
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Interpret as system timezone
    dt_aware = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=system_tz)
    return dt_aware


def print_data_usage(_console: Console) -> None:
    """Print data command usage lines to the given console.

    Single source of truth comes from DATA_COMMANDS in command_registry.
    """
    _console.print("[red]Usage:[/red]")
    for meta in DATA_COMMANDS:
        _console.print(f"  {meta.usage} - {meta.description}")


def import_csv_command(
    file_path: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> None:
    """
    Import CSV file into database with optional date filtering
    
    Args:
        file_path: Path to CSV file
        symbol: Stock symbol
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
    """
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]✗ File not found: {file_path}[/red]")
        return
    
    if not path.suffix.lower() == '.csv':
        console.print(f"[red]✗ File must be a CSV file[/red]")
        return
    
    console.print(f"\n[cyan]Importing {path.name} for {symbol.upper()}...[/cyan]")
    
    # Parse dates if provided
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_start_date(start_date)  # 00:00:00
            console.print(f"[yellow]📅 Start date filter: {start_date} 00:00:00[/yellow]")
        except ValueError:
            console.print(f"[red]Invalid start date format. Use YYYY-MM-DD[/red]")
            return
    
    if end_date:
        try:
            end_dt = parse_end_date(end_date)  # 23:59:59
            console.print(f"[yellow]📅 End date filter: {end_date} 23:59:59[/yellow]")
        except ValueError:
            console.print(f"[red]Invalid end date format. Use YYYY-MM-DD[/red]")
            return
    
    if not start_date and not end_date:
        console.print("[dim]No date filters - importing all data from file[/dim]")
    elif start_date and not end_date:
        console.print(f"[dim]Importing data from {start_date} onwards[/dim]")
    elif not start_date and end_date:
        console.print(f"[dim]Importing data up to {end_date}[/dim]")
    else:
        console.print(f"[dim]Importing date range: {start_date} to {end_date}[/dim]")
    
    # Try to detect if file has header by checking first line
    has_header = False
    try:
        with open(path, 'r') as f:
            first_line = f.readline().strip()
            # If first line contains common header words, it's likely a header
            if any(word in first_line.lower() for word in ['date', 'time', 'open', 'high', 'low', 'close', 'volume']):
                has_header = True
                console.print("[dim]Detected header row[/dim]")
            else:
                console.print("[dim]No header detected, treating first line as data[/dim]")
    except:
        pass  # Default to no header
    
    try:
        with SessionLocal() as session:
            # Route through DataManager API so all imports share the same path
            dm = get_data_manager()
            result = dm.import_csv(
                session=session,
                file_path=str(path.absolute()),
                symbol=symbol,
                skip_header=has_header,
                start_date=start_dt,
                end_date=end_dt,
            )
        
        if result['success']:
            console.print(f"\n[green]✓ Import successful![/green]")
            console.print(f"  Symbol: {result['symbol']}")
            console.print(f"  Total rows: {result['total_rows']}")
            console.print(f"  Upserted: {result['imported']}")
            console.print(f"  [dim](Inserted new or updated existing bars)[/dim]")
            
            if result.get('date_range'):
                console.print(f"  Date range: {result['date_range']['start']} to {result['date_range']['end']}")
            
            if result.get('quality_score'):
                quality_pct = result['quality_score'] * 100
                # Always round down to 1 decimal place
                quality_pct_display = math.floor(quality_pct * 10) / 10
                quality_color = "green" if quality_pct >= 95 else "yellow" if quality_pct >= 80 else "red"
                console.print(f"  Quality: [{quality_color}]{quality_pct_display:.1f}%[/{quality_color}]")
            
            if result.get('missing_bars', 0) > 0:
                console.print(f"  [yellow]⚠ Missing bars: {result['missing_bars']}[/yellow]")
        else:
            console.print(f"[red]✗ Import failed: {result.get('message')}[/red]")
    
    except Exception as e:
        console.print(f"[red]✗ Import error: {e}[/red]")
        logger.error(f"CSV import error: {e}")


def list_symbols_command(symbol: str) -> None:
    """List all available intervals for a symbol in unified table.
    
    Shows seconds, minutes, days, weeks, and quotes in single view.
    """
    symbol = symbol.upper()
    
    try:
        from app.managers.data_manager.parquet_storage import parquet_storage
        
        # Get all available intervals for this symbol
        intervals = parquet_storage.get_available_intervals(symbol)
        
        if not intervals:
            console.print(f"\n[yellow]No data found for {symbol}[/yellow]")
            console.print(f"[dim]Import data using: data import-api <interval> {symbol} <start> <end>[/dim]")
            return
        
        # Create unified table
        table = Table(
            title=f"\nData Summary: {symbol}",
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Interval", style="cyan", width=10)
        table.add_column("Type", style="magenta", width=12)
        table.add_column("Bars", justify="right", style="green", width=12)
        table.add_column("Quality", justify="right", style="white", width=8)
        table.add_column("Start Date", style="dim")
        table.add_column("End Date", style="dim")
        
        # Process each interval
        for interval in sorted(intervals):
            # Determine interval type
            if interval == 'quotes':
                interval_type = "Quotes"
            elif interval.endswith('s'):
                interval_type = "Seconds"
            elif interval.endswith('m'):
                interval_type = "Minutes"
            elif interval.endswith('d'):
                interval_type = "Days"
            elif interval.endswith('w'):
                interval_type = "Weeks"
            else:
                interval_type = "Unknown"
            
            # Get bar count and date range
            try:
                with SessionLocal() as session:
                    dm = get_data_manager()
                    
                    if interval == 'quotes':
                        # Quotes are stored differently
                        try:
                            quotes = parquet_storage.read_quotes(
                                symbol=symbol,
                                start_date=None,
                                end_date=None
                            )
                            bar_count = len(quotes)
                            if bar_count > 0:
                                start_date = quotes[0]['timestamp']
                                end_date = quotes[-1]['timestamp']
                            else:
                                start_date = None
                                end_date = None
                        except:
                            bar_count = 0
                            start_date = None
                            end_date = None
                    else:
                        # Regular bars
                        bar_count = dm.get_bar_count(session, symbol, interval=interval)
                        start_date, end_date = dm.get_date_range(session, symbol, interval=interval)
                        
                        # Get quality score
                        quality_result = dm.check_data_quality(session, symbol, interval=interval)
                        quality_score = quality_result.get('quality_score', 0.0)
                        quality_pct = quality_score * 100
                        # Always round down to 1 decimal place
                        quality_pct_display = math.floor(quality_pct * 10) / 10
                        
                        # Color code quality
                        if quality_pct >= 95:
                            quality_str = f"[green]{quality_pct_display:.0f}%[/green]"
                        elif quality_pct >= 80:
                            quality_str = f"[yellow]{quality_pct_display:.0f}%[/yellow]"
                        else:
                            quality_str = f"[red]{quality_pct_display:.0f}%[/red]"
                    
                    table.add_row(
                        interval,
                        interval_type,
                        f"{bar_count:,}" if bar_count > 0 else "0",
                        quality_str if bar_count > 0 else "N/A",
                        format_timestamp(start_date, include_seconds=False) if start_date else "N/A",
                        format_timestamp(end_date, include_seconds=False) if end_date else "N/A",
                    )
            except Exception as e:
                logger.warning(f"Error reading {interval} for {symbol}: {e}")
                table.add_row(
                    interval,
                    interval_type,
                    "Error",
                    "N/A",
                    "N/A",
                    "N/A",
                )
        
        console.print(table)
        console.print(f"\n[dim]Available intervals: {', '.join(sorted(intervals))}[/dim]")
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"List data error: {e}")


def data_info_command(symbol: str) -> None:
    """
    Show data info for a symbol
    
    Args:
        symbol: Stock symbol
    """
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            quality = dm.check_data_quality(session, symbol.upper())
            
            if quality['total_bars'] == 0:
                console.print(f"\n[yellow]No data found for {symbol.upper()}[/yellow]")
                return
            
            start_date, end_date = dm.get_date_range(session, symbol.upper())
            
            console.print(f"\n[cyan]Data Info: {symbol.upper()}[/cyan]")
            console.print(f"  Total bars: {quality['total_bars']:,}")
            console.print(f"  Start: {format_timestamp(start_date, include_seconds=False)}")
            console.print(f"  End: {format_timestamp(end_date, include_seconds=False)}")
            
            if start_date and end_date:
                duration = end_date - start_date
                days = duration.days + (duration.seconds / 86400)
                console.print(f"  Duration: {days:.1f} days")
                
                # Estimate trading days (assuming 6.5 hours per day, 390 minutes)
                trading_days = quality['total_bars'] / 390
                console.print(f"  Estimated trading days: {trading_days:.1f}")
            
            console.print()
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Data info error: {e}")


def data_quality_command(
    symbol: str,
    interval: str = "1m",
    start_date: str = None,
    end_date: str = None
) -> None:
    """Check data quality for a symbol using unified quality analyzer.
    
    Args:
        symbol: Stock symbol
        interval: Bar interval (e.g., "1m", "5m", "1d", "1w")
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
    """
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            quality = dm.check_data_quality(
                session,
                symbol.upper(),
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            if not quality.get('success') or quality['total_bars'] == 0:
                message = quality.get('message', 'No data found')
                console.print(f"\n[yellow]{message} for {symbol.upper()} {interval}[/yellow]")
                return
            
            # Build title
            title = f"\nData Quality: {symbol.upper()} {interval}"
            if start_date or end_date:
                title += f" ({start_date or 'start'} to {end_date or 'end'})"
            
            # Create table
            table = Table(title=title, show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right", style="white")
            
            table.add_row("Interval", interval)
            table.add_row("Total bars", f"{quality['total_bars']:,}")
            table.add_row("Expected bars", f"{quality['expected_bars']:,}")
            
            # Show missing or surplus bars
            missing = quality.get('missing_bars', 0)
            surplus = quality.get('surplus_bars', 0)
            if surplus > 0:
                table.add_row("Surplus bars", f"[green]+{surplus:,}[/green]")
            else:
                table.add_row("Missing bars", f"{missing:,}")
            
            # Show duplicates if any
            if quality.get('duplicate_bars', 0) > 0:
                table.add_row("Duplicate bars", f"{quality['duplicate_bars']:,}")
            
            quality_pct = quality['quality_score'] * 100
            # Always round down to 1 decimal place (99.99 => 99.9, not 100.0)
            quality_pct_display = math.floor(quality_pct * 10) / 10
            quality_color = "green" if quality_pct >= 95 else "yellow" if quality_pct >= 80 else "red"
            table.add_row("Quality score", f"[{quality_color}]{quality_pct_display:.1f}%[/{quality_color}]")
            
            if quality.get('date_range'):
                table.add_row("Start date", quality['date_range']['start'])
                table.add_row("End date", quality['date_range']['end'])
            
            console.print(table)
            
            # Show message
            console.print(f"\n[dim]{quality.get('message', '')}[/dim]")
            
            # Show gaps if any
            gaps = quality.get('gaps', [])
            if gaps:
                console.print(f"\n[yellow]Detected {len(gaps)} gap(s):[/yellow]")
                for i, gap in enumerate(gaps[:5], 1):  # Show first 5
                    console.print(
                        f"  {i}. {gap['start']} to {gap['end']} "
                        f"({gap['missing_count']} bars missing)"
                    )
                if len(gaps) > 5:
                    console.print(f"  ... and {len(gaps) - 5} more gaps")
            
            console.print()
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Data quality error: {e}", exc_info=True)


def select_data_api_command(api: str) -> None:
    """Select data API provider via DataManager (e.g., alpaca, schwab)."""
    dm = get_data_manager()
    ok = dm.select_data_api(api)
    if ok:
        console.print(f"[green]✓[/green] Data API provider set to [cyan]{dm.data_api}[/cyan] and connected")
    else:
        console.print(f"[red]✗[/red] Failed to connect data API provider [cyan]{api}[/cyan]")


def import_from_api_command(
    data_type: str,
    symbol: str,
    start_date: str,
    end_date: str,
) -> None:
    """Import data from external API via DataManager.import_from_api."""
    try:
        start_dt = parse_start_date(start_date)  # 00:00:00
        end_dt = parse_end_date(end_date)  # 23:59:59
    except ValueError:
        console.print("[red]Dates must be in YYYY-MM-DD format[/red]")
        return

    console.print(
        f"[yellow]Importing {data_type} data for {symbol.upper()}[/yellow]"
    )
    console.print(
        f"[dim]  From: {format_timestamp(start_dt)}[/dim]"
    )
    console.print(
        f"[dim]  To:   {format_timestamp(end_dt)}[/dim]"
    )

    dm = get_data_manager()

    try:
        with SessionLocal() as session:
            result = dm.import_from_api(
                session=session,
                data_type=data_type,
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
            )

        # Show summary feedback
        if result.get("success"):
            console.print(
                f"[green]✓[/green] {result.get('message', 'Import completed')}"
            )
        else:
            console.print(
                f"[yellow]![/yellow] {result.get('message', 'Import completed with no data')}"
            )

        total_rows = result.get("total_rows")
        imported = result.get("imported")
        if total_rows is not None and imported is not None:
            console.print(
                f"  Total rows from provider: {total_rows:,}\n"
                f"  Upserted into DB:        {imported:,}"
            )

        if result.get("date_range"):
            dr = result["date_range"]
            console.print(
                f"  Date range: {dr.get('start', 'N/A')} to {dr.get('end', 'N/A')}"
            )
    except NotImplementedError as e:
        console.print(f"[red]✗[/red] {e}")
        logger.warning(str(e))
    except Exception as e:
        console.print(f"[red]✗ Import error: {e}[/red]")
        logger.error(f"API import error: {e}")


def aggregate_command(
    target_interval: str,
    source_interval: str,
    symbol: str,
    start_date: str,
    end_date: str,
) -> None:
    """Aggregate existing Parquet data to new interval.
    
    Examples:
        data aggregate 5m 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1d 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1w 1d AAPL 2025-01-01 2025-12-31
    """
    console.print(
        f"\n[cyan]Aggregating {source_interval} → {target_interval} bars for {symbol.upper()}[/cyan]"
    )
    console.print(f"[dim]Date range: {start_date} to {end_date}[/dim]\n")
    
    dm = get_data_manager()
    
    try:
        with SessionLocal() as session:
            result = dm.aggregate_and_store(
                session=session,
                target_interval=target_interval,
                source_interval=source_interval,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
        
        # Display results
        if result.get("success"):
            console.print(f"[green]✓ Aggregation successful![/green]\n")
            console.print(f"  Mode: [cyan]{result.get('mode', 'unknown')}[/cyan]")
            console.print(f"  Source bars ({source_interval}): {result.get('source_bars', 0):,}")
            console.print(f"  Aggregated bars ({target_interval}): {result.get('aggregated_bars', 0):,}")
            console.print(f"  Files written: {result.get('files_written', 0)}")
            console.print(f"  Date range: {result.get('date_range', 'N/A')}")
            
            # Show reduction ratio
            source_bars = result.get('source_bars', 0)
            agg_bars = result.get('aggregated_bars', 0)
            if source_bars > 0 and agg_bars > 0:
                ratio = source_bars / agg_bars
                console.print(f"  Compression: {ratio:.1f}x ({source_bars:,} → {agg_bars:,})")
            
            console.print(f"\n[green]{result.get('message', 'Complete')}[/green]")
        else:
            console.print(f"[yellow]⚠ Aggregation incomplete[/yellow]\n")
            console.print(f"  {result.get('message', 'No details available')}")
            
            # Show what was processed
            if result.get('source_bars', 0) > 0:
                console.print(f"\n  Source bars loaded: {result.get('source_bars', 0):,}")
                console.print(f"  Aggregated bars: {result.get('aggregated_bars', 0)}")
    
    except ValueError as e:
        console.print(f"[red]✗ Validation error:[/red]\n  {e}")
        logger.warning(f"Aggregation validation error: {e}")
    except Exception as e:
        console.print(f"[red]✗ Aggregation error: {e}[/red]")
        logger.error(f"Aggregation error: {e}", exc_info=True)


def delete_symbol_command(
    symbol: str,
    interval: str = None,
    start_date: str = None,
    end_date: str = None
) -> None:
    """Delete market data for a symbol with optional filters.
    
    Args:
        symbol: Stock symbol
        interval: Optional interval filter (e.g., "1m", "5m"). If None, deletes ALL intervals.
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
    """
    # Build confirmation message
    delete_desc = f"{symbol.upper()}"
    if interval:
        delete_desc += f" {interval} data"
    else:
        delete_desc += " ALL intervals"
    
    if start_date or end_date:
        delete_desc += f" from {start_date or 'start'} to {end_date or 'end'}"
    
    if not Confirm.ask(
        f"\n[yellow]⚠ Delete {delete_desc}? This cannot be undone![/yellow]"
    ):
        console.print("[dim]Cancelled[/dim]")
        return
    
    try:
        dm = get_data_manager()
        result = dm.delete_data(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date
        )
        
        if result["success"]:
            console.print(f"\n[green]✓ {result['message']}[/green]")
            console.print(f"  Intervals deleted: {', '.join(result['intervals_deleted'])}")
            console.print(f"  Files deleted: {result['files_deleted']}\n")
        else:
            console.print(f"\n[yellow]{result['message']}[/yellow]\n")
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Delete data error: {e}")


def delete_all_command() -> None:
    """Delete ALL market data from database."""
    console.print("\n[red]⚠️  WARNING: You are about to DELETE ALL MARKET DATA![/red]")
    console.print(
        "[red]This will remove data for ALL symbols and CANNOT be undone![/red]\n"
    )

    if not Confirm.ask(
        "[yellow]Type 'yes' to confirm you want to delete everything[/yellow]"
    ):
        console.print("[dim]Cancelled[/dim]")
        return

    if not Confirm.ask(
        "\n[red]Are you ABSOLUTELY sure? This is your last chance![/red]"
    ):
        console.print("[dim]Cancelled[/dim]")
        return

    try:
        with SessionLocal() as session:
            manager = get_data_manager()
            deleted = manager.delete_all_data(session)

        console.print(
            f"\n[green]✓ Deleted ALL market data: {deleted:,} bars[/green]"
        )
        console.print("[dim]Database is now empty[/dim]\n")

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Delete all error: {e}")


def export_csv_command(
    data_type: str,
    symbol: str,
    start_date: str,
    end_date: Optional[str],
    file_path: str,
) -> None:
    """Export bars, ticks, or quotes to CSV using DataManager.

    data_type: "bar", "tick", or "quote" (case-insensitive)
    start_date: YYYY-MM-DD (required)
    end_date:   YYYY-MM-DD (optional, defaults to same day as start)
    file_path:  Path to CSV file to write
    """
    symbol_u = symbol.upper()
    kind = data_type.lower()
    if kind not in {"bar", "bars", "tick", "ticks", "quote", "quotes"}:
        console.print("[red]data_type must be 'bar', 'tick', or 'quote'[/red]")
        return

    # Parse dates
    try:
        start_dt = parse_start_date(start_date)  # 00:00:00
    except ValueError:
        console.print("[red]Start date must be in YYYY-MM-DD format[/red]")
        return

    end_dt = None
    if end_date:
        try:
            end_dt = parse_end_date(end_date)  # 23:59:59
        except ValueError:
            console.print("[red]End date must be in YYYY-MM-DD format[/red]")
            return
        # Inclusive day range: end at end_date + 1 day (exclusive)
        from datetime import timedelta
        end_dt = end_dt + timedelta(days=1)
    else:
        # Single day: [start, start+1 day)
        from datetime import timedelta
        end_dt = start_dt + timedelta(days=1)

    is_bar = kind in {"bar", "bars"}
    is_tick = kind in {"tick", "ticks"}
    is_quote = kind in {"quote", "quotes"}

    interval = "1m" if is_bar else ("tick" if is_tick else None)

    console.print(
        f"\n[cyan]Exporting {data_type} data for {symbol_u} to {file_path}...[/cyan]"
    )

    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            if is_quote:
                quotes = dm.get_quotes(session, symbol_u, start_dt, end_dt)
                records = quotes
            else:
                bars = dm.get_bars(session, symbol_u, start_dt, end_dt, interval=interval)
                records = bars

        if not records:
            console.print("[yellow]No data found for given range[/yellow]")
            return

        import csv
        from pathlib import Path

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="") as f:
            writer = csv.writer(f)

            if is_quote:
                writer.writerow([
                    "symbol",
                    "timestamp",
                    "bid_price",
                    "bid_size",
                    "ask_price",
                    "ask_size",
                    "exchange",
                ])
                for q in records:
                    writer.writerow([
                        q.symbol,
                        q.timestamp.isoformat(),
                        q.bid_price,
                        q.bid_size,
                        q.ask_price,
                        q.ask_size,
                        q.exchange,
                    ])
            else:
                writer.writerow([
                    "symbol",
                    "timestamp",
                    "interval",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ])
                for bar in records:
                    writer.writerow([
                        bar.symbol,
                        bar.timestamp.isoformat(),
                        interval,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                    ])

        console.print(
            f"[green]✓[/green] Exported {len(records):,} {data_type} rows for {symbol_u} to {file_path}"
        )

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error exporting CSV: {e}[/red]")
        logger.error(f"Export CSV error: {e}")


def on_demand_bars_command(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = "1m",
) -> None:
    """Fetch and display on-demand bars via DataManager.

    This reads from the local DB only (no external API).
    """
    try:
        start_dt = parse_start_date(start_date)  # 00:00:00
        end_dt = parse_end_date(end_date)  # 23:59:59
    except ValueError:
        console.print("[red]Dates must be in YYYY-MM-DD format[/red]")
        return

    if start_dt >= end_dt:
        console.print("[red]start_date must be before end_date[/red]")
        return

    with SessionLocal() as session:
        dm = get_data_manager()
        bars = dm.get_bars(session, symbol.upper(), start_dt, end_dt, interval=interval)

    if not bars:
        console.print(f"[yellow]No bar data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand bars: {symbol.upper()} ({interval})", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")

    max_rows = 200
    for bar in bars[:max_rows]:
        ts = format_timestamp(bar.timestamp, include_seconds=False)
        table.add_row(
            ts,
            f"{bar.open:.2f}",
            f"{bar.high:.2f}",
            f"{bar.low:.2f}",
            f"{bar.close:.2f}",
            f"{bar.volume:.0f}",
        )

    console.print(table)
    if len(bars) > max_rows:
        console.print(
            f"[dim]Showing first {max_rows} of {len(bars):,} bars. Use export-csv for full export.[/dim]"
        )


def on_demand_ticks_command(
    symbol: str,
    start_date: str,
    end_date: str,
) -> None:
    """Fetch and display on-demand ticks via DataManager.get_ticks."""
    try:
        start_dt = parse_start_date(start_date)  # 00:00:00
        end_dt = parse_end_date(end_date)  # 23:59:59
    except ValueError:
        console.print("[red]Dates must be in YYYY-MM-DD format[/red]")
        return

    if start_dt >= end_dt:
        console.print("[red]start_date must be before end_date[/red]")
        return

    with SessionLocal() as session:
        dm = get_data_manager()
        ticks = dm.get_ticks(session, symbol.upper(), start_dt, end_dt)

    if not ticks:
        console.print(f"[yellow]No tick data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand ticks: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Size", justify="right")

    max_rows = 200
    for t in ticks[:max_rows]:
        ts = format_timestamp(t.timestamp)
        table.add_row(ts, f"{t.price:.4f}", f"{t.size:.0f}")

    console.print(table)
    if len(ticks) > max_rows:
        console.print(
            f"[dim]Showing first {max_rows} of {len(ticks):,} ticks. Use export-csv for full export.[/dim]"
        )


def on_demand_quotes_command(
    symbol: str,
    start_date: str,
    end_date: str,
) -> None:
    """Fetch and display on-demand quotes via DataManager.get_quotes."""
    try:
        start_dt = parse_start_date(start_date)  # 00:00:00
        end_dt = parse_end_date(end_date)  # 23:59:59
    except ValueError:
        console.print("[red]Dates must be in YYYY-MM-DD format[/red]")
        return

    if start_dt >= end_dt:
        console.print("[red]start_date must be before end_date[/red]")
        return

    with SessionLocal() as session:
        dm = get_data_manager()
        quotes = dm.get_quotes(session, symbol.upper(), start_dt, end_dt)

    if not quotes:
        console.print(f"[yellow]No quote data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand quotes: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("BidSize", justify="right")
    table.add_column("AskSize", justify="right")

    max_rows = 200
    for q in quotes[:max_rows]:
        ts = format_timestamp(q.timestamp)
        table.add_row(
            ts,
            f"{q.bid_price:.4f}",
            f"{q.ask_price:.4f}",
            f"{q.bid_size:.0f}",
            f"{q.ask_size:.0f}",
        )

    console.print(table)
    if len(quotes) > max_rows:
        console.print(
            f"[dim]Showing first {max_rows} of {len(quotes):,} quotes. Use export-csv for full export.[/dim]"
        )


def _consume_stream_to_file(
    stream_iterator,
    file_path: str,
    data_type: str,  # "bar", "tick", or "quote"
) -> None:
    """Background task to consume stream and write to file."""
    import csv as _csv
    
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with path.open("w", newline="") as f:
            writer = _csv.writer(f)
            
            # Write header based on data type
            if data_type == "bar":
                writer.writerow(["symbol", "timestamp", "interval", "open", "high", "low", "close", "volume"])
            elif data_type == "tick":
                writer.writerow(["symbol", "timestamp", "price", "size"])
            elif data_type == "quote":
                writer.writerow(["symbol", "timestamp", "bid_price", "bid_size", "ask_price", "ask_size", "exchange"])
            
            count = 0
            for item in stream_iterator:
                count += 1
                if data_type == "bar":
                    writer.writerow([item.symbol, item.timestamp.isoformat(), "1m", item.open, item.high, item.low, item.close, item.volume])
                elif data_type == "tick":
                    writer.writerow([item.symbol, item.timestamp.isoformat(), item.price, item.size])
                elif data_type == "quote":
                    writer.writerow([item.symbol, item.timestamp.isoformat(), item.bid_price, item.bid_size, item.ask_price, item.ask_size, item.exchange])
            
            logger.info(f"Stream file writer completed: {count} items written to {file_path}")
    except Exception as e:
        logger.error(f"Error writing stream to file {file_path}: {e}")


def stream_bars_command(
    symbol: str,
    interval: str = "1m",
    file_path: Optional[str] = None,
) -> None:
    """Fetch bars from DB (blocking), then start streaming via coordinator (background)."""
    from uuid import uuid4 as _uuid4

    stream_id = _uuid4().hex
    
    console.print(f"[cyan]Fetching bar data for {symbol.upper()} from database...[/cyan]")
    
    try:
        dm = get_data_manager()
        
        # Initialize backtest if needed  
        with SessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                dm.init_backtest(init_session)
        
        # **Load bars from Parquet**
        from app.managers.data_manager.parquet_storage import parquet_storage
        from datetime import time
        
        now = dm.get_current_time()
        
        # Determine end time
        if dm.backtest_end_date is None:
            end_date = now
        else:
            # Get market close time from TimeManager
            with SessionLocal() as db_session:
                time_mgr = dm.system_manager.get_time_manager()
                session_obj = time_mgr.get_trading_session(db_session, dm.backtest_end_date)
                if session_obj:
                    end_date = session_obj.get_regular_close_datetime()
                else:
                    end_date = now
        
        # Load bars from Parquet
        console.print(f"[yellow]Loading {interval} bars for {symbol.upper()} from Parquet...[/yellow]")
        df = parquet_storage.read_bars(interval, symbol.upper(), start_date=now, end_date=end_date)
        
        # Convert DataFrame to list of dicts (BarData compatible)
        bars = df.to_dict('records') if not df.empty else []
        
        bar_count = len(bars)
        console.print(f"[green]✓[/green] Loaded {bar_count:,} bars from Parquet")
        
        # OLD ARCHITECTURE REMOVED:
        # This command used BacktestStreamCoordinator which is no longer used.
        # SessionCoordinator handles all streaming now via session config.
        console.print("[yellow]⚠ This command is deprecated - use session config to stream bars[/yellow]")
        return
        
        # OLD CODE COMMENTED OUT:
        # from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        # coordinator = get_coordinator()
        # coordinator.start_worker()
        # success, input_queue = coordinator.register_stream(symbol.upper(), StreamType.BAR)
        # coordinator.feed_data_list(symbol.upper(), StreamType.BAR, bars)
        
        # Get merged stream from coordinator
        stream_iterator = coordinator.get_merged_stream()
        
        # Start file writer in background if requested
        if file_path:
            def consume_and_close():
                try:
                    _consume_stream_to_file(stream_iterator, file_path, "bar")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create thread and start it in background
            thread = threading.Thread(target=consume_and_close, daemon=True)
            register_background_task(thread)
            thread.start()
            
            console.print(f"[green]✓[/green] Bar stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Bar stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-bars' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting bar stream: {e}[/red]")
        logger.error(f"Bar stream startup error: {e}")


def stream_ticks_command(
    symbol: str,
    file_path: Optional[str] = None,
) -> None:
    """Fetch ticks from DB (blocking), then start streaming via coordinator (background)."""
    from uuid import uuid4 as _uuid4

    stream_id = _uuid4().hex
    
    console.print(f"[cyan]Fetching tick data for {symbol.upper()} from database...[/cyan]")
    
    try:
        dm = get_data_manager()
        
        # Initialize backtest if needed  
        with SessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                dm.init_backtest(init_session)
        
        # **Load ticks (1s bars) from Parquet**
        from app.managers.data_manager.parquet_storage import parquet_storage
        from datetime import time
        
        now = dm.get_current_time()
        
        # Determine end time
        if dm.backtest_end_date is None:
            end_date = now
        else:
            # Get market close time from TimeManager
            with SessionLocal() as db_session:
                time_mgr = dm.system_manager.get_time_manager()
                session_obj = time_mgr.get_trading_session(db_session, dm.backtest_end_date)
                if session_obj:
                    end_date = session_obj.get_regular_close_datetime()
                else:
                    end_date = now
        
        # Load 1s bars from Parquet (ticks are stored as 1s bars)
        console.print(f"[yellow]Loading ticks (1s bars) for {symbol.upper()} from Parquet...[/yellow]")
        df = parquet_storage.read_bars('1s', symbol.upper(), start_date=now, end_date=end_date)
        
        # Convert DataFrame to list of dicts
        ticks = df.to_dict('records') if not df.empty else []
        
        tick_count = len(ticks)
        console.print(f"[green]✓[/green] Loaded {tick_count:,} ticks (1s bars) from Parquet")
        
        # OLD ARCHITECTURE REMOVED:
        # This command used BacktestStreamCoordinator which is no longer used.
        console.print("[yellow]⚠ This command is deprecated - use session config to stream ticks[/yellow]")
        return
        
        # OLD CODE COMMENTED OUT:
        # from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        # coordinator = get_coordinator()
        # coordinator.start_worker()
        
        # Register stream
        success, input_queue = coordinator.register_stream(symbol.upper(), StreamType.TICK)
        if not success:
            console.print(f"[red]✗ Stream already active for {symbol.upper()}[/red]")
            return
        
        # Feed all data directly to queue (no async, instant!)
        coordinator.feed_data_list(symbol.upper(), StreamType.TICK, ticks)
        
        # Get merged stream from coordinator
        stream_iterator = coordinator.get_merged_stream()
        
        # Start file writer in background if requested
        if file_path:
            def consume_and_close():
                try:
                    _consume_stream_to_file(stream_iterator, file_path, "tick")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create thread and start it in background
            thread = threading.Thread(target=consume_and_close, daemon=True)
            register_background_task(thread)
            thread.start()
            
            console.print(f"[green]✓[/green] Tick stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Tick stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-ticks' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting tick stream: {e}[/red]")
        logger.error(f"Tick stream startup error: {e}")


def stream_quotes_command(
    symbol: str,
    file_path: Optional[str] = None,
) -> None:
    """Fetch quotes from DB (blocking), then start streaming via coordinator (background)."""
    from uuid import uuid4 as _uuid4

    stream_id = _uuid4().hex
    
    console.print(f"[cyan]Fetching quote data for {symbol.upper()} from database...[/cyan]")
    
    try:
        dm = get_data_manager()
        
        # Initialize backtest if needed  
        with SessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                dm.init_backtest(init_session)
        
        # **Load quotes from Parquet**
        from app.managers.data_manager.parquet_storage import parquet_storage
        from datetime import time
        
        now = dm.get_current_time()
        
        # Determine end time
        if dm.backtest_end_date is None:
            end_date = now
        else:
            # Get market close time from TimeManager
            with SessionLocal() as db_session:
                time_mgr = dm.system_manager.get_time_manager()
                session_obj = time_mgr.get_trading_session(db_session, dm.backtest_end_date)
                if session_obj:
                    end_date = session_obj.get_regular_close_datetime()
                else:
                    end_date = now
        
        # Load quotes from Parquet
        console.print(f"[yellow]Loading quotes for {symbol.upper()} from Parquet...[/yellow]")
        df = parquet_storage.read_quotes(symbol.upper(), start_date=now, end_date=end_date)
        
        # Convert DataFrame to list of dicts
        quotes = df.to_dict('records') if not df.empty else []
        
        quote_count = len(quotes)
        console.print(f"[green]✓[/green] Loaded {quote_count:,} quotes from Parquet")
        
        # OLD ARCHITECTURE REMOVED:
        # This command used BacktestStreamCoordinator which is no longer used.
        console.print("[yellow]⚠ This command is deprecated - use session config to stream quotes[/yellow]")
        return
        
        # OLD CODE COMMENTED OUT:
        # from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        # coordinator = get_coordinator()
        # coordinator.start_worker()
        
        # Register stream
        success, input_queue = coordinator.register_stream(symbol.upper(), StreamType.QUOTE)
        if not success:
            console.print(f"[red]✗ Stream already active for {symbol.upper()}[/red]")
            return
        
        # Feed all data directly to queue (no async, instant!)
        coordinator.feed_data_list(symbol.upper(), StreamType.QUOTE, quotes)
        
        # Get merged stream from coordinator
        stream_iterator = coordinator.get_merged_stream()
        
        # Start file writer in background if requested
        if file_path:
            def consume_and_close():
                try:
                    _consume_stream_to_file(stream_iterator, file_path, "quote")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create thread and start it in background
            thread = threading.Thread(target=consume_and_close, daemon=True)
            register_background_task(thread)
            thread.start()
            
            console.print(f"[green]✓[/green] Quote stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Quote stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-quotes' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting quote stream: {e}[/red]")
        logger.error(f"Quote stream startup error: {e}")


def latest_bar_command(symbol: str, interval: str = "1m") -> None:
    """Show the latest bar for a symbol from the local DB."""
    with SessionLocal() as session:
        dm = get_data_manager()
        bar = dm.get_latest_bar(session, symbol.upper(), interval=interval)

    if not bar:
        console.print(f"[yellow]No bar data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest bar: {symbol.upper()} ({interval})", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")

    ts = format_timestamp(bar.timestamp, include_seconds=False)
    table.add_row(
        ts,
        f"{bar.open:.2f}",
        f"{bar.high:.2f}",
        f"{bar.low:.2f}",
        f"{bar.close:.2f}",
        f"{bar.volume:.0f}",
    )

    console.print(table)


def latest_tick_command(symbol: str) -> None:
    """Show the latest tick for a symbol from the local DB."""
    with SessionLocal() as session:
        dm = get_data_manager()
        tick = dm.get_latest_tick(session, symbol.upper())

    if not tick:
        console.print(f"[yellow]No tick data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest tick: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Size", justify="right")

    ts = format_timestamp(tick.timestamp)
    table.add_row(ts, f"{tick.price:.4f}", f"{tick.size:.0f}")

    console.print(table)


def latest_quote_command(symbol: str) -> None:
    """Show the latest bid/ask quote for a symbol from the local DB."""
    with SessionLocal() as session:
        dm = get_data_manager()
        quote = dm.get_latest_quote(session, symbol.upper())

    if not quote:
        console.print(f"[yellow]No quote data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest quote: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp (ET)", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("BidSize", justify="right")
    table.add_column("AskSize", justify="right")

    ts = format_timestamp(quote.timestamp)
    table.add_row(
        ts,
        f"{quote.bid_price:.4f}",
        f"{quote.ask_price:.4f}",
        f"{quote.bid_size:.0f}",
        f"{quote.ask_size:.0f}",
    )

    console.print(table)


def set_backtest_speed_command(speed: str) -> None:
    """Set DataManager backtest speed multiplier.
    
    Args:
        speed: Speed multiplier as string (e.g., "0" for max, "1.0" for realtime, "2.0" for 2x speed)
    """
    from app.config import settings

    # Parse speed as float
    try:
        speed_value = float(speed)
    except ValueError:
        console.print("[red]Speed must be a number (e.g., 0 for max, 1.0 for realtime, 2.0 for 2x speed)[/red]")
        return
    
    if speed_value < 0:
        console.print("[red]Speed must be >= 0[/red]")
        return

    try:
        dm = get_data_manager()
        dm.set_backtest_speed(speed_value)

        console.print("[green]✓[/green] Backtest speed updated:")
        console.print(f"  speed_multiplier: {speed_value}")
        if speed_value == 0:
            console.print("  [dim]Mode: Maximum speed (no pacing)[/dim]")
        elif speed_value == 1.0:
            console.print("  [dim]Mode: Realtime speed[/dim]")
        elif speed_value > 1.0:
            console.print(f"  [dim]Mode: {speed_value}x realtime speed[/dim]")
        else:
            console.print(f"  [dim]Mode: {speed_value}x realtime speed (slower)[/dim]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error setting backtest speed: {e}[/red]")
        logger.error(f"Set backtest speed error: {e}")


def set_backtest_window_command(
    start_date: str,
    end_date: Optional[str] = None,
) -> None:
    """Set/override the DataManager backtest window.

    ``start_date`` and optional ``end_date`` should be provided as
    ``YYYY-MM-DD``. If ``end_date`` is omitted, the current
    ``backtest_end_date`` is preserved (or falls back to ``start_date`` if it
    has not been initialized yet).
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        console.print("[red]Start date must be in YYYY-MM-DD format[/red]")
        return

    end_dt = None
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            console.print("[red]End date must be in YYYY-MM-DD format[/red]")
            return

    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            dm.set_backtest_window(session, start_dt, end_dt)

            # After the call, dm.backtest_end_date reflects the effective end
            # date chosen by DataManager (either explicit, reused, or
            # computed last trading day).
            effective_end = dm.backtest_end_date

        console.print("[green]✓[/green] Backtest window updated:")
        console.print(f"  Start date: {start_dt.isoformat()}")
        console.print(f"  End date:   {effective_end.isoformat() if effective_end else start_dt.isoformat()}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error updating backtest window: {e}[/red]")
        logger.error(f"Set backtest window error: {e}")


def stop_bars_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active bar stream via DataManager.stop_bars_stream."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            # session not needed for stop, but kept for symmetry and future use
            _ = session
            dm.stop_bars_stream(stream_id)
        console.print("[green]✓[/green] Bar stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping bar stream: {e}[/red]")
        logger.error(f"Stop bar stream error: {e}")


def stop_ticks_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active tick stream via DataManager.stop_ticks_stream."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            _ = session
            dm.stop_ticks_stream(stream_id)
        console.print("[green]✓[/green] Tick stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping tick stream: {e}[/red]")
        logger.error(f"Stop tick stream error: {e}")


def stop_quotes_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active quote stream via DataManager.stop_quotes_stream."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            _ = session
            dm.stop_quotes_stream(stream_id)
        console.print("[green]✓[/green] Quote stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping quote stream: {e}[/red]")
        logger.error(f"Stop quote stream error: {e}")


def stop_all_streams_command() -> None:
    """Stop ALL active data streams and coordinator worker via DataManager.stop_all_streams."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            _ = session
            dm.stop_all_streams()
        console.print("[green]✓[/green] All streams stopped (bars, ticks, quotes, coordinator)")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping all streams: {e}[/red]")
        logger.error(f"Stop all streams error: {e}")


def snapshot_command(symbol: str) -> None:
    """Get latest snapshot from data provider (live mode only)."""
    try:
        dm = get_data_manager()
        snapshot = dm.get_snapshot(symbol)
        
        if snapshot is None:
            console.print(f"[yellow]✗ No snapshot available for {symbol}[/yellow]")
            return
        
        console.print(f"\n[bold cyan]Snapshot for {symbol}[/bold cyan]\n")
        
        # Latest trade
        if snapshot.get("latest_trade"):
            trade = snapshot["latest_trade"]
            console.print(f"[bold]Latest Trade:[/bold]")
            console.print(f"  Price: ${trade['price']:.2f}")
            console.print(f"  Size: {trade['size']:,}")
            console.print(f"  Time: {trade['timestamp']}\n")
        
        # Latest quote
        if snapshot.get("latest_quote"):
            quote = snapshot["latest_quote"]
            console.print(f"[bold]Latest Quote:[/bold]")
            console.print(f"  Bid: ${quote['bid_price']:.2f} x {quote['bid_size']:,}")
            console.print(f"  Ask: ${quote['ask_price']:.2f} x {quote['ask_size']:,}")
            console.print(f"  Spread: ${quote['ask_price'] - quote['bid_price']:.2f}\n")
        
        # Daily bar
        if snapshot.get("daily_bar"):
            bar = snapshot["daily_bar"]
            console.print(f"[bold]Today's Bar:[/bold]")
            console.print(f"  Open: ${bar['open']:.2f}")
            console.print(f"  High: ${bar['high']:.2f}")
            console.print(f"  Low: ${bar['low']:.2f}")
            console.print(f"  Close: ${bar['close']:.2f}")
            console.print(f"  Volume: {bar['volume']:,}\n")
        
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error fetching snapshot: {e}[/red]")
        logger.error(f"Snapshot command error: {e}")


def session_volume_command(symbol: str) -> None:
    """Get cumulative volume for current trading session."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            volume = dm.get_current_session_volume(session, symbol)
            
            console.print(f"\n[bold cyan]{symbol} Session Volume[/bold cyan]")
            console.print(f"Cumulative Volume: [green]{volume:,}[/green] shares\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error fetching session volume: {e}[/red]")
        logger.error(f"Session volume command error: {e}")


def session_high_low_command(symbol: str) -> None:
    """Get session high and low prices."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            high, low = dm.get_current_session_high_low(session, symbol)
            
            if high is None or low is None:
                console.print(f"[yellow]No session data available for {symbol}[/yellow]")
                return
            
            console.print(f"\n[bold cyan]{symbol} Session High/Low[/bold cyan]")
            console.print(f"Session High: [green]${high:.2f}[/green]")
            console.print(f"Session Low: [red]${low:.2f}[/red]")
            console.print(f"Range: ${high - low:.2f}\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error fetching session high/low: {e}[/red]")
        logger.error(f"Session high/low command error: {e}")


def avg_volume_command(symbol: str, days: int) -> None:
    """Get average daily volume over specified trading days."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            avg_vol = dm.get_average_volume(session, symbol, days)
            
            console.print(f"\n[bold cyan]{symbol} Average Volume ({days} days)[/bold cyan]")
            console.print(f"Average Daily Volume: [green]{avg_vol:,.0f}[/green] shares\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error calculating average volume: {e}[/red]")
        logger.error(f"Average volume command error: {e}")


def high_low_command(symbol: str, days: int) -> None:
    """Get historical high/low prices over specified period."""
    try:
        with SessionLocal() as session:
            dm = get_data_manager()
            high, low = dm.get_historical_high_low(session, symbol, days)
            
            if high is None or low is None:
                console.print(f"[yellow]No data available for {symbol}[/yellow]")
                return
            
            console.print(f"\n[bold cyan]{symbol} Historical High/Low ({days} days)[/bold cyan]")
            console.print(f"Highest: [green]${high:.2f}[/green]")
            console.print(f"Lowest: [red]${low:.2f}[/red]")
            console.print(f"Range: ${high - low:.2f}\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error fetching historical high/low: {e}[/red]")
        logger.error(f"Historical high/low command error: {e}")


app = typer.Typer()


@app.command("list")
def data_list(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Show all available intervals for a symbol (seconds, minutes, days, weeks, quotes)."""
    list_symbols_command(symbol)


@app.command("info")
def data_info(symbol: str = typer.Argument(..., help="Stock symbol")) -> None:
    """Show data info for a symbol."""
    data_info_command(symbol)


@app.command("quality")
def data_quality(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    interval: str = typer.Option("1m", "--interval", "-i", help="Bar interval (e.g., 1m, 5m, 1d)"),
    start_date: str = typer.Option(None, "--start", help="Optional start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, "--end", help="Optional end date (YYYY-MM-DD)"),
) -> None:
    """Check data quality for a symbol with detailed gap analysis.
    
    Examples:
        data quality AAPL                      # Check 1m data (default)
        data quality AAPL -i 5m                # Check 5m data
        data quality AAPL -i 1d --start 2025-07-01 --end 2025-07-31
    """
    data_quality_command(symbol, interval, start_date, end_date)


@app.command("delete")
def data_delete(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    interval: str = typer.Option(None, "--interval", "-i", help="Optional interval (e.g., 1m, 5m, 1d)"),
    start_date: str = typer.Option(None, "--start", help="Optional start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, "--end", help="Optional end date (YYYY-MM-DD)"),
) -> None:
    """Delete market data for a symbol with optional filters.
    
    Examples:
        data delete AAPL                           # Delete all data
        data delete AAPL --interval 5m             # Delete only 5m data
        data delete AAPL --start 2025-07-01        # Delete from July 2025 onwards
        data delete AAPL -i 1m --start 2025-07-01 --end 2025-07-31
    """
    delete_symbol_command(symbol, interval, start_date, end_date)


@app.command("delete-all")
def data_delete_all() -> None:
    """Delete ALL data (⚠)."""
    delete_all_command()


@app.command("backtest-speed")
def backtest_speed(
    speed: str = typer.Argument(..., help="Backtest speed multiplier: 0=max, 1.0=realtime, 2.0=2x speed, 0.5=half speed"),
) -> None:
    """Set backtest execution speed multiplier."""
    set_backtest_speed_command(speed)


@app.command("backtest-window")
def backtest_window(
    start_date: str = typer.Argument(..., help="Backtest start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Argument(
        None,
        help="Optional backtest end date (YYYY-MM-DD)",
    ),
) -> None:
    """Set DataManager backtest window dates."""
    set_backtest_window_command(start_date, end_date)


@app.command("export-csv")
def export_csv(
    data_type: str = typer.Argument(..., help="Data type: 'bar' or 'tick'"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Argument(
        None,
        help="Optional end date (YYYY-MM-DD); defaults to single day",
    ),
    file_path: str = typer.Option(..., "--file", "-f", help="Output CSV file path"),
) -> None:
    """Export bars or ticks to CSV via DataManager (data export-csv)."""
    export_csv_command(data_type, symbol, start_date, end_date, file_path)


@app.command("bars")
def on_demand_bars(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
    interval: str = typer.Option("1m", "--interval", help="Bar interval (e.g., 1m, tick)"),
) -> None:
    """Fetch and display bars from the local DB (no API calls)."""
    on_demand_bars_command(symbol, start_date, end_date, interval)


@app.command("ticks")
def on_demand_ticks(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Fetch and display ticks from the local DB (no API calls)."""
    on_demand_ticks_command(symbol, start_date, end_date)


@app.command("quotes")
def on_demand_quotes(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Fetch and display quotes from the local DB (no API calls)."""
    on_demand_quotes_command(symbol, start_date, end_date)


@app.command("latest-bar")
def latest_bar(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    interval: str = typer.Option("1m", "--interval", help="Bar interval (e.g., 1m, tick)"),
) -> None:
    """Show the latest bar for a symbol."""
    latest_bar_command(symbol, interval)


@app.command("latest-tick")
def latest_tick(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Show the latest tick for a symbol."""
    latest_tick_command(symbol)


@app.command("latest-quote")
def latest_quote(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Show the latest bid/ask quote for a symbol."""
    latest_quote_command(symbol)


@app.command("session")
def session(
    refresh_seconds: Optional[int] = typer.Argument(None, help="Auto-refresh interval in seconds (default: 1s, use 0 to display once)"),
    csv_file: Optional[str] = typer.Argument(None, help="CSV file path to export data (default: validation/test_session.csv, always overwrites)"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Duration to run in seconds (default: run indefinitely)"),
    no_live: bool = typer.Option(False, "--no-live", help="Disable live updating, print each refresh (better for scripts)"),
) -> None:
    """Display live session data with auto-refresh (default: 1s). CSV export not yet implemented in new version."""
    from app.cli.session_data_display import data_session_command
    data_session_command(refresh_seconds, csv_file, duration, no_live)


@app.command("validate")
def validate(
    csv_file: Optional[str] = typer.Argument(None, help="CSV file to validate (default: validation/test_session.csv)"),
    config_file: Optional[str] = typer.Option(None, "--config", help="Session config JSON (default: session_configs/example_session.json)"),
    db_check: bool = typer.Option(False, "--db-check", help="Enable database cross-validation"),
) -> None:
    """Validate session data CSV dump against behavioral requirements and config expectations."""
    import subprocess
    from pathlib import Path
    
    # Build command
    script_path = Path("validation/validate_session_dump.py")
    if not script_path.exists():
        typer.echo("Error: Validation script not found at validation/validate_session_dump.py", err=True)
        raise typer.Exit(1)
    
    cmd = ["python", str(script_path)]
    
    if csv_file:
        cmd.append(csv_file)
    
    if config_file:
        cmd.extend(["--config", config_file])
    
    if db_check:
        cmd.append("--db-check")
    
    # Run validation script
    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)


@app.command("stream-bars")
def stream_bars(
    interval: str = typer.Argument(..., help="Bar interval (e.g., 1m)"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    file_path: Optional[str] = typer.Argument(None, help="Optional output CSV file"),
) -> None:
    """Start streaming bars to console or CSV file."""
    stream_bars_command(symbol, interval, file_path)


@app.command("stream-ticks")
def stream_ticks(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    file_path: Optional[str] = typer.Argument(None, help="Optional output CSV file"),
) -> None:
    """Start streaming ticks to console or CSV file."""
    stream_ticks_command(symbol, file_path)


@app.command("stream-quotes")
def stream_quotes(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    file_path: Optional[str] = typer.Argument(None, help="Optional output CSV file"),
) -> None:
    """Start streaming quotes to console or CSV file."""
    stream_quotes_command(symbol, file_path)


@app.command("stop-stream-bars")
def stop_stream_bars(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active bar stream(s) to stop."""
    stop_bars_stream_command(stream_id)


@app.command("stop-stream-ticks")
def stop_stream_ticks(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active tick stream(s) to stop."""
    stop_ticks_stream_command(stream_id)


@app.command("stop-stream-quotes")
def stop_stream_quotes(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active quote stream(s) to stop."""
    stop_quotes_stream_command(stream_id)


@app.command("stop-all-streams")
def stop_all_streams() -> None:
    """Stop ALL active data streams (bars, ticks, quotes) and coordinator worker."""
    stop_all_streams_command()


@app.command("snapshot")
def snapshot(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get latest snapshot from data provider (live mode only)."""
    snapshot_command(symbol)


@app.command("session-volume")
def session_volume(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get cumulative volume for current trading session."""
    session_volume_command(symbol)


@app.command("session-high-low")
def session_high_low(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get session high and low prices."""
    session_high_low_command(symbol)


@app.command("avg-volume")
def avg_volume(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    days: int = typer.Argument(..., help="Number of trading days"),
) -> None:
    """Get average daily volume over specified trading days."""
    avg_volume_command(symbol, days)


@app.command("high-low")
def high_low(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    days: int = typer.Argument(..., help="Number of days lookback"),
) -> None:
    """Get historical high/low prices over specified period."""
    high_low_command(symbol, days)


@app.command("api")
def set_api(
    api: str = typer.Argument(
        ..., help="Data API provider (e.g., alpaca, schwab)"
    ),
) -> None:
    """Select data API provider via DataManager and auto-connect."""
    select_data_api_command(api)


@app.command("import-api")
def import_api(
    data_type: str = typer.Argument(..., help="Data type (e.g., 1m, tick)"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Import data from external API via DataManager.import_from_api."""
    import_from_api_command(data_type, symbol, start_date, end_date)


@app.command("import-file")
def import_file(
    file_path: str = typer.Argument(..., help="Path to CSV file"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
) -> None:
    """Import CSV data via DataManager (data import-file)."""
    import_csv_command(file_path, symbol, start_date, end_date)


@app.command("aggregate")
def aggregate_data(
    target: str = typer.Argument(..., help="Target interval (5m, 1d, 1w)"),
    source: str = typer.Argument(..., help="Source interval (1s, 1m, 5m, 1d)"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Aggregate existing Parquet data to new interval.
    
    Examples:
        data aggregate 5m 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1d 1m AAPL 2025-07-01 2025-07-31
        data aggregate 1w 1d AAPL 2025-01-01 2025-12-31
    """
    aggregate_command(target, source, symbol, start_date, end_date)


# ============================================================================
# Dynamic Symbol Management Commands
# ============================================================================

def add_symbol_command(symbol: str, streams: Optional[str]) -> None:
    """Add a symbol dynamically to the active session."""
    try:
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        
        # Check if system is running
        if not system_mgr.is_running():
            console.print("[yellow]⚠ System is not running. Start it first with 'system start'[/yellow]")
            return
        
        # Get session coordinator
        if not hasattr(system_mgr, '_coordinator') or not system_mgr._coordinator:
            console.print("[yellow]⚠ No active session. Session coordinator not initialized[/yellow]")
            return
        
        coordinator = system_mgr._coordinator
        
        # Parse streams
        stream_list = None
        if streams:
            stream_list = [s.strip() for s in streams.split(",")]
        
        # Add the symbol
        console.print(f"[cyan]Adding symbol {symbol.upper()} to active session...[/cyan]")
        result = coordinator.add_symbol(symbol.upper(), streams=stream_list)
        
        if result:
            console.print(f"[green]✓ Symbol {symbol.upper()} queued for addition[/green]")
            if coordinator.mode == "backtest":
                console.print("[dim]  Backtest mode: Streaming will pause, load historical data, and catch up[/dim]")
            else:
                console.print("[dim]  Live mode: Historical data loading, stream starting[/dim]")
        else:
            console.print(f"[red]✗ Failed to add symbol {symbol.upper()}[/red]")
            console.print("[dim]  Symbol may already exist or session not running[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error adding symbol: {e}[/red]")
        logger.error(f"Add symbol command error: {e}", exc_info=True)


def remove_symbol_command(symbol: str) -> None:
    """Remove a symbol from the active session."""
    try:
        from app.managers.system_manager import get_system_manager
        system_mgr = get_system_manager()
        
        # Check if system is running
        if not system_mgr.is_running():
            console.print("[yellow]⚠ System is not running[/yellow]")
            return
        
        # Get session coordinator
        if not hasattr(system_mgr, '_coordinator') or not system_mgr._coordinator:
            console.print("[yellow]⚠ No active session[/yellow]")
            return
        
        coordinator = system_mgr._coordinator
        
        # Remove the symbol
        console.print(f"[cyan]Removing symbol {symbol.upper()} from active session...[/cyan]")
        result = coordinator.remove_symbol(symbol.upper())
        
        if result:
            console.print(f"[green]✓ Symbol {symbol.upper()} removed from session[/green]")
        else:
            console.print(f"[red]✗ Failed to remove symbol {symbol.upper()}[/red]")
            console.print("[dim]  Symbol may not be dynamically added[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error removing symbol: {e}[/red]")
        logger.error(f"Remove symbol command error: {e}", exc_info=True)


@app.command("add-symbol")
def add_symbol(
    symbol: str = typer.Argument(..., help="Stock symbol to add"),
    streams: Optional[str] = typer.Option(None, "--streams", help="Comma-separated stream types (default: 1m)"),
) -> None:
    """Add a symbol dynamically to the active session."""
    add_symbol_command(symbol, streams)


@app.command("remove-symbol")
def remove_symbol(
    symbol: str = typer.Argument(..., help="Stock symbol to remove"),
) -> None:
    """Remove a symbol from the active session."""
    remove_symbol_command(symbol)
