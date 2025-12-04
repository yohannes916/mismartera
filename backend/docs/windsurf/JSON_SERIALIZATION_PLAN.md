# JSON Serialization with Diff Tracking - Implementation Plan

## Overview

Add comprehensive JSON serialization to all major system components with intelligent diff tracking for performance optimization. All work happens synchronously in the caller's thread.

## Architecture

### Core Components

1. **DiffTracker Base Class** - Handles state comparison and diff generation
2. **SymbolSessionData.to_json()** - Per-symbol serialization with diff tracking
3. **SessionData.to_json()** - Aggregates all symbols
4. **Thread base classes** - Mixin for thread serialization
5. **SystemManager.to_json()** - Top-level aggregator API

### Flags

- **`complete: bool`** (default=False)
  - If True: Return complete object
  - If False: Return only changed items since last call
  
- **`debug: bool`** (default=False)
  - If False: Only current session data (streamed + derived)
  - If True: Include historical data, performance metrics, queue stats

### Bar Data Format

For efficiency, bars are serialized as:
```json
{
  "columns": ["timestamp", "open", "high", "low", "close", "volume"],
  "data": [
    ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
    ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000]
  ]
}
```

This format is ~50% smaller than array of dicts and faster to serialize/deserialize.

## Implementation Steps

### Phase 1: Base Infrastructure

**File:** `/backend/app/core/diff_tracker.py` (NEW)

```python
class DiffTracker:
    """Base class for diff tracking in JSON serialization."""
    
    def __init__(self):
        self._last_snapshot = {}
        self._last_hash = None
    
    def compute_diff(self, current_data: dict) -> tuple[dict, list[str]]:
        """
        Compare current data with last snapshot.
        Returns: (diff_dict, changed_paths)
        """
        pass
    
    def update_snapshot(self, data: dict):
        """Update the last snapshot."""
        pass
    
    def reset_snapshot(self):
        """Clear snapshot (forces complete next time)."""
        pass
```

### Phase 2: SymbolSessionData Serialization

**File:** `/backend/app/state/session_data.py`

Add to `SymbolSessionData` class:

```python
class SymbolSessionData(DiffTracker):
    def __init__(self, symbol: str):
        super().__init__()
        # ... existing code ...
    
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        """
        Serialize symbol data to JSON.
        
        Args:
            complete: If True, return full object. If False, return diff.
            debug: If True, include historical data and performance metrics.
        
        Returns:
            Dictionary suitable for JSON serialization.
        """
        data = {
            "symbol": self.symbol,
            "volume": self.volume,
            "high": self.high,
            "low": self.low,
            "vwap": self.vwap,
            "bar_counts": {},
            "bar_quality": self.bar_quality,
            "bars_updated": self.bars_updated,
            "time_range": {
                "first_bar": self.first_bar_ts.strftime("%H:%M:%S") if self.first_bar_ts else None,
                "last_bar": self.last_bar_ts.strftime("%H:%M:%S") if self.last_bar_ts else None
            }
        }
        
        # Add bar counts
        with self._lock:
            if self.bars_1m:
                data["bar_counts"]["1m"] = len(self.bars_1m)
            if self.bars_5m:
                data["bar_counts"]["5m"] = len(self.bars_5m)
            # ... other intervals ...
            
            # Current session bars (NOT historical)
            if debug:
                data["current_bars"] = self._serialize_bars(only_session=True)
                data["historical_summary"] = self._get_historical_summary()
                data["performance"] = self._get_performance_metrics()
        
        # Apply diff tracking
        if complete:
            self.update_snapshot(data)
            return data
        else:
            diff, changed_paths = self.compute_diff(data)
            self.update_snapshot(data)
            return diff if diff else data  # Return full if first call
    
    def _serialize_bars(self, only_session: bool = True) -> dict:
        """Serialize bars in efficient array format."""
        result = {}
        
        with self._lock:
            for interval in ["1m", "5m", "15m", "30m", "1h"]:
                bars = getattr(self, f"bars_{interval}", None)
                if bars is None or bars.empty:
                    continue
                
                # Filter to session only if requested
                if only_session and self.first_bar_ts:
                    bars = bars[bars.index >= self.first_bar_ts]
                
                if not bars.empty:
                    result[interval] = {
                        "columns": ["timestamp", "open", "high", "low", "close", "volume"],
                        "data": [
                            [
                                row.Index.strftime("%H:%M:%S"),
                                float(row.open),
                                float(row.high),
                                float(row.low),
                                float(row.close),
                                int(row.volume)
                            ]
                            for row in bars.itertuples()
                        ]
                    }
        
        return result
    
    def _get_historical_summary(self) -> dict:
        """Get summary of historical data."""
        return {
            "loaded": self.historical_loaded,
            "bar_counts": {
                "1m": len(self.bars_1m) if self.bars_1m is not None else 0,
                "5m": len(self.bars_5m) if self.bars_5m is not None else 0,
                # ... other intervals ...
            },
            "date_range": {
                "start": self.historical_start_date.isoformat() if self.historical_start_date else None,
                "end": self.historical_end_date.isoformat() if self.historical_end_date else None
            }
        }
    
    def _get_performance_metrics(self) -> dict:
        """Get performance metrics."""
        return {
            "last_update_ms": self._last_update_duration_ms,
            "total_updates": self._update_count
        }
```

### Phase 3: SessionData Serialization

**File:** `/backend/app/state/session_data.py`

Add to `SessionData` class:

```python
class SessionData(DiffTracker):
    def __init__(self):
        super().__init__()
        # ... existing code ...
    
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        """
        Serialize session data to JSON.
        
        Args:
            complete: If True, return full object. If False, return diff.
            debug: If True, include detailed data from symbols.
        
        Returns:
            Dictionary suitable for JSON serialization.
        """
        data = {
            "system": {
                "state": self.system_state,
                "mode": self.system_mode
            },
            "session": {
                "date": self.session_date.isoformat() if self.session_date else None,
                "time": self.session_time.strftime("%H:%M:%S") if self.session_time else None,
                "active": self.session_active,
                "ended": self.session_ended,
                "symbol_count": len(self.symbols)
            },
            "symbols": {}
        }
        
        # Add all symbols
        with self._lock:
            for symbol, symbol_data in self.symbols.items():
                data["symbols"][symbol] = symbol_data.to_json(complete=complete, debug=debug)
        
        # Apply diff tracking
        if complete:
            self.update_snapshot(data)
            return data
        else:
            diff, changed_paths = self.compute_diff(data)
            self.update_snapshot(data)
            return diff if diff else data
```

### Phase 4: Thread Serialization

**File:** `/backend/app/threads/base_thread.py` (NEW)

```python
class JsonSerializableMixin(DiffTracker):
    """Mixin for threads to add JSON serialization."""
    
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        """
        Serialize thread state to JSON.
        
        Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement to_json()")
    
    def _get_thread_info(self) -> dict:
        """Get basic thread information."""
        return {
            "name": self.name,
            "is_alive": self.is_alive(),
            "daemon": self.daemon
        }
```

**Update existing threads:**

1. **SessionCoordinator** (`/backend/app/threads/session_coordinator.py`)
2. **DataUpkeepThread** (`/backend/app/threads/data_upkeep_thread.py`)
3. **BacktestStreamCoordinator** (`/backend/app/managers/data_manager/backtest_stream_coordinator.py`)

Each implements:
```python
def to_json(self, complete: bool = False, debug: bool = False) -> dict:
    data = {
        "thread_info": self._get_thread_info(),
        "state": self._state,
        # ... thread-specific data ...
    }
    
    if debug:
        data["performance"] = self._get_performance_metrics()
    
    # Apply diff tracking
    if complete:
        self.update_snapshot(data)
        return data
    else:
        diff, changed_paths = self.compute_diff(data)
        self.update_snapshot(data)
        return diff if diff else data
```

### Phase 5: SystemManager API

**File:** `/backend/app/managers/system_manager.py`

```python
class SystemManager(DiffTracker):
    def __init__(self):
        super().__init__()
        # ... existing code ...
    
    def to_json(self, complete: bool = False, debug: bool = False) -> dict:
        """
        Get complete system state as JSON.
        
        Args:
            complete: If True, return full object. If False, return diff.
            debug: If True, include performance metrics and detailed data.
        
        Returns:
            Dictionary with system_manager, threads, and session_data.
        """
        # Get time manager for current time
        time_mgr = self.get_time_manager()
        current_time = time_mgr.get_current_time()
        
        data = {
            "system_manager": {
                "state": self.state,
                "mode": self.mode,
                "timezone": str(time_mgr.get_market_timezone()),
                "backtest_window": {
                    "start_date": time_mgr.backtest_start_date.isoformat() if time_mgr.backtest_start_date else None,
                    "end_date": time_mgr.backtest_end_date.isoformat() if time_mgr.backtest_end_date else None
                }
            },
            "threads": {},
            "session_data": None
        }
        
        if debug:
            data["system_manager"]["performance"] = {
                "uptime_seconds": (current_time - self._start_time).total_seconds(),
                "memory_usage_mb": self._get_memory_usage()
            }
        
        # Add threads
        if self._session_coordinator:
            data["threads"]["session_coordinator"] = self._session_coordinator.to_json(complete=complete, debug=debug)
        
        # Add data manager threads
        dm = self.get_data_manager()
        if dm:
            # Data upkeep thread
            if hasattr(dm, '_data_upkeep_thread') and dm._data_upkeep_thread:
                data["threads"]["data_upkeep"] = dm._data_upkeep_thread.to_json(complete=complete, debug=debug)
            
            # Stream coordinator
            if hasattr(dm, '_stream_coordinator') and dm._stream_coordinator:
                data["threads"]["stream_coordinator"] = dm._stream_coordinator.to_json(complete=complete, debug=debug)
        
        # Add session data
        session_data = self.get_session_data()
        if session_data:
            data["session_data"] = session_data.to_json(complete=complete, debug=debug)
        
        # Add metadata
        all_changed_paths = []
        data["_metadata"] = {
            "generated_at": current_time.isoformat(),
            "complete": complete,
            "debug": debug,
            "diff_mode": not complete
        }
        
        # Apply diff tracking at top level
        if complete:
            self.update_snapshot(data)
            return data
        else:
            diff, changed_paths = self.compute_diff(data)
            self.update_snapshot(data)
            
            if changed_paths:
                data["_metadata"]["changed_paths"] = changed_paths
            
            return diff if diff else data
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
```

### Phase 6: CLI Command

**File:** `/backend/app/cli/system_commands.py`

```python
async def system_json_handler(
    system_mgr: 'SystemManager',
    complete: str = "false",
    debug: str = "false"
) -> None:
    """
    Get system state as JSON.
    
    Usage:
        system json                     # Diff mode, no debug
        system json --complete          # Full object
        system json --debug             # Diff mode with debug info
        system json --complete --debug  # Full object with debug info
    """
    complete_flag = complete.lower() == "true"
    debug_flag = debug.lower() == "true"
    
    json_data = system_mgr.to_json(complete=complete_flag, debug=debug_flag)
    
    # Pretty print
    import json
    print(json.dumps(json_data, indent=2))
```

Register command:
```python
registry.register_command(
    namespace="system",
    command="json",
    handler=system_json_handler,
    description="Get system state as JSON",
    parameters=[
        CommandParameter("complete", "boolean", False, "Return complete object (not diff)"),
        CommandParameter("debug", "boolean", False, "Include debug information")
    ]
)
```

## Performance Considerations

1. **Bar Serialization**: Array format is ~50% smaller than dict format
2. **Diff Tracking**: Only changed data is returned (except first call or complete=True)
3. **Locking**: All data access uses existing locks (thread-safe)
4. **Caller's Thread**: All work happens synchronously (no threading overhead)
5. **Memory**: Snapshots are shallow dicts (minimal overhead)

## Testing Strategy

1. **Unit Tests**: Test each component's to_json() in isolation
2. **Integration Tests**: Test full system_manager.to_json()
3. **Diff Tests**: Verify diff tracking works correctly
4. **Performance Tests**: Measure serialization time with large datasets
5. **Memory Tests**: Verify snapshot memory usage

## Files to Create

1. `/backend/app/core/diff_tracker.py` - Base diff tracking class
2. `/backend/app/threads/base_thread.py` - Thread serialization mixin
3. `/backend/tests/test_json_serialization.py` - Unit tests
4. `/backend/docs/windsurf/JSON_SERIALIZATION_API.md` - API documentation

## Files to Modify

1. `/backend/app/state/session_data.py` - Add to_json() to SymbolSessionData and SessionData
2. `/backend/app/threads/session_coordinator.py` - Add to_json()
3. `/backend/app/threads/data_upkeep_thread.py` - Add to_json()
4. `/backend/app/managers/data_manager/backtest_stream_coordinator.py` - Add to_json()
5. `/backend/app/managers/system_manager.py` - Add to_json() API
6. `/backend/app/cli/system_commands.py` - Add system json command
7. `/backend/app/cli/command_registry.py` - Register new command

## Implementation Order

1. **DiffTracker base class** - Core infrastructure
2. **SymbolSessionData.to_json()** - Smallest unit
3. **SessionData.to_json()** - Aggregates symbols
4. **Thread mixin and implementations** - Individual threads
5. **SystemManager.to_json()** - Top-level aggregator
6. **CLI command** - User interface
7. **Tests** - Validation
8. **Documentation** - Usage guide

## Example Usage

```bash
# In CLI
system@mismartera: system json
# Returns diff (only changed items)

system@mismartera: system json --complete
# Returns full object

system@mismartera: system json --debug
# Returns diff with performance metrics, historical data, queue stats

system@mismartera: system json --complete --debug
# Returns full object with all debug information
```

## Future Enhancements

1. **WebSocket API**: Stream JSON updates in real-time
2. **HTTP API**: REST endpoint for system state
3. **Compression**: Gzip compression for large payloads
4. **Filtering**: Allow selective component serialization
5. **Export**: Save JSON to file for analysis
