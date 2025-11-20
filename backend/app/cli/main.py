"""
MisMartera Trading Backend - CLI Application
"""
import typer
from rich.console import Console
from rich.panel import Panel
from rich import box
from app.config import settings
from app.logger import logger

# Create Typer app
app = typer.Typer(
    name="mismartera",
    help="Mismartera Trading CLI",
    add_completion=False,
)

# Rich console for beautiful output
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit")
):
    """
    MisMartera Trading Backend CLI
    
    A day trading application with Charles Schwab API integration and Claude AI analysis.
    """
    if version:
        console.print(f"[cyan]{settings.APP_NAME}[/cyan] v{settings.APP_VERSION}")
        raise typer.Exit()
    
    if ctx.invoked_subcommand is None:
        # Show welcome message when no command is provided
        console.print(Panel.fit(
            f"[bold cyan]{settings.APP_NAME}[/bold cyan]\n"
            f"[dim]Version {settings.APP_VERSION}[/dim]\n\n"
            f"[yellow]Use --help to see available commands[/yellow]",
            box=box.ROUNDED,
            border_style="cyan"
        ))


@app.command()
def server(
    host: str = typer.Option(settings.API_HOST, "--host", "-h", help="Server host"),
    port: int = typer.Option(settings.API_PORT, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(settings.DEBUG, "--reload", "-r", help="Enable auto-reload")
):
    """
    Start the FastAPI server
    """
    import uvicorn
    
    console.print(f"[green]Starting server at http://{host}:{port}[/green]")
    console.print(f"[dim]API docs: http://{host}:{port}/docs[/dim]")
    console.print(f"[dim]ReDoc: http://{host}:{port}/redoc[/dim]\n")
    
    logger.info(f"Starting server via CLI at {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.LOG_LEVEL.lower()
    )


@app.command()
def init_db():
    """
    Initialize the database (create tables)
    """
    import asyncio
    from app.models import init_db as initialize_database
    
    console.print("[yellow]Initializing database...[/yellow]")
    logger.info("Initializing database via CLI")
    
    try:
        asyncio.run(initialize_database())
        console.print("[green]✓[/green] Database initialized successfully")
        logger.success("Database initialized via CLI")
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
        logger.error(f"Database initialization failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def status():
    """
    Show application status
    """
    from rich.table import Table
    
    table = Table(title="System Status", box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Application", settings.APP_NAME)
    table.add_row("Version", settings.APP_VERSION)
    table.add_row("Debug Mode", str(settings.DEBUG))
    table.add_row("Paper Trading", str(settings.PAPER_TRADING))
    table.add_row("Log Level", settings.LOG_LEVEL)
    table.add_row("Database", settings.DATABASE_URL.split("///")[-1] if ":///" in settings.DATABASE_URL else settings.DATABASE_URL)
    table.add_row("API Host", f"{settings.API_HOST}:{settings.API_PORT}")
    
    console.print(table)
    logger.debug("Status command executed")


# Import and add command groups
# These will be implemented next
try:
    from app.cli.commands import admin, account, execution, analysis, alpaca
    from app.cli import data_commands
    
    app.add_typer(admin.app, name="admin", help="Admin commands")
    app.add_typer(account.app, name="account", help="Account management")
    app.add_typer(execution.app, name="execution", help="Order execution")
    app.add_typer(data_commands.app, name="data", help="Market data")
    app.add_typer(analysis.app, name="analysis", help="AI analysis")
    app.add_typer(alpaca.app, name="alpaca", help="Alpaca integration")
except ImportError:
    # Commands not yet implemented
    pass


if __name__ == "__main__":
    app()
