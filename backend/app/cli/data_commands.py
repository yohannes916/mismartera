"""
CLI commands for market data management
"""
from pathlib import Path
from typing import Optional
from datetime import datetime, date
import asyncio

import typer
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from app.services.csv_import_service import csv_import_service
from app.models.database import AsyncSessionLocal
from app.managers import DataManager
from app.logger import logger
from app.cli.command_registry import DATA_COMMANDS
from app.managers.data_manager.repositories.holiday_repo import HolidayRepository
from app.config import settings


console = Console()

# Background task registry to prevent garbage collection
_background_tasks: set = set()


def get_data_manager() -> DataManager:
    """Get DataManager instance via SystemManager.
    
    The SystemManager ensures all managers are singletons and can
    communicate with each other.
    """
    from app.managers.system_manager import get_system_manager
    system_mgr = get_system_manager()
    return system_mgr.get_data_manager()


def register_background_task(task: asyncio.Task) -> None:
    """Register a background task to prevent garbage collection.
    
    Also adds a callback to remove the task when it completes.
    """
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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
    from zoneinfo import ZoneInfo
    
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Interpret as Eastern Time (handles EST/EDT automatically)
    dt_et = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=ZoneInfo("America/New_York"))
    return dt_et


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
    from zoneinfo import ZoneInfo
    
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Interpret as Eastern Time (handles EST/EDT automatically)
    dt_et = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=ZoneInfo("America/New_York"))
    return dt_et


def print_data_usage(_console: Console) -> None:
    """Print data command usage lines to the given console.

    Single source of truth comes from DATA_COMMANDS in command_registry.
    """
    _console.print("[red]Usage:[/red]")
    for meta in DATA_COMMANDS:
        _console.print(f"  {meta.usage} - {meta.description}")


async def import_csv_command(
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
        async with AsyncSessionLocal() as session:
            # Route through DataManager API so all imports share the same path
            dm = get_data_manager()
            result = await dm.import_csv(
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
                quality_color = "green" if quality_pct >= 95 else "yellow" if quality_pct >= 80 else "red"
                console.print(f"  Quality: [{quality_color}]{quality_pct:.1f}%[/{quality_color}]")
            
            if result.get('missing_bars', 0) > 0:
                console.print(f"  [yellow]⚠ Missing bars: {result['missing_bars']}[/yellow]")
        else:
            console.print(f"[red]✗ Import failed: {result.get('message')}[/red]")
    
    except Exception as e:
        console.print(f"[red]✗ Import error: {e}[/red]")
        logger.error(f"CSV import error: {e}")


async def list_symbols_command() -> None:
    """List all symbols in database (1m bars, daily bars, ticks, quotes)"""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()

            # ---- 1m bar data ----
            symbols = await dm.get_symbols(session)
            if not symbols:
                console.print("\n[yellow]No 1m bar data in database yet. Import CSV or use data import-api 1m to get started.[/yellow]")
            else:
                table = Table(title="\nMarket Data Symbols (1m bars)", show_header=True, header_style="bold cyan")
                table.add_column("Symbol", style="cyan", width=10)
                table.add_column("Bars", justify="right", style="green")
                table.add_column("Start Date", style="dim")
                table.add_column("End Date", style="dim")

                for symbol in symbols:
                    quality = await dm.check_data_quality(session, symbol)
                    total_bars = quality.get("total_bars", 0)
                    start_date, end_date = await dm.get_date_range(session, symbol)

                    table.add_row(
                        symbol,
                        f"{total_bars:,}",
                        start_date.strftime("%Y-%m-%d %H:%M") if start_date else "N/A",
                        end_date.strftime("%Y-%m-%d %H:%M") if end_date else "N/A",
                    )

                console.print(table)
                console.print(f"\n[dim]Total bar symbols: {len(symbols)}[/dim]\n")

            # ---- 1d (daily) bar data ----
            daily_symbols = await dm.get_symbols(session, interval="1d")
            if daily_symbols:
                daily_table = Table(title="Daily Bar Data (1d)", show_header=True, header_style="bold cyan")
                daily_table.add_column("Symbol", style="cyan", width=10)
                daily_table.add_column("Bars", justify="right", style="green")
                daily_table.add_column("Start Date", style="dim")
                daily_table.add_column("End Date", style="dim")

                for symbol in daily_symbols:
                    total_bars = await dm.get_bar_count(session, symbol, interval="1d")
                    start_date, end_date = await dm.get_date_range(session, symbol, interval="1d")

                    daily_table.add_row(
                        symbol,
                        f"{total_bars:,}",
                        start_date.strftime("%Y-%m-%d") if start_date else "N/A",
                        end_date.strftime("%Y-%m-%d") if end_date else "N/A",
                    )

                console.print(daily_table)
                console.print(f"\n[dim]Total daily bar symbols: {len(daily_symbols)}[/dim]\n")

            # ---- Tick data (interval='tick') ----
            tick_symbols = await dm.get_symbols(session, interval="tick")
            if tick_symbols:
                tick_table = Table(title="Tick Data Symbols", show_header=True, header_style="bold cyan")
                tick_table.add_column("Symbol", style="cyan", width=10)
                tick_table.add_column("Ticks", justify="right", style="green")
                tick_table.add_column("Start Tick", style="dim")
                tick_table.add_column("End Tick", style="dim")

                for symbol in tick_symbols:
                    total_ticks = await dm.get_bar_count(session, symbol, interval="tick")
                    start_tick, end_tick = await dm.get_date_range(session, symbol, interval="tick")

                    tick_table.add_row(
                        symbol,
                        f"{total_ticks:,}",
                        start_tick.strftime("%Y-%m-%d %H:%M:%S") if start_tick else "N/A",
                        end_tick.strftime("%Y-%m-%d %H:%M:%S") if end_tick else "N/A",
                    )

                console.print(tick_table)
                console.print(f"\n[dim]Total tick symbols: {len(tick_symbols)}[/dim]\n")
            
            # ---- Quote data (bid/ask) ----
            from app.managers.data_manager.repositories.quote_repo import QuoteRepository

            quote_symbols = await QuoteRepository.get_symbols(session)
            if quote_symbols:
                quote_table = Table(title="Quote Data Symbols", show_header=True, header_style="bold cyan")
                quote_table.add_column("Symbol", style="cyan", width=10)
                quote_table.add_column("Quotes", justify="right", style="green")
                quote_table.add_column("First Quote", style="dim")
                quote_table.add_column("Last Quote", style="dim")

                for symbol in quote_symbols:
                    from app.managers.data_manager.repositories.quote_repo import QuoteRepository as QR
                    total_quotes = await QR.get_quote_count(session, symbol)
                    start_q, end_q = await QR.get_date_range(session, symbol)

                    quote_table.add_row(
                        symbol,
                        f"{total_quotes:,}",
                        start_q.strftime("%Y-%m-%d %H:%M:%S") if start_q else "N/A",
                        end_q.strftime("%Y-%m-%d %H:%M:%S") if end_q else "N/A",
                    )

                console.print(quote_table)
                console.print(f"\n[dim]Total quote symbols: {len(quote_symbols)}[/dim]\n")
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"List symbols error: {e}")


async def data_info_command(symbol: str) -> None:
    """
    Show data info for a symbol
    
    Args:
        symbol: Stock symbol
    """
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            quality = await dm.check_data_quality(session, symbol.upper())
            
            if quality['total_bars'] == 0:
                console.print(f"\n[yellow]No data found for {symbol.upper()}[/yellow]")
                return
            
            start_date, end_date = await dm.get_date_range(session, symbol.upper())
            
            console.print(f"\n[cyan]Data Info: {symbol.upper()}[/cyan]")
            console.print(f"  Total bars: {quality['total_bars']:,}")
            console.print(f"  Start: {start_date.strftime('%Y-%m-%d %H:%M')}" if start_date else "  Start: N/A")
            console.print(f"  End: {end_date.strftime('%Y-%m-%d %H:%M')}" if end_date else "  End: N/A")
            
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


async def data_quality_command(symbol: str) -> None:
    """
    Check data quality for a symbol
    
    Args:
        symbol: Stock symbol
    """
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            quality = await dm.check_data_quality(session, symbol.upper())
            
            if quality['total_bars'] == 0:
                console.print(f"\n[yellow]No data found for {symbol.upper()}[/yellow]")
                return
            
            # Create table
            table = Table(title=f"\nData Quality: {symbol.upper()}", show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right", style="white")
            
            table.add_row("Total bars", f"{quality['total_bars']:,}")
            table.add_row("Expected bars", f"{quality['expected_bars']:,}")
            table.add_row("Missing bars", f"{quality['missing_bars']:,}")
            # Only show duplicate timestamps if there are any
            if quality['duplicate_timestamps'] > 0:
                table.add_row("Duplicate timestamps", f"{quality['duplicate_timestamps']}")
            
            quality_pct = quality['quality_score'] * 100
            quality_color = "green" if quality_pct >= 95 else "yellow" if quality_pct >= 80 else "red"
            table.add_row("Quality score", f"[{quality_color}]{quality_pct:.1f}%[/{quality_color}]")
            
            if quality.get('date_range'):
                table.add_row("Start date", quality['date_range']['start'])
                table.add_row("End date", quality['date_range']['end'])
            
            console.print(table)
            
            # Quality assessment
            if quality_pct >= 95:
                console.print("\n[green]✓ Excellent data quality[/green]")
            elif quality_pct >= 80:
                console.print("\n[yellow]⚠ Good data quality with some gaps[/yellow]")
            else:
                console.print("\n[red]✗ Poor data quality - consider re-importing[/red]")
            
            console.print()
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Data quality error: {e}")


async def select_data_api_command(api: str) -> None:
    """Select data API provider via DataManager (e.g., alpaca, schwab)."""
    dm = get_data_manager()
    ok = await dm.select_data_api(api)
    if ok:
        console.print(f"[green]✓[/green] Data API provider set to [cyan]{dm.data_api}[/cyan] and connected")
    else:
        console.print(f"[red]✗[/red] Failed to connect data API provider [cyan]{api}[/cyan]")


async def import_from_api_command(
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
        f"[dim]  From: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
    )
    console.print(
        f"[dim]  To:   {end_dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
    )

    dm = get_data_manager()

    try:
        async with AsyncSessionLocal() as session:
            result = await dm.import_from_api(
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


async def delete_symbol_command(symbol: str) -> None:
    """Delete all market data for a symbol."""
    if not Confirm.ask(
        f"\n[yellow]⚠ Delete ALL data for {symbol.upper()}? This cannot be undone![/yellow]"
    ):
        console.print("[dim]Cancelled[/dim]")
        return

    try:
        async with AsyncSessionLocal() as session:
            manager = get_data_manager()
            deleted = await manager.delete_symbol_data(session, symbol.upper())

        if deleted > 0:
            console.print(
                f"\n[green]✓ Deleted {deleted:,} bars for {symbol.upper()}[/green]\n"
            )
        else:
            console.print(f"\n[yellow]No data found for {symbol.upper()}[/yellow]\n")

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Delete symbol error: {e}")


async def delete_all_command() -> None:
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
        async with AsyncSessionLocal() as session:
            manager = get_data_manager()
            deleted = await manager.delete_all_data(session)

        console.print(
            f"\n[green]✓ Deleted ALL market data: {deleted:,} bars[/green]"
        )
        console.print("[dim]Database is now empty[/dim]\n")

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Delete all error: {e}")


async def export_csv_command(
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
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            if is_quote:
                quotes = await dm.get_quotes(session, symbol_u, start_dt, end_dt)
                records = quotes
            else:
                bars = await dm.get_bars(session, symbol_u, start_dt, end_dt, interval=interval)
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


async def on_demand_bars_command(
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

    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        bars = await dm.get_bars(session, symbol.upper(), start_dt, end_dt, interval=interval)

    if not bars:
        console.print(f"[yellow]No bar data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand bars: {symbol.upper()} ({interval})", box=box.ROUNDED)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")

    max_rows = 200
    for bar in bars[:max_rows]:
        ts = bar.timestamp.strftime("%Y-%m-%d %H:%M")
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


async def on_demand_ticks_command(
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

    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        ticks = await dm.get_ticks(session, symbol.upper(), start_dt, end_dt)

    if not ticks:
        console.print(f"[yellow]No tick data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand ticks: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Size", justify="right")

    max_rows = 200
    for t in ticks[:max_rows]:
        ts = t.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(ts, f"{t.price:.4f}", f"{t.size:.0f}")

    console.print(table)
    if len(ticks) > max_rows:
        console.print(
            f"[dim]Showing first {max_rows} of {len(ticks):,} ticks. Use export-csv for full export.[/dim]"
        )


async def on_demand_quotes_command(
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

    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        quotes = await dm.get_quotes(session, symbol.upper(), start_dt, end_dt)

    if not quotes:
        console.print(f"[yellow]No quote data found for {symbol.upper()} in given range[/yellow]")
        return

    table = Table(title=f"On-demand quotes: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("BidSize", justify="right")
    table.add_column("AskSize", justify="right")

    max_rows = 200
    for q in quotes[:max_rows]:
        ts = q.timestamp.strftime("%Y-%m-%d %H:%M:%S")
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


async def _consume_stream_to_file(
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
            async for item in stream_iterator:
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


async def stream_bars_command(
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
        async with AsyncSessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                await dm.init_backtest(init_session)
        
        # **BLOCKING DB FETCH** - Get all bars before proceeding
        async with AsyncSessionLocal() as fetch_session:
            from app.repositories.market_data_repository import MarketDataRepository
            from datetime import time
            from app.models.trading_calendar import TradingHours
            
            now = dm.get_current_time()
            
            # Determine end time
            if dm.backtest_end_date is None:
                end_date = now
            else:
                close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
                end_date = datetime.combine(dm.backtest_end_date, close_et)
            
            # FETCH ALL BARS FROM DB (this blocks until complete)
            bars = await MarketDataRepository.get_bars_by_symbol(
                fetch_session,
                symbol=symbol.upper(),
                start_date=now,
                end_date=end_date,
                interval=interval,
            )
            
            bar_count = len(bars)
            console.print(f"[green]✓[/green] Fetched {bar_count:,} bars from database")
        
        # Register stream and feed pre-fetched data directly (fast!)
        from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        
        coordinator = get_coordinator()
        coordinator.start_worker()  # Start worker thread if not running
        
        # Register stream
        success, input_queue = coordinator.register_stream(symbol.upper(), StreamType.BAR)
        if not success:
            console.print(f"[red]✗ Stream already active for {symbol.upper()}[/red]")
            return
        
        # Feed all data directly to queue (no async, instant!)
        coordinator.feed_data_list(symbol.upper(), StreamType.BAR, bars)
        
        # Get merged stream from coordinator
        stream_iterator = coordinator.get_merged_stream()
        
        # Start file writer in background if requested
        if file_path:
            async def consume_and_close():
                try:
                    await _consume_stream_to_file(stream_iterator, file_path, "bar")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create task and register it to prevent garbage collection
            task = asyncio.create_task(consume_and_close())
            register_background_task(task)
            
            # Yield control to let the task start
            await asyncio.sleep(0)
            
            console.print(f"[green]✓[/green] Bar stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Bar stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-bars' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting bar stream: {e}[/red]")
        logger.error(f"Bar stream startup error: {e}")


async def stream_ticks_command(
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
        async with AsyncSessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                await dm.init_backtest(init_session)
        
        # **BLOCKING DB FETCH** - Get all ticks before proceeding
        async with AsyncSessionLocal() as fetch_session:
            from app.repositories.market_data_repository import MarketDataRepository
            from datetime import time
            from app.models.trading_calendar import TradingHours
            
            now = dm.get_current_time()
            
            # Determine end time
            if dm.backtest_end_date is None:
                end_date = now
            else:
                close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
                end_date = datetime.combine(dm.backtest_end_date, close_et)
            
            # FETCH ALL TICKS FROM DB (this blocks until complete)
            ticks = await MarketDataRepository.get_ticks_by_symbol(
                fetch_session,
                symbol=symbol.upper(),
                start_date=now,
                end_date=end_date,
            )
            
            tick_count = len(ticks)
            console.print(f"[green]✓[/green] Fetched {tick_count:,} ticks from database")
        
        # Register stream and feed pre-fetched data directly (fast!)
        from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        
        coordinator = get_coordinator()
        coordinator.start_worker()  # Start worker thread if not running
        
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
            async def consume_and_close():
                try:
                    await _consume_stream_to_file(stream_iterator, file_path, "tick")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create task and register it to prevent garbage collection
            task = asyncio.create_task(consume_and_close())
            register_background_task(task)
            
            # Yield control to let the task start
            await asyncio.sleep(0)
            
            console.print(f"[green]✓[/green] Tick stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Tick stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-ticks' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting tick stream: {e}[/red]")
        logger.error(f"Tick stream startup error: {e}")


async def stream_quotes_command(
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
        async with AsyncSessionLocal() as init_session:
            if dm.system_manager.mode.value == "backtest" and dm.backtest_start_date is None:
                await dm.init_backtest(init_session)
        
        # **BLOCKING DB FETCH** - Get all quotes before proceeding
        async with AsyncSessionLocal() as fetch_session:
            from app.repositories.market_data_repository import MarketDataRepository
            from datetime import time
            from app.models.trading_calendar import TradingHours
            
            now = dm.get_current_time()
            
            # Determine end time
            if dm.backtest_end_date is None:
                end_date = now
            else:
                close_et = time.fromisoformat(TradingHours.MARKET_CLOSE)
                end_date = datetime.combine(dm.backtest_end_date, close_et)
            
            # FETCH ALL QUOTES FROM DB (this blocks until complete)
            quotes = await MarketDataRepository.get_quotes_by_symbol(
                fetch_session,
                symbol=symbol.upper(),
                start_date=now,
                end_date=end_date,
            )
            
            quote_count = len(quotes)
            console.print(f"[green]✓[/green] Fetched {quote_count:,} quotes from database")
        
        # Register stream and feed pre-fetched data directly (fast!)
        from app.managers.data_manager.backtest_stream_coordinator import get_coordinator, StreamType
        
        coordinator = get_coordinator()
        coordinator.start_worker()  # Start worker thread if not running
        
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
            async def consume_and_close():
                try:
                    await _consume_stream_to_file(stream_iterator, file_path, "quote")
                except Exception as e:
                    logger.error(f"Error in file writer: {e}")
            
            # Create task and register it to prevent garbage collection
            task = asyncio.create_task(consume_and_close())
            register_background_task(task)
            
            # Yield control to let the task start
            await asyncio.sleep(0)
            
            console.print(f"[green]✓[/green] Quote stream started with stream id [yellow]{stream_id}[/yellow]")
            console.print(f"[dim]Writing to {file_path}[/dim]")
        else:
            console.print(f"[green]✓[/green] Quote stream started with stream id [yellow]{stream_id}[/yellow]")
        
        console.print("[dim]Use 'data stop-stream-quotes' to stop the stream[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗ Error starting quote stream: {e}[/red]")
        logger.error(f"Quote stream startup error: {e}")


async def latest_bar_command(symbol: str, interval: str = "1m") -> None:
    """Show the latest bar for a symbol from the local DB."""
    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        bar = await dm.get_latest_bar(session, symbol.upper(), interval=interval)

    if not bar:
        console.print(f"[yellow]No bar data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest bar: {symbol.upper()} ({interval})", box=box.ROUNDED)
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

    console.print(table)


async def latest_tick_command(symbol: str) -> None:
    """Show the latest tick for a symbol from the local DB."""
    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        tick = await dm.get_latest_tick(session, symbol.upper())

    if not tick:
        console.print(f"[yellow]No tick data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest tick: {symbol.upper()}", box=box.ROUNDED)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Size", justify="right")

    ts = tick.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    table.add_row(ts, f"{tick.price:.4f}", f"{tick.size:.0f}")

    console.print(table)


async def latest_quote_command(symbol: str) -> None:
    """Show the latest bid/ask quote for a symbol from the local DB."""
    async with AsyncSessionLocal() as session:
        dm = get_data_manager()
        quote = await dm.get_latest_quote(session, symbol.upper())

    if not quote:
        console.print(f"[yellow]No quote data found for {symbol.upper()}[/yellow]")
        return

    table = Table(title=f"Latest quote: {symbol.upper()}", box=box.ROUNDED)
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

    console.print(table)


async def set_backtest_speed_command(speed: str) -> None:
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
        await dm.set_backtest_speed(speed_value)

        console.print("[green]✓[/green] Backtest speed updated:")
        console.print(f"  DATA_MANAGER_BACKTEST_SPEED: {settings.DATA_MANAGER_BACKTEST_SPEED}")
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


async def set_backtest_window_command(
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
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            await dm.set_backtest_window(session, start_dt, end_dt)

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


async def import_holidays_command(file_path: str) -> None:
    """Import market holidays from a CSV file via DataManager."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            result = await dm.import_holidays_from_file(session, file_path)

        if result.get("success"):
            console.print("[green]✓[/green] Holidays imported successfully")
            if "inserted" in result:
                console.print(f"  Inserted/updated: {result['inserted']} entries")
        else:
            console.print(f"[yellow]![/yellow] {result.get('message', 'Import completed with no data')}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error importing holidays: {e}[/red]")
        logger.error(f"Import holidays error: {e}")


async def list_holidays_command(year: int | None = None) -> None:
    """List market holidays for a year (or all if year is None)."""
    try:
        async with AsyncSessionLocal() as session:
            if year is None:
                # List all holidays in a broad range
                start = date(2000, 1, 1)
                end = date(2100, 12, 31)
            else:
                start = date(year, 1, 1)
                end = date(year, 12, 31)

            holidays = await HolidayRepository.get_holidays_in_range(session, start, end)

        if not holidays:
            console.print("[yellow]No holidays found[/yellow]")
            return

        table = Table(title="Market Holidays", show_header=True, header_style="bold cyan")
        table.add_column("Date", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Closed", style="green")
        table.add_column("Early Close", style="yellow")

        for h in holidays:
            table.add_row(
                h.date.isoformat(),
                h.holiday_name or "",
                "YES" if h.is_closed else "NO",
                h.early_close_time.isoformat() if h.early_close_time else "",
            )

        console.print(table)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error listing holidays: {e}[/red]")
        logger.error(f"List holidays error: {e}")


async def delete_holidays_command(year: int) -> None:
    """Delete holidays for a specific year via DataManager."""
    if not Confirm.ask(f"[yellow]Delete all holidays for {year}?[/yellow]"):
        console.print("[dim]Cancelled[/dim]")
        return

    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            deleted = await dm.delete_holidays_for_year(session, year)

        console.print(f"[green]✓[/green] Deleted {deleted} holidays for year {year}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error deleting holidays: {e}[/red]")
        logger.error(f"Delete holidays error: {e}")


async def stop_bars_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active bar stream via DataManager.stop_bars_stream."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            # session not needed for stop, but kept for symmetry and future use
            _ = session
            await dm.stop_bars_stream(stream_id)
        console.print("[green]✓[/green] Bar stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping bar stream: {e}[/red]")
        logger.error(f"Stop bar stream error: {e}")


async def stop_ticks_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active tick stream via DataManager.stop_ticks_stream."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            _ = session
            await dm.stop_ticks_stream(stream_id)
        console.print("[green]✓[/green] Tick stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping tick stream: {e}[/red]")
        logger.error(f"Stop tick stream error: {e}")


async def stop_quotes_stream_command(stream_id: Optional[str] = None) -> None:
    """Stop an active quote stream via DataManager.stop_quotes_stream."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            _ = session
            await dm.stop_quotes_stream(stream_id)
        console.print("[green]✓[/green] Quote stream stop signal sent")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping quote stream: {e}[/red]")
        logger.error(f"Stop quote stream error: {e}")


async def stop_all_streams_command() -> None:
    """Stop ALL active data streams and coordinator worker via DataManager.stop_all_streams."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            _ = session
            await dm.stop_all_streams()
        console.print("[green]✓[/green] All streams stopped (bars, ticks, quotes, coordinator)")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error stopping all streams: {e}[/red]")
        logger.error(f"Stop all streams error: {e}")


async def snapshot_command(symbol: str) -> None:
    """Get latest snapshot from data provider (live mode only)."""
    try:
        dm = get_data_manager()
        snapshot = await dm.get_snapshot(symbol)
        
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


async def session_volume_command(symbol: str) -> None:
    """Get cumulative volume for current trading session."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            volume = await dm.get_current_session_volume(session, symbol)
            
            console.print(f"\n[bold cyan]{symbol} Session Volume[/bold cyan]")
            console.print(f"Cumulative Volume: [green]{volume:,}[/green] shares\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error fetching session volume: {e}[/red]")
        logger.error(f"Session volume command error: {e}")


async def session_high_low_command(symbol: str) -> None:
    """Get session high and low prices."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            high, low = await dm.get_current_session_high_low(session, symbol)
            
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


async def avg_volume_command(symbol: str, days: int) -> None:
    """Get average daily volume over specified trading days."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            avg_vol = await dm.get_average_volume(session, symbol, days)
            
            console.print(f"\n[bold cyan]{symbol} Average Volume ({days} days)[/bold cyan]")
            console.print(f"Average Daily Volume: [green]{avg_vol:,.0f}[/green] shares\n")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error calculating average volume: {e}[/red]")
        logger.error(f"Average volume command error: {e}")


async def high_low_command(symbol: str, days: int) -> None:
    """Get historical high/low prices over specified period."""
    try:
        async with AsyncSessionLocal() as session:
            dm = get_data_manager()
            high, low = await dm.get_historical_high_low(session, symbol, days)
            
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
def data_list() -> None:
    """List all symbols in database (1m bars, daily bars, ticks, quotes)."""
    asyncio.run(list_symbols_command())


@app.command("info")
def data_info(symbol: str = typer.Argument(..., help="Stock symbol")) -> None:
    """Show data info for a symbol."""
    asyncio.run(data_info_command(symbol))


@app.command("quality")
def data_quality(symbol: str = typer.Argument(..., help="Stock symbol")) -> None:
    """Check data quality for a symbol."""
    asyncio.run(data_quality_command(symbol))


@app.command("delete")
def data_delete(symbol: str = typer.Argument(..., help="Stock symbol")) -> None:
    """Delete all data for a symbol (⚠)."""
    asyncio.run(delete_symbol_command(symbol))


@app.command("delete-all")
def data_delete_all() -> None:
    """Delete ALL data (⚠)."""
    asyncio.run(delete_all_command())


@app.command("backtest-speed")
def backtest_speed(
    speed: str = typer.Argument(..., help="Backtest speed multiplier: 0=max, 1.0=realtime, 2.0=2x speed, 0.5=half speed"),
) -> None:
    """Set backtest execution speed multiplier."""
    asyncio.run(set_backtest_speed_command(speed))


@app.command("backtest-window")
def backtest_window(
    start_date: str = typer.Argument(..., help="Backtest start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Argument(
        None,
        help="Optional backtest end date (YYYY-MM-DD)",
    ),
) -> None:
    """Set DataManager backtest window dates."""
    asyncio.run(set_backtest_window_command(start_date, end_date))


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
    asyncio.run(export_csv_command(data_type, symbol, start_date, end_date, file_path))


@app.command("bars")
def on_demand_bars(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
    interval: str = typer.Option("1m", "--interval", help="Bar interval (e.g., 1m, tick)"),
) -> None:
    """Fetch and display bars from the local DB (no API calls)."""
    asyncio.run(on_demand_bars_command(symbol, start_date, end_date, interval))


@app.command("ticks")
def on_demand_ticks(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Fetch and display ticks from the local DB (no API calls)."""
    asyncio.run(on_demand_ticks_command(symbol, start_date, end_date))


@app.command("quotes")
def on_demand_quotes(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Fetch and display quotes from the local DB (no API calls)."""
    asyncio.run(on_demand_quotes_command(symbol, start_date, end_date))


@app.command("latest-bar")
def latest_bar(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    interval: str = typer.Option("1m", "--interval", help="Bar interval (e.g., 1m, tick)"),
) -> None:
    """Show the latest bar for a symbol."""
    asyncio.run(latest_bar_command(symbol, interval))


@app.command("latest-tick")
def latest_tick(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Show the latest tick for a symbol."""
    asyncio.run(latest_tick_command(symbol))


@app.command("latest-quote")
def latest_quote(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Show the latest bid/ask quote for a symbol."""
    asyncio.run(latest_quote_command(symbol))


@app.command("session")
def session(
    refresh_seconds: Optional[int] = typer.Argument(None, help="Auto-refresh interval in seconds (default: 1s, use 0 to display once)"),
    csv_file: Optional[str] = typer.Argument(None, help="CSV file path to export data (default: validation/test_session.csv, always overwrites)"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Duration to run in seconds (default: run indefinitely)"),
    no_live: bool = typer.Option(False, "--no-live", help="Disable live updating, print each refresh (better for scripts)"),
) -> None:
    """Display live session data with auto-refresh and CSV export (default: 1s, exports to validation/test_session.csv)."""
    from app.cli.session_data_display import data_session_command
    asyncio.run(data_session_command(refresh_seconds, csv_file, duration, no_live))


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
    asyncio.run(stream_bars_command(symbol, interval, file_path))


@app.command("stream-ticks")
def stream_ticks(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    file_path: Optional[str] = typer.Argument(None, help="Optional output CSV file"),
) -> None:
    """Start streaming ticks to console or CSV file."""
    asyncio.run(stream_ticks_command(symbol, file_path))


@app.command("stream-quotes")
def stream_quotes(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    file_path: Optional[str] = typer.Argument(None, help="Optional output CSV file"),
) -> None:
    """Start streaming quotes to console or CSV file."""
    asyncio.run(stream_quotes_command(symbol, file_path))


@app.command("stop-stream-bars")
def stop_stream_bars(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active bar stream(s) to stop."""
    asyncio.run(stop_bars_stream_command(stream_id))


@app.command("stop-stream-ticks")
def stop_stream_ticks(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active tick stream(s) to stop."""
    asyncio.run(stop_ticks_stream_command(stream_id))


@app.command("stop-stream-quotes")
def stop_stream_quotes(
    stream_id: Optional[str] = typer.Argument(None, help="Optional stream id; omit to stop all"),
) -> None:
    """Signal active quote stream(s) to stop."""
    asyncio.run(stop_quotes_stream_command(stream_id))


@app.command("stop-all-streams")
def stop_all_streams() -> None:
    """Stop ALL active data streams (bars, ticks, quotes) and coordinator worker."""
    asyncio.run(stop_all_streams_command())


@app.command("snapshot")
def snapshot(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get latest snapshot from data provider (live mode only)."""
    asyncio.run(snapshot_command(symbol))


@app.command("session-volume")
def session_volume(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get cumulative volume for current trading session."""
    asyncio.run(session_volume_command(symbol))


@app.command("session-high-low")
def session_high_low(
    symbol: str = typer.Argument(..., help="Stock symbol"),
) -> None:
    """Get session high and low prices."""
    asyncio.run(session_high_low_command(symbol))


@app.command("avg-volume")
def avg_volume(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    days: int = typer.Argument(..., help="Number of trading days"),
) -> None:
    """Get average daily volume over specified trading days."""
    asyncio.run(avg_volume_command(symbol, days))


@app.command("high-low")
def high_low(
    symbol: str = typer.Argument(..., help="Stock symbol"),
    days: int = typer.Argument(..., help="Number of days lookback"),
) -> None:
    """Get historical high/low prices over specified period."""
    asyncio.run(high_low_command(symbol, days))


@app.command("api")
def set_api(
    api: str = typer.Argument(
        ..., help="Data API provider (e.g., alpaca, schwab)"
    ),
) -> None:
    """Select data API provider via DataManager and auto-connect."""
    asyncio.run(select_data_api_command(api))


@app.command("import-api")
def import_api(
    data_type: str = typer.Argument(..., help="Data type (e.g., 1m, tick)"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
) -> None:
    """Import data from external API via DataManager.import_from_api."""
    asyncio.run(import_from_api_command(data_type, symbol, start_date, end_date))


@app.command("import-file")
def import_file(
    file_path: str = typer.Argument(..., help="Path to CSV file"),
    symbol: str = typer.Argument(..., help="Stock symbol"),
    start_date: str = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
) -> None:
    """Import CSV data via DataManager (data import-file)."""
    asyncio.run(import_csv_command(file_path, symbol, start_date, end_date))
