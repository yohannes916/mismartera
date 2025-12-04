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
                sdc = system_mgr.session_config.session_data_config
                console.print(f"[dim]Symbols: {', '.join(sdc.symbols)}[/dim]")
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


def export_status_command(complete: bool = True, filename: Optional[str] = None, format: str = "expanded") -> None:
    """Export system status to JSON file.
    
    Exports complete system state including session data, threads, performance metrics,
    and configuration to a JSON file. Supports delta mode for efficient updates.
    
    Args:
        complete: If True, export full data. If False, export delta from last export.
                 Default: True
        filename: Output file path. If not provided, auto-generates to data/status/:
                 data/status/system_status_<session_config_name>_<complete|delta>_<date>_<time>.json
        format: Array formatting - "expanded" (multi-line, default) or "compact" (single-line for inspection)
    
    Examples:
        system export-status
        system export-status complete=false
        system export-status format=compact  # Single-line arrays for easier inspection
        system export-status complete=true status/my_status.json
        system export-status my_status.json
    """
    import json
    import re
    from pathlib import Path
    
    system_mgr = get_system_manager()
    
    try:
        import time
        
        # Track timing for metadata
        start_time = time.time()
        
        # Get system state (complete or delta)
        system_state = system_mgr.system_info(complete=complete)
        
        # Auto-generate filename if not provided
        if filename is None:
            from datetime import datetime
            
            # Get current time (prefer TimeManager, fallback to system time)
            try:
                time_mgr = system_mgr.get_time_manager()
                current_time = time_mgr.get_current_time()
            except Exception:
                current_time = datetime.now()
            
            config_name = "default"
            if system_mgr.session_config:
                config_name = system_mgr.session_config.session_name.replace(" ", "_")
            
            mode_suffix = "complete" if complete else "delta"
            timestamp = current_time.strftime("%Y%m%d_%H%M%S")
            filename = f"data/status/system_status_{config_name}_{mode_suffix}_{timestamp}.json"
        
        # Ensure directory exists
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Track JSON serialization time
        json_start = time.time()
        json_str = json.dumps(system_state, indent=2, default=str)
        json_time_ms = (time.time() - json_start) * 1000
        
        # Track compact formatting time (if applied)
        compact_time_ms = 0
        if format == "compact":
            compact_start = time.time()
            
            # Compact bar data arrays - any array containing only primitives (no nested objects/arrays)
            # This makes bar data like ["09:34:00", 13.48, 13.48, 13.48, 13.48, 1072.0] single-line
            def compact_simple_array(match):
                """Compact a multi-line array containing only primitives into a single line."""
                array_content = match.group(1)  # Content between [ and ]
                # Extract all values (strings, numbers, booleans, nulls)
                values = re.findall(r'"[^"]*"|-?\d+\.?\d*(?:[eE][+-]?\d+)?|true|false|null', array_content)
                if values:  # Only compact if we found values
                    return f"[{', '.join(values)}]"
                return match.group(0)  # Return original if no match
            
            # Match arrays that:
            # 1. Start with [ and end with ]
            # 2. Contain newlines (multi-line)
            # 3. Don't contain nested { } or [ ] (only primitives)
            # This pattern works for bar data arrays but preserves structure of complex nested arrays
            pattern = r'\[([^\[\]{}]*\n[^\[\]{}]*)\]'
            json_str = re.sub(pattern, compact_simple_array, json_str)
            
            compact_time_ms = (time.time() - compact_start) * 1000
        
        # Calculate total time up to this point (before metadata update)
        total_time_ms = (time.time() - start_time) * 1000
        
        # Update metadata with timing information
        # Parse back to dict to update metadata
        system_state_updated = json.loads(json_str)
        if "_metadata" in system_state_updated:
            system_state_updated["_metadata"]["export_timing"] = {
                "_info": "Time taken to prepare JSON export (ms)",
                "total_ms": round(total_time_ms, 2),
                "json_serialization_ms": round(json_time_ms, 2),
                "compact_formatting_ms": round(compact_time_ms, 2) if format == "compact" else None,
                "format_applied": format
            }
        
        # Re-serialize with updated metadata
        json_str = json.dumps(system_state_updated, indent=2, default=str)
        
        # Re-apply compact formatting if it was requested (metadata update breaks it)
        if format == "compact":
            def compact_simple_array(match):
                array_content = match.group(1)
                values = re.findall(r'"[^"]*"|-?\d+\.?\d*(?:[eE][+-]?\d+)?|true|false|null', array_content)
                if values:
                    return f"[{', '.join(values)}]"
                return match.group(0)
            
            pattern = r'\[([^\[\]{}]*\n[^\[\]{}]*)\]'
            json_str = re.sub(pattern, compact_simple_array, json_str)
        
        with open(filepath, 'w') as f:
            f.write(json_str)
        
        file_size = filepath.stat().st_size
        export_mode = "complete" if complete else "delta"
        console.print(f"[green]✓[/green] System status exported to: {filepath}")
        console.print(f"[dim]Mode: {export_mode} | Format: {format} | File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)[/dim]")
        
        # Show timing information
        timing_parts = [f"Total: {total_time_ms:.0f}ms", f"Serialization: {json_time_ms:.0f}ms"]
        if format == "compact":
            timing_parts.append(f"Compact: {compact_time_ms:.0f}ms")
        console.print(f"[dim]Export timing: {' | '.join(timing_parts)}[/dim]")
        
        # Show summary
        if "session_data" in system_state and "symbols" in system_state["session_data"]:
            symbol_count = len(system_state["session_data"]["symbols"])
            console.print(f"[dim]Symbols: {symbol_count}[/dim]")
        
        if "threads" in system_state:
            thread_count = len(system_state["threads"])
            console.print(f"[dim]Threads: {thread_count}[/dim]")
    
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to export system status")
        console.print(f"[dim]{str(e)}[/dim]")
        logger.error(f"Export status command error: {e}", exc_info=True)
