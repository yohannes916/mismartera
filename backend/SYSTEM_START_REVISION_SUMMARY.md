# System Start() Revision - Implementation Summary

## Objective Completed ✅

Revised the `system_manager.start()` functionality with strict configuration requirements as specified.

## Requirements Met

### 1. ✅ Mandatory Configuration Parameter
- `start()` now requires `config_file_path: str` parameter
- No default or optional path accepted
- Raises `ValueError` if path is None, empty, or invalid

### 2. ✅ Strict File Requirement and Error Handling
- No fallback to default files
- Raises `FileNotFoundError` if file doesn't exist
- Raises `json.JSONDecodeError` if file is not valid JSON
- Raises `ValueError` if configuration validation fails
- System state remains STOPPED on any failure

### 3. ✅ Configuration and Integration Logic
- Successfully parses JSON configuration with:
  - `data_streams` section
  - `trading_config` section
  - `api_config` section
  - Optional `metadata` section
- Iterates through data streams
- Calls `data_manager.start_stream()` for each entry

### 4. ✅ State Management Order
- Configuration loaded and validated FIRST
- All data streams started SECOND
- System transitions to RUNNING LAST
- Critical sequence enforced to prevent data processing before streams are ready

### 5. ✅ Configurable Session Parameters
Session configurations now support:
- **Max buying power** - Total capital available
- **Max per trade** - Maximum amount per trade
- **Max per symbol** - Maximum position size per symbol
- **Max open positions** - Concurrent position limit
- **Data API** - Provider selection (alpaca, schwab)
- **Trade API** - Trading API provider
- **Account ID** - Account identifier if applicable
- **Paper trading mode** - Paper vs live trading flag
- **Multiple data streams** - Bars, ticks, quotes for any symbol

## Files Created

### 1. Session Configuration Model
**File**: `app/models/session_config.py`

**Classes:**
- `DataStreamConfig` - Individual stream configuration
- `TradingConfig` - Trading parameters and risk limits
- `APIConfig` - API provider configuration
- `SessionConfig` - Root configuration object

**Features:**
- Full validation for all fields
- Clear error messages
- Type safety with dataclasses
- JSON deserialization

### 2. Example Configuration
**File**: `session_configs/example_session.json`

**Contains:**
- 3 data streams (2 bars, 1 tick)
- Complete trading configuration
- API configuration
- Metadata section

### 3. Documentation
**File**: `SESSION_CONFIG_SYSTEM.md`

**Covers:**
- Complete configuration format
- Usage examples
- Error handling
- Best practices
- Migration guide
- Configuration templates

## Files Modified

### 1. System Manager
**File**: `app/managers/system_manager.py`

**Changes:**
- Added `SessionConfig` import
- Added `_session_config` field to store configuration
- **Completely rewrote `start()` method:**
  - Now async
  - Requires `config_file_path` parameter
  - Strict validation (no defaults)
  - Loads and validates JSON configuration
  - Starts all configured data streams
  - Only transitions to RUNNING after streams started
  - Comprehensive error handling with clear messages
- **Updated `stop()` method:**
  - Now async
  - Stops all active data streams
  - Clears session configuration
- Added `session_config` property for external access

### 2. System Commands
**File**: `app/cli/system_commands.py`

**Changes:**
- **Updated `start_command()`:**
  - Now requires `config_file_path` parameter
  - Async implementation with await
  - Comprehensive error handling (FileNotFoundError, ValueError, etc.)
  - Displays session info on success
- **Updated `stop_command()`:**
  - Now async
  - Calls async stop() method

### 3. Interactive CLI
**File**: `app/cli/interactive.py`

**Changes:**
- Updated system start handler to:
  - Check for config file path argument
  - Display error if missing
  - Pass config path to start_command
  - Show usage example on error

### 4. Command Registry
**File**: `app/cli/command_registry.py`

**Changes:**
- Updated `system start` command metadata:
  - Usage: `system start <config_file>`
  - Description updated
  - Examples added with actual paths

## API Changes

### Before
```python
# Old synchronous API
system_mgr.start()  # No parameters
system_mgr.stop()   # Synchronous
```

### After
```python
# New async API
system_mgr.start("session_configs/my_session.json")  # Required path
system_mgr.stop()  # Async
```

## CLI Changes

### Before
```bash
system start  # No arguments needed
```

### After
```bash
system start session_configs/example_session.json  # Config required
system start ./my_config.json
```

## Error Messages

### Missing Configuration
```
ValueError: Configuration file path is mandatory.
You must provide a valid path to a session configuration file.
```

### File Not Found
```
FileNotFoundError: Configuration file not found: config.json
Absolute path: /home/user/mismartera/backend/config.json
Please provide a valid path to a session configuration file.
```

### Invalid JSON
```
json.JSONDecodeError: Configuration file contains invalid JSON: config.json
Error: Expecting property name enclosed in double quotes
```

### Validation Error
```
ValueError: Configuration validation failed: config.json
Error: max_per_trade cannot exceed max_buying_power
```

### Stream Startup Failure
```
Exception: Failed to start stream: bars AAPL
(All previously started streams are automatically stopped)
```

## Startup Sequence

```
1. CLI: system start <config_file>
   ↓
2. Validate file path exists and is not empty
   ↓
3. Read and parse JSON file
   ↓
4. Create SessionConfig and validate all fields
   ↓
5. Initialize managers if needed
   ↓
6. Apply API configuration
   ↓
7. Start each data stream sequentially:
   ├─ Stream 1: bars AAPL 1m ✓
   ├─ Stream 2: bars TSLA 1m ✓
   └─ Stream 3: ticks AAPL ✓
   ↓
8. ✅ ONLY NOW: Transition to RUNNING state
   ↓
9. Display success summary with:
   - Session name
   - Number of active streams
   - Max buying power
   - Max per trade
   - Paper trading status
```

## Configuration Schema

```json
{
  "session_name": "string (required)",
  "data_streams": [
    {
      "type": "bars|ticks|quotes (required)",
      "symbol": "string (required)",
      "interval": "string (required for bars only)",
      "output_file": "string (optional)"
    }
  ],
  "trading_config": {
    "max_buying_power": "number (required, > 0)",
    "max_per_trade": "number (required, > 0, <= max_buying_power)",
    "max_per_symbol": "number (required, > 0, <= max_buying_power)",
    "max_open_positions": "number (optional, default 10)",
    "paper_trading": "boolean (optional, default true)"
  },
  "api_config": {
    "data_api": "alpaca|schwab (required)",
    "trade_api": "alpaca|schwab (required)",
    "account_id": "string (optional)"
  },
  "metadata": {
    "created_by": "string (optional)",
    "description": "string (optional)",
    "strategy": "string (optional)",
    ...
  }
}
```

## Validation Rules

### Session Name
- ✅ Must not be empty
- ✅ Must be a string

### Data Streams
- ✅ At least one stream required
- ✅ Type must be "bars", "ticks", or "quotes"
- ✅ Symbol cannot be empty
- ✅ Bars must have interval specified
- ✅ Each stream individually validated

### Trading Config
- ✅ All amounts must be positive
- ✅ max_per_trade ≤ max_buying_power
- ✅ max_per_symbol ≤ max_buying_power
- ✅ max_open_positions must be positive

### API Config
- ✅ data_api must be valid provider
- ✅ trade_api must be valid provider
- ✅ Validated against allowed list

## Testing Scenarios

### ✅ Valid Configuration
```bash
system start session_configs/example_session.json
# Result: System starts successfully with all streams
```

### ✅ Missing File
```bash
system start nonexistent.json
# Result: FileNotFoundError with clear message
```

### ✅ Empty Path
```bash
system start ""
# Result: ValueError - Configuration file path is mandatory
```

### ✅ Invalid JSON
```bash
system start broken.json
# Result: json.JSONDecodeError with details
```

### ✅ Validation Failure
```bash
# Config has max_per_trade > max_buying_power
system start invalid_config.json
# Result: ValueError with validation error
```

### ✅ Stream Startup Failure
```bash
# Config references non-existent symbol or API unavailable
system start config_with_bad_symbol.json
# Result: Exception, all streams stopped, system remains STOPPED
```

## Benefits Achieved

1. **✅ Explicit Configuration** - No hidden defaults or assumptions
2. **✅ Validation** - All parameters validated before use
3. **✅ Safety** - System can't run without proper configuration
4. **✅ Traceability** - Configuration files can be version controlled
5. **✅ Flexibility** - Easy to create different session profiles
6. **✅ Risk Management** - Position limits enforced from config
7. **✅ Clear Errors** - Detailed error messages for all failure modes
8. **✅ Atomic Startup** - Streams started before state transition
9. **✅ Clean Shutdown** - All streams stopped on system stop
10. **✅ Audit Trail** - Metadata tracks strategy and parameters

## Breaking Changes

### Code Impact
- Any code calling `system_mgr.start()` must be updated
- Must now provide configuration file path
- Must use (async)

### Migration Required
```python
# OLD
system_mgr.start()

# NEW
system_mgr.start("session_configs/my_session.json")
```

### CLI Impact
- Command `system start` now requires argument
- Users must specify configuration file

## Next Steps

### Recommended Actions
1. Create session configurations for different strategies
2. Test configurations in paper trading mode
3. Version control session configs
4. Document strategy-specific configurations
5. Create configuration templates for common patterns

### Future Enhancements
1. Configuration schema validation (JSON Schema)
2. Configuration builder CLI tool
3. Configuration import/export utilities
4. Configuration diff/compare tool
5. Hot-reload configuration changes
6. Configuration profiles manager

## Summary

✅ **All requirements met**  
✅ **Strict validation enforced**  
✅ **No defaults or fallbacks**  
✅ **Streams started before RUNNING**  
✅ **Complete session configuration**  
✅ **Clear error handling**  
✅ **Comprehensive documentation**  
✅ **Example configuration provided**  

The system now requires explicit, validated configuration for all trading sessions, ensuring safer and more predictable operations with full control over risk parameters and data streams.
