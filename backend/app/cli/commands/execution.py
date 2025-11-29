"""CLI commands for order execution and account management
"""
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich import box
from app.logger import logger
from app.database import get_async_session

app = typer.Typer()
console = Console()


@app.command("order")
def place_order(
    symbol: str = typer.Argument(..., help="Stock symbol (e.g., AAPL)"),
    quantity: float = typer.Argument(..., help="Quantity to trade"),
    side: str = typer.Option("BUY", "--side", "-s", help="BUY or SELL"),
    order_type: str = typer.Option("MARKET", "--type", "-t", help="MARKET, LIMIT, STOP"),
    price: float = typer.Option(None, "--price", "-p", help="Limit price (for LIMIT orders)"),
):
    """
    Place a new order
    """
    console.print(f"[yellow]Placing {side} order for {quantity} {symbol}...[/yellow]")
    logger.info(f"Order command: {side} {quantity} {symbol} ({order_type})")
    
    # TODO: Implement actual order placement
    console.print("[dim]Order execution not yet implemented[/dim]")
    console.print("[dim]Requires Schwab API configuration[/dim]")


@app.command("orders")
def list_orders(
    status: str = typer.Option("ALL", "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of orders to show")
):
    """
    List recent orders
    """
    console.print("[yellow]Fetching orders...[/yellow]")
    logger.info("List orders command executed")
    
    # TODO: Implement actual order listing
    console.print("[dim]No orders found (API not configured)[/dim]")


@app.command("cancel")
def cancel_order(
    order_id: str = typer.Argument(..., help="Order ID to cancel")
):
    """
    Cancel an order
    """
    console.print(f"[yellow]Cancelling order {order_id}...[/yellow]")
    logger.info(f"Cancel order command: {order_id}")
    
    # TODO: Implement actual order cancellation
    console.print("[dim]Order cancellation not yet implemented[/dim]")


@app.command("balance")
def show_balance(
    account_id: str = typer.Option("default", "--account", "-a", help="Account ID"),
    no_sync: bool = typer.Option(False, "--no-sync", help="Don't sync from broker")
):
    """
    Show account balance information
    """
    console.print(f"[yellow]Fetching balance for account {account_id}...[/yellow]")
    
    async def _show_balance():
        from app.managers.system_manager import get_system_manager
        
        try:
            system_mgr = get_system_manager()
            exec_mgr = system_mgr.get_execution_manager()
            
            async with get_async_session() as session:
                balance = await exec_mgr.get_balance(
                    session, 
                    account_id=account_id,
                    sync_from_broker=not no_sync
                )
            
            # Display balance in table
            table = Table(title=f"Account Balance ({balance['brokerage']})" , box=box.ROUNDED)
            table.add_column("Metric", style="cyan", width=20)
            table.add_column("Value", style="green", justify="right")
            
            table.add_row("Account ID", balance["account_id"])
            table.add_row("Cash Balance", f"${balance['cash_balance']:,.2f}")
            table.add_row("Buying Power", f"${balance['buying_power']:,.2f}")
            table.add_row("Total Value", f"${balance['total_value']:,.2f}")
            table.add_row("Mode", balance["mode"].upper())
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error fetching balance: {e}[/red]")
            logger.error(f"Balance command error: {e}", exc_info=True)
    
    asyncio.run(_show_balance())


@app.command("positions")
def show_positions(
    account_id: str = typer.Option("default", "--account", "-a", help="Account ID"),
    no_sync: bool = typer.Option(False, "--no-sync", help="Don't sync from broker")
):
    """
    Show current positions
    """
    console.print(f"[yellow]Fetching positions for account {account_id}...[/yellow]")
    
    async def _show_positions():
        from app.managers.system_manager import get_system_manager
        
        try:
            system_mgr = get_system_manager()
            exec_mgr = system_mgr.get_execution_manager()
            
            async with get_async_session() as session:
                positions = await exec_mgr.get_positions(
                    session,
                    account_id=account_id,
                    sync_from_broker=not no_sync
                )
            
            if not positions:
                console.print("[dim]No open positions[/dim]")
                return
            
            # Display positions in table
            table = Table(title="Current Positions", box=box.ROUNDED)
            table.add_column("Symbol", style="cyan", width=8)
            table.add_column("Quantity", justify="right", style="white")
            table.add_column("Avg Price", justify="right", style="white")
            table.add_column("Current Price", justify="right", style="white")
            table.add_column("Market Value", justify="right", style="white")
            table.add_column("Unrealized P&L", justify="right")
            table.add_column("%", justify="right")
            
            total_value = 0
            total_pnl = 0
            
            for pos in positions:
                quantity = pos["quantity"]
                avg_price = pos["avg_entry_price"]
                current_price = pos["current_price"] or 0
                market_value = pos["market_value"] or 0
                unrealized_pnl = pos["unrealized_pnl"] or 0
                
                # Calculate percentage
                cost_basis = avg_price * abs(quantity)
                pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis != 0 else 0
                
                # Color code P&L
                pnl_color = "green" if unrealized_pnl >= 0 else "red"
                pnl_str = f"[{pnl_color}]${unrealized_pnl:+,.2f}[/{pnl_color}]"
                pnl_pct_str = f"[{pnl_color}]{pnl_percent:+.2f}%[/{pnl_color}]"
                
                table.add_row(
                    pos["symbol"],
                    f"{quantity:,.0f}",
                    f"${avg_price:,.2f}",
                    f"${current_price:,.2f}",
                    f"${market_value:,.2f}",
                    pnl_str,
                    pnl_pct_str
                )
                
                total_value += market_value
                total_pnl += unrealized_pnl
            
            # Add total row
            total_color = "green" if total_pnl >= 0 else "red"
            table.add_section()
            table.add_row(
                "[bold]TOTAL[/bold]",
                "",
                "",
                "",
                f"[bold]${total_value:,.2f}[/bold]",
                f"[bold {total_color}]${total_pnl:+,.2f}[/bold {total_color}]",
                ""
            )
            
            console.print(table)
            console.print(f"\n[dim]Total positions: {len(positions)}[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error fetching positions: {e}[/red]")
            logger.error(f"Positions command error: {e}", exc_info=True)
    
    asyncio.run(_show_positions())
