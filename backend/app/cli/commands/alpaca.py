"""CLI commands for Alpaca integration (connect/disconnect tests)."""
import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich import box

from app.logger import logger
from app.integrations import alpaca_client


app = typer.Typer()
console = Console()


@app.command("connect")
def connect():
    """Test Alpaca API connectivity using current credentials."""
    console.print("[yellow]Testing Alpaca API connection...[/yellow]")
    logger.info("Alpaca connect command executed")

    async def _test() -> bool:
        return await alpaca_client.validate_connection()

    ok = asyncio.run(_test())

    if ok:
        console.print(
            Panel.fit(
                "[green]✓ Alpaca connection successful[/green]",
                box=box.ROUNDED,
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[red]✗ Alpaca connection failed[/red]\n"
                "[dim]Check ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, "
                "and ALPACA_API_BASE_URL in your environment[/dim]",
                box=box.ROUNDED,
                border_style="red",
            )
        )


@app.command("disconnect")
def disconnect():
    """Logical Alpaca disconnect (no persistent session, so this is informational)."""
    console.print("[yellow]Disconnecting Alpaca (logical only)...[/yellow]")
    logger.info("Alpaca disconnect command executed")

    console.print(
        Panel.fit(
            "[cyan]Alpaca uses stateless API keys.[/cyan]\n"
            "[dim]To fully disconnect, remove or rotate your Alpaca API keys "
            "from the environment (.env).[/dim]",
            box=box.ROUNDED,
            border_style="cyan",
        )
    )
