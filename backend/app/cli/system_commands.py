"""System Management CLI Commands.

Commands for controlling the system lifecycle:
- start: Start the system run
- pause: Pause the system run
- resume: Resume from paused state
- stop: Stop the system run
- status: Show current system status
"""
from rich.console import Console
from rich.table import Table, box
from rich import print as rprint
from typing import Optional, List, Dict, Any, Tuple, Union, Set
from enum import Enum
import asyncio
import logging

from app.managers.system_manager import get_system_manager, SystemState
from app.logger import logger


console = Console()


def start_command(config_file_path: str) -> None:
    """Start the system run with a configuration file.
    
    Loads session configuration and starts all configured data streams.
    Transitions to RUNNING state only after successful initialization.
    
    Args:
        config_file_path: Path to session configuration JSON file
                         (defaults to session_configs/example_session.json if not provided)
    
    Example:
        system start
        system start session_configs/example_session.json
        system start ./my_config.json
    """
    system_mgr = get_system_manager()
    
    # Show which config is being used
    if config_file_path == "session_configs/example_session.json":
        console.print(f"[yellow]Starting system with default configuration:[/yellow] {config_file_path}")
    else:
        console.print(f"[yellow]Starting system with configuration:[/yellow] {config_file_path}")
    
    try:
        success = system_mgr.start(config_file_path)
        
        if success:
            console.print("\n[green]✓ System started successfully[/green]")
            if system_mgr.session_config:
                console.print(f"[dim]Session: {system_mgr.session_config.session_name}[/dim]")
                console.print(f"[dim]Active streams: {len(system_mgr.session_config.data_streams)}[/dim]")
                console.print(f"[dim]State: {system_mgr.state.value}[/dim]")
        else:
            if system_mgr.state == SystemState.RUNNING:
                console.print("[yellow]![/yellow] System is already running")
            elif system_mgr.state == SystemState.PAUSED:
                console.print("[yellow]![/yellow] System is paused. Use 'system resume' to continue.")
            else:
                console.print("[red]✗[/red] Failed to start system")
    
    except FileNotFoundError as e:
        console.print(f"\n[red]✗ Configuration file not found[/red]")
        console.print(f"[dim]{str(e)}[/dim]")
    except ValueError as e:
        console.print(f"\n[red]✗ Configuration validation error[/red]")
        console.print(f"[dim]{str(e)}[/dim]")
    except Exception as e:
        console.print(f"\n[red]✗ System startup failed[/red]")
        console.print(f"[dim]{str(e)}[/dim]")
        logger.error(f"System start command error: {e}", exc_info=True)


def pause_command() -> None:
    """Pause the system run.
    
    Suspends all operations while maintaining state.
    
    Example:
        system pause
    """
    system_mgr = get_system_manager()
    
    success = system_mgr.pause()
    
    if success:
        console.print("[green]✓[/green] System paused")
        console.print("[dim]Use 'system resume' to continue[/dim]")
    else:
        console.print(f"[yellow]![/yellow] Cannot pause system in state: {system_mgr.state.value}")


def resume_command() -> None:
    """Resume the system from paused state.
    
    Continues operations from where they were paused.
    
    Example:
        system resume
    """
    system_mgr = get_system_manager()
    
    success = system_mgr.resume()
    
    if success:
        console.print("[green]✓[/green] System resumed")
        console.print(f"[dim]State: {system_mgr.state.value}[/dim]")
    else:
        console.print(f"[yellow]![/yellow] Cannot resume system in state: {system_mgr.state.value}")


def stop_command() -> None:
    """Stop the system run.
    
    Stops all data streams and transitions to STOPPED state.
    
    Example:
        system stop
    """
    system_mgr = get_system_manager()
    
    success = system_mgr.stop()
    
    if success:
        console.print("[green]✓[/green] System stopped")
        console.print("[dim]All data streams have been stopped[/dim]")
        console.print(f"[dim]State: {system_mgr.state.value}[/dim]")
    else:
        console.print("[yellow]![/yellow] System is already stopped")


def mode_command(mode: str) -> None:
    """Set operation mode (live or backtest).
    
    Args:
        mode: "live" or "backtest"
    
    Example:
        system mode backtest
        system mode live
    """
    system_mgr = get_system_manager()
    
    success = system_mgr.set_mode(mode)
    
    if success:
        console.print(f"[green]✓[/green] Operation mode set to: {system_mgr.mode.value}")
    else:
        console.print(f"[red]✗[/red] Failed to set mode to: {mode}")
        if system_mgr.state != SystemState.STOPPED:
            console.print("[yellow]![/yellow] System must be stopped to change mode. Stop the system first.")



def status_command() -> None:
    """Show comprehensive system status.
    
    Displays detailed status of all system components including managers,
    session data, market status, background threads, and configuration.
    
    Example:
        system status
    """
    from app.cli.system_status_impl import show_comprehensive_status
    
    # Delegate to the comprehensive implementation
    show_comprehensive_status()
