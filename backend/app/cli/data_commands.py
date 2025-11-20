"""
CLI commands for market data management
"""
from pathlib import Path
from typing import Optional
from datetime import datetime
import asyncio

import typer
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

from app.services.csv_import_service import csv_import_service
from app.models.database import AsyncSessionLocal
from app.managers import DataManager
from app.logger import logger


console = Console()


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
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            console.print(f"[yellow]📅 Start date filter: {start_date}[/yellow]")
        except ValueError:
            console.print(f"[red]Invalid start date format. Use YYYY-MM-DD[/red]")
            return
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            console.print(f"[yellow]📅 End date filter: {end_date}[/yellow]")
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
            dm = DataManager()
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
    """List all symbols in database"""
    try:
        async with AsyncSessionLocal() as session:
            dm = DataManager()
            symbols = await dm.get_symbols(session)
            
            if not symbols:
                console.print("\n[yellow]No data in database yet. Import CSV files to get started.[/yellow]")
                return
            
            # Create table
            table = Table(title="\nMarket Data Symbols", show_header=True, header_style="bold cyan")
            table.add_column("Symbol", style="cyan", width=10)
            table.add_column("Bars", justify="right", style="green")
            table.add_column("Start Date", style="dim")
            table.add_column("End Date", style="dim")
            
            for symbol in symbols:
                count = await dm.check_data_quality(session, symbol)
                total_bars = count.get("total_bars", 0)
                start_date, end_date = await dm.get_date_range(session, symbol)
                
                table.add_row(
                    symbol,
                    f"{total_bars:,}",
                    start_date.strftime("%Y-%m-%d %H:%M") if start_date else "N/A",
                    end_date.strftime("%Y-%m-%d %H:%M") if end_date else "N/A"
                )
            
            console.print(table)
            console.print(f"\n[dim]Total symbols: {len(symbols)}[/dim]\n")
    
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
            dm = DataManager()
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
            dm = DataManager()
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


async def set_operating_mode_command(mode: str) -> None:
    """Set DataManager operating mode via API (realtime or backtest)."""
    dm = DataManager()
    await dm.set_operating_mode(mode)
    console.print(f"[green]✓[/green] DataManager operating mode set to [cyan]{dm.mode}[/cyan]")


async def select_data_api_command(api: str) -> None:
    """Select data API provider via DataManager (e.g., alpaca, schwab)."""
    dm = DataManager()
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
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        console.print("[red]Dates must be in YYYY-MM-DD format[/red]")
        return

    console.print(
        f"[yellow]Importing {data_type} data for {symbol.upper()} "
        f"from {start_date} to {end_date} via DataManager API...[/yellow]"
    )

    dm = DataManager()

    try:
        async with AsyncSessionLocal() as session:
            await dm.import_from_api(
                session=session,
                data_type=data_type,
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
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
            manager = DataManager()
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
            manager = DataManager()
            deleted = await manager.delete_all_data(session)

        console.print(
            f"\n[green]✓ Deleted ALL market data: {deleted:,} bars[/green]"
        )
        console.print("[dim]Database is now empty[/dim]\n")

    except Exception as e:  # noqa: BLE001
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"Delete all error: {e}")


app = typer.Typer()


@app.command("list")
def data_list() -> None:
    """List all symbols in database."""
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


@app.command("mode")
def set_mode(
    mode: str = typer.Argument(..., help="Operating mode: realtime or backtest"),
) -> None:
    """Set DataManager operating mode (realtime or backtest)."""
    asyncio.run(set_operating_mode_command(mode))


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
