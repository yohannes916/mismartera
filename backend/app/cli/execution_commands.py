"""
CLI commands for order execution and account management
"""
from typing import Optional
from datetime import datetime, date, timedelta
import asyncio

from rich.table import Table
from rich.console import Console
from rich import box

from app.logger import logger
from app.cli.command_registry import EXECUTION_COMMANDS
from app.models.database import SessionLocal


console = Console()


def get_execution_manager():
    """Get ExecutionManager instance via SystemManager."""
    from app.managers.system_manager import get_system_manager
    system_mgr = get_system_manager()
    return system_mgr.get_execution_manager()


def print_execution_usage(_console: Console) -> None:
    """Print execution command usage lines to the given console.
    
    Single source of truth comes from EXECUTION_COMMANDS in command_registry.
    """
    _console.print("[red]Usage:[/red]")
    for meta in EXECUTION_COMMANDS:
        _console.print(f"  {meta.usage} - {meta.description}")


async def select_execution_api_command(provider: str):
    """Select execution/trading API provider (alpaca, schwab, or mismartera)."""
    provider = provider.lower()
    
    if provider not in ["alpaca", "schwab", "mismartera"]:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print("[yellow]Available providers:[/yellow]")
        console.print("  • alpaca   - Alpaca Markets API (live/paper)")
        console.print("  • schwab   - Charles Schwab API (live)")
        console.print("  • mismartera - Simulated backtesting (internal)")
        return
    
    try:
        exec_mgr = get_execution_manager()
        exec_mgr.set_brokerage(provider)
        
        # Test connection
        console.print(f"[yellow]Testing {provider} connection...[/yellow]")
        
        if provider == "alpaca":
            from app.integrations.alpaca_client import alpaca_client
            connected = await alpaca_client.validate_connection()
        elif provider == "schwab":
            from app.integrations.schwab_client import schwab_client
            connected = await schwab_client.validate_connection()
        elif provider == "mismartera":
            # Mismartera is internal - always connected
            connected = True
        else:
            connected = False
        
        if connected:
            console.print(f"[green]✓ Execution API provider set to {provider} and connected[/green]")
            if provider == "mismartera":
                console.print(f"[dim]  Simulated backtesting mode - orders will be executed using session_data pricing[/dim]")
        else:
            console.print(f"[yellow]⚠ Execution API provider set to {provider} but connection failed[/yellow]")
            console.print(f"[dim]Check credentials and try again[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error setting execution API: {e}[/red]")
        logger.error(f"Execution API selection error: {e}", exc_info=True)


async def balance_command(account_id: str = "default", no_sync: bool = False):
    """Show account balance information."""
    console.print(f"[yellow]Fetching balance for account {account_id}...[/yellow]")
    
    try:
        exec_mgr = get_execution_manager()
        
        with SessionLocal() as session:
            balance = await exec_mgr.get_balance(
                session,
                account_id=account_id,
                sync_from_broker=not no_sync
            )
        
        # Display balance in table
        table = Table(
            title=f"Account Balance ({balance['brokerage']})",
            box=box.ROUNDED
        )
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Account ID", balance["account_id"])
        table.add_row("Cash Balance", f"${balance['cash_balance']:,.2f}")
        table.add_row("Buying Power", f"${balance['buying_power']:,.2f}")
        table.add_row("Total Value", f"${balance['total_value']:,.2f}")
        table.add_row("Mode", balance["mode"].upper())
        
        console.print(table)
        
        if not no_sync:
            console.print("[dim]✓ Synced from broker[/dim]")
        else:
            console.print("[dim]⚠ Using cached data (no broker sync)[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error fetching balance: {e}[/red]")
        logger.error(f"Balance command error: {e}", exc_info=True)


async def positions_command(account_id: str = "default", no_sync: bool = False):
    """Show current positions."""
    console.print(f"[yellow]Fetching positions for account {account_id}...[/yellow]")
    
    try:
        exec_mgr = get_execution_manager()
        
        with SessionLocal() as session:
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
        
        if not no_sync:
            console.print("[dim]✓ Synced from broker[/dim]")
        else:
            console.print("[dim]⚠ Using cached data (no broker sync)[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error fetching positions: {e}[/red]")
        logger.error(f"Positions command error: {e}", exc_info=True)


async def orders_command(
    account_id: str = "default",
    status: Optional[str] = None,
    days: int = 7
):
    """Show order history."""
    console.print(f"[yellow]Fetching orders for account {account_id}...[/yellow]")
    
    try:
        exec_mgr = get_execution_manager()
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        with SessionLocal() as session:
            orders = await exec_mgr.get_order_history(
                session,
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                status=status
            )
        
        if not orders:
            console.print(f"[dim]No orders found in last {days} days[/dim]")
            return
        
        # Display orders in table
        title = f"Order History (Last {days} days)"
        if status:
            title += f" - Status: {status}"
        
        table = Table(title=title, box=box.ROUNDED)
        table.add_column("Order ID", style="cyan", width=12)
        table.add_column("Time", style="white", width=16)
        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Side", style="white", width=4)
        table.add_column("Qty", justify="right", style="white")
        table.add_column("Type", style="white")
        table.add_column("Price", justify="right", style="white")
        table.add_column("Status", justify="center")
        
        for order in orders:
            # Determine status color
            status_str = order["status"]
            if status_str == "FILLED":
                status_color = "green"
            elif status_str in ["CANCELLED", "REJECTED"]:
                status_color = "red"
            elif status_str in ["PENDING", "WORKING"]:
                status_color = "yellow"
            else:
                status_color = "white"
            
            # Format timestamp
            created_at = order["created_at"]
            if isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime("%m/%d %H:%M:%S")
                except:
                    time_str = created_at[:16]
            else:
                time_str = str(created_at)[:16]
            
            # Format price
            price = order.get("price") or order.get("avg_fill_price")
            price_str = f"${price:.2f}" if price else "-"
            
            table.add_row(
                order["order_id"][:12],
                time_str,
                order["symbol"],
                order["side"],
                f"{order['quantity']:.0f}",
                order["order_type"],
                price_str,
                f"[{status_color}]{status_str}[/{status_color}]"
            )
        
        console.print(table)
        console.print(f"\n[dim]Total orders: {len(orders)}[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error fetching orders: {e}[/red]")
        logger.error(f"Orders command error: {e}", exc_info=True)


async def place_order_command(
    symbol: str,
    quantity: float,
    side: str = "BUY",
    order_type: str = "MARKET",
    price: Optional[float] = None,
    account_id: str = "default"
):
    """Place a new order."""
    console.print(f"[yellow]Placing {side} order for {quantity} {symbol}...[/yellow]")
    
    try:
        exec_mgr = get_execution_manager()
        
        with SessionLocal() as session:
            result = await exec_mgr.place_order(
                session,
                account_id=account_id,
                symbol=symbol.upper(),
                quantity=quantity,
                side=side.upper(),
                order_type=order_type.upper(),
                price=price,
                time_in_force="DAY"
            )
        
        # Display result
        console.print(f"[green]✓ Order placed successfully[/green]")
        console.print(f"  Order ID: [cyan]{result['order_id']}[/cyan]")
        console.print(f"  Status: [{result['status']}]{result['status']}[/{result['status']}]")
        console.print(f"  Symbol: {result['symbol']}")
        console.print(f"  Quantity: {result['quantity']}")
        console.print(f"  Side: {result['side']}")
        console.print(f"  Type: {result['order_type']}")
        
    except Exception as e:
        console.print(f"[red]✗ Error placing order: {e}[/red]")
        logger.error(f"Place order command error: {e}", exc_info=True)


async def cancel_order_command(order_id: str):
    """Cancel an order."""
    console.print(f"[yellow]Cancelling order {order_id}...[/yellow]")
    
    try:
        exec_mgr = get_execution_manager()
        
        with SessionLocal() as session:
            result = await exec_mgr.cancel_order(session, order_id)
        
        console.print(f"[green]✓ Order {order_id} cancelled successfully[/green]")
        
    except Exception as e:
        console.print(f"[red]✗ Error cancelling order: {e}[/red]")
        logger.error(f"Cancel order command error: {e}", exc_info=True)
