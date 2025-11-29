#!/usr/bin/env python3
"""
Quick demo of TimeManager CLI commands
Run this to verify all CLI commands work correctly
"""
import asyncio
import sys
sys.path.insert(0, '/home/yohannes/mismartera/backend')

from app.cli.time_commands import (
    current_time_command,
    market_status_command,
    trading_session_command,
    next_trading_date_command,
    trading_days_command,
    holidays_command,
    timezone_convert_command
)
from rich.console import Console

console = Console()

async def main():
    console.print("\n[bold cyan]═══════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   TimeManager CLI Commands Demo[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]\n")
    
    # Test 1: Current time
    console.print("[bold yellow]1. Current Time[/bold yellow]")
    await current_time_command()
    console.print()
    
    # Test 2: Current time in different timezone
    console.print("[bold yellow]2. Current Time in UTC[/bold yellow]")
    await current_time_command(timezone="UTC")
    console.print()
    
    # Test 3: Market status
    console.print("[bold yellow]3. Market Status[/bold yellow]")
    await market_status_command(exchange="NYSE")
    console.print()
    
    # Test 4: Trading session for today
    console.print("[bold yellow]4. Trading Session (Today)[/bold yellow]")
    await trading_session_command()
    console.print()
    
    # Test 5: Trading session for a specific date
    console.print("[bold yellow]5. Trading Session (2024-12-25 - Christmas)[/bold yellow]")
    await trading_session_command(date_str="2024-12-25")
    console.print()
    
    # Test 6: Next trading dates
    console.print("[bold yellow]6. Next 3 Trading Dates[/bold yellow]")
    await next_trading_date_command(from_date_str="2024-11-27", n=3)
    console.print()
    
    # Test 7: Count trading days
    console.print("[bold yellow]7. Trading Days in November 2024[/bold yellow]")
    await trading_days_command(start_str="2024-11-01", end_str="2024-11-30")
    console.print()
    
    # Test 8: List holidays
    console.print("[bold yellow]8. Holidays for 2024[/bold yellow]")
    await holidays_command(year=2024)
    console.print()
    
    # Test 9: Timezone conversion
    console.print("[bold yellow]9. Timezone Conversion (ET to UTC)[/bold yellow]")
    await timezone_convert_command("2024-11-25 10:30:00", "America/New_York", "UTC")
    console.print()
    
    console.print("[bold green]✓ All CLI commands executed successfully![/bold green]\n")

if __name__ == "__main__":
    asyncio.run(main())
