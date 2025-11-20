"""
CLI commands for holiday calendar management
"""
from pathlib import Path
from rich.table import Table
from rich.console import Console
from datetime import datetime

from app.managers import DataManager
from app.models.database import AsyncSessionLocal
from app.logger import logger


console = Console()


async def import_holidays_command(file_path: str, year: str = None) -> None:
    """
    Import holiday schedule from CSV file
    
    Args:
        file_path: Path to holiday CSV file
        year: Optional year for display
    """
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]✗ File not found: {file_path}[/red]")
        return
    
    if not path.suffix.lower() == '.csv':
        console.print(f"[red]✗ File must be a CSV file[/red]")
        return
    
    console.print(f"\n[cyan]Importing holidays from {path.name}...[/cyan]")
    
    try:
        async with AsyncSessionLocal() as session:
            manager = DataManager()
            result = await manager.import_holidays_from_file(
                session=session,
                file_path=str(path.absolute()),
            )
        
        if result['success']:
            console.print(f"\n[green]✓ Import successful![/green]")
            console.print(f"  Total rows: {result['total_rows']}")
            console.print(f"  Imported: {result['imported']}")
            if result.get('year'):
                console.print(f"  Year: {result['year']}")
            console.print()
        else:
            console.print(f"[red]✗ Import failed: {result.get('message')}[/red]")
    
    except Exception as e:
        console.print(f"[red]✗ Import error: {e}[/red]")
        logger.error(f"Holiday import error: {e}")


async def list_holidays_command(year: int = None) -> None:
    """
    List all holidays in database
    
    Args:
        year: Optional year filter (if None, shows all years)
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get holidays for the year or all holidays via DataManager
            if year:
                start_date = datetime(year, 1, 1).date()
                end_date = datetime(year, 12, 31).date()
                title = f"\nMarket Holidays {year}"
            else:
                # Show all holidays from 1900 to 2100
                start_date = datetime(1900, 1, 1).date()
                end_date = datetime(2100, 12, 31).date()
                title = "\nMarket Holidays (All Years)"

            manager = DataManager()
            holidays = await manager.get_holidays(
                session=session,
                start_date=start_date,
                end_date=end_date,
            )
            
            if not holidays:
                console.print(f"\n[yellow]No holidays found[/yellow]")
                console.print("[dim]Import a holiday schedule with: holidays import <file>[/dim]\n")
                return
            
            # Group holidays by year if showing all
            if not year:
                years = sorted(set(h.date.year for h in holidays))
                console.print(f"\n[cyan]Found holidays for years: {', '.join(map(str, years))}[/cyan]")
            
            # Create table
            table = Table(
                title=title,
                show_header=True,
                header_style="bold cyan"
            )
            table.add_column("Date", style="cyan")
            table.add_column("Day", style="dim")
            table.add_column("Holiday", style="yellow")
            table.add_column("Status", justify="center")
            table.add_column("Notes", style="dim")
            
            for holiday in holidays:
                day_name = holiday.date.strftime("%A")
                date_str = holiday.date.strftime("%Y-%m-%d")
                
                if holiday.is_closed:
                    status = "[red]CLOSED[/red]"
                else:
                    close_time = holiday.early_close_time.strftime("%I:%M %p")
                    status = f"[yellow]Early: {close_time}[/yellow]"
                
                table.add_row(
                    date_str,
                    day_name,
                    holiday.holiday_name,
                    status,
                    holiday.notes or ""
                )
            
            console.print(table)
            
            if not year:
                # Show breakdown by year
                years = {}
                for holiday in holidays:
                    y = holiday.date.year
                    years[y] = years.get(y, 0) + 1
                
                console.print(f"\n[dim]Total: {len(holidays)} holidays/early closes[/dim]")
                console.print("[dim]Breakdown by year:[/dim]")
                for y in sorted(years.keys()):
                    console.print(f"  [dim]{y}: {years[y]} holidays[/dim]")
                console.print()
            else:
                console.print(f"\n[dim]Total: {len(holidays)} holidays/early closes[/dim]\n")
    
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        logger.error(f"List holidays error: {e}")


async def delete_holidays_command(year: int) -> None:
    """Delete all holidays for a given year"""
    try:
        if year < 1900 or year > 2100:
            console.print("[red]✗ Invalid year. Please use a year between 1900 and 2100[/red]")
            return

        async with AsyncSessionLocal() as session:
            manager = DataManager(mode="real")
            deleted = await manager.delete_holidays_for_year(session, year)

        if deleted == 0:
            console.print(f"\n[yellow]No holidays found for {year} to delete[/yellow]\n")
        else:
            console.print(f"\n[green]✓ Deleted {deleted} holidays for year {year}[/green]\n")
    except Exception as e:
        console.print(f"[red]✗ Error deleting holidays: {e}[/red]")
        logger.error(f"Delete holidays error: {e}")
