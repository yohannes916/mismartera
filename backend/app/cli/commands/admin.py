"""
CLI commands for admin operations
"""
import typer
from rich.console import Console
from rich.table import Table
from rich import box
import httpx
from app.config import settings
from app.logger import logger, logger_manager

app = typer.Typer()
console = Console()


@app.command("log-level")
def set_log_level(
    level: str = typer.Argument(..., help="Log level (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)")
):
    """
    Change application log level at runtime
    """
    try:
        new_level = logger_manager.set_level(level)
        console.print(f"[green]✓[/green] Log level changed to: [cyan]{new_level}[/cyan]")
        logger.success(f"Log level changed to {new_level} via CLI")
    except ValueError as e:
        console.print(f"[red]✗[/red] Error: {e}")
        logger.error(f"Invalid log level: {level}")
        raise typer.Exit(code=1)


@app.command("log-level-get")
def get_log_level():
    """
    Get current log level
    """
    current = logger_manager.get_level()
    available = logger_manager.get_available_levels()
    
    table = Table(title="Log Level Configuration", box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Current Level", current)
    table.add_row("Available Levels", ", ".join(available))
    
    console.print(table)


@app.command("api-status")
def api_status():
    """
    Check if API server is running
    """
    url = f"http://{settings.API.host}:{settings.API.port}/health"
    
    try:
        with console.status("[yellow]Checking API server...[/yellow]"):
            response = httpx.get(url, timeout=5.0)
            
        if response.status_code == 200:
            data = response.json()
            console.print(f"[green]✓[/green] API server is running")
            console.print(f"[dim]Status: {data.get('status')}[/dim]")
            console.print(f"[dim]Version: {data.get('version')}[/dim]")
        else:
            console.print(f"[yellow]⚠[/yellow] API server responded with status {response.status_code}")
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] API server is not running at {url}")
        console.print(f"[dim]Start it with: mismartera server[/dim]")
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
