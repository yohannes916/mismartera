# Default Configuration File for System Start

## Overview

The `system start` command now uses a **default configuration file** when no file is specified, making it easier to quickly start the system for testing and development.

## What Changed

### Before (Explicit File Required)
```bash
system start session_configs/example_session.json  # ✅ Required
system start                                       # ❌ Error: Configuration file path required
```

### After (Optional File with Default)
```bash
system start session_configs/example_session.json  # ✅ Uses specified file
system start                                       # ✅ Uses default: session_configs/example_session.json
```

## Default Configuration File

**Path**: `session_configs/example_session.json`

**Why This File?**
- Ready-to-use example configuration
- Includes backtest mode with reasonable defaults
- Multiple symbols and stream types for testing
- Well-documented with comments in metadata

## Usage Examples

### Quick Start (Default Config)
```bash
# Simply run with no arguments - uses default config
system start
```

**Output:**
```
Starting system with default configuration: session_configs/example_session.json
...
System started successfully!
  Session: Example Trading Session
  Mode: BACKTEST
  Backtest Window: 2024-11-01 to 2024-11-22
  ...
```

### Custom Config
```bash
# Specify a different config file
system start session_configs/my_custom_config.json
```

**Output:**
```
Starting system with configuration: session_configs/my_custom_config.json
...
```

### Relative Path
```bash
# Use relative path
system start ./my_config.json
```

### Absolute Path
```bash
# Use absolute path
system start /home/user/trading/configs/live_session.json
```

## When to Use Default vs Custom

### Use Default When:
- ✅ Quick testing during development
- ✅ Learning the system
- ✅ Running examples from documentation
- ✅ Verifying system functionality
- ✅ Default backtest window is acceptable

### Use Custom Config When:
- ✅ Running specific strategies
- ✅ Live trading sessions
- ✅ Different backtest time periods
- ✅ Custom symbol lists
- ✅ Different risk parameters
- ✅ Production deployments

## Implementation Details

### CLI Handler
```python
# In interactive.py
if subcmd == 'start':
    # Use default config if not provided
    config_path = args[1] if len(args) >= 2 else "session_configs/example_session.json"
    await start_command(config_path)
```

### Command Registry
```python
SystemCommandMeta(
    name="start",
    usage="system start [config_file]",  # ← [config_file] indicates optional
    description="Start the system run (defaults to example_session.json)",
    examples=["system start", "system start session_configs/my_config.json"],
)
```

### Visual Feedback
The CLI shows different messages for default vs custom configs:

**Default:**
```
Starting system with default configuration: session_configs/example_session.json
```

**Custom:**
```
Starting system with configuration: session_configs/my_custom_config.json
```

## File Validation

Even with the default, all validation still applies:

1. ✅ **File must exist** - Even the default file must be present
2. ✅ **Must be valid JSON** - Syntax errors will be caught
3. ✅ **Must pass validation** - All configuration rules apply
4. ✅ **Strict error handling** - Same error handling as custom files

If the default file is missing or invalid:
```
✗ Configuration file not found
Configuration file not found: session_configs/example_session.json
Absolute path: /home/user/mismartera/backend/session_configs/example_session.json
Please provide a valid path to a session configuration file.
```

## Benefits

### 1. **Faster Development Workflow**
```bash
# Before: Type full path every time
system start session_configs/example_session.json

# After: Quick start
system start
```

### 2. **Easier for Beginners**
New users can start the system immediately without needing to know file paths.

### 3. **Better Documentation**
Documentation can show simpler examples:
```bash
# Quick start
system start

# Custom start
system start my_config.json
```

### 4. **Testing Convenience**
During development and testing, faster iterations:
```bash
system start    # Quick test with defaults
system stop
system start    # Test again
```

### 5. **Still Explicit When Needed**
Production and custom scenarios still specify exact files:
```bash
system start production/live_trading_v2.json
```

## Best Practices

### 1. Keep Default Config Working
Always ensure `session_configs/example_session.json`:
- ✅ Exists in the repository
- ✅ Has valid JSON syntax
- ✅ Passes all validation
- ✅ Uses reasonable defaults
- ✅ Works in backtest mode (safer for default)

### 2. Use Custom Configs for Production
```bash
# Development/Testing
system start

# Production
system start production/live_trading_strategy_a.json
```

### 3. Document Custom Configs
When creating custom configs, document them:
```json
"metadata": {
  "description": "Production config for Strategy A",
  "notes": "Uses live mode with real capital",
  "last_updated": "2024-11-22"
}
```

### 4. Version Control Configs
Keep all configs in version control:
```
session_configs/
├── example_session.json      ← Default
├── live/
│   ├── strategy_a.json
│   └── strategy_b.json
└── backtest/
    ├── 2024_q4.json
    └── test_strategy.json
```

## Help Display

The help command now shows the optional nature:

```bash
system@mismartera: help

System Management:
  system start [config_file]     Start the system run (defaults to example_session.json)
  system pause                   Pause the system run
  system stop                    Stop the system run
  ...
```

## Scripting Support

The default config works great in scripts:

**startup_script.txt:**
```bash
clear
system start              # Uses default - quick and easy
system status
```

**custom_script.txt:**
```bash
clear
system start production/my_strategy.json  # Custom for this script
system status
```

## Error Messages

All error messages remain the same - whether using default or custom config:

**Missing File:**
```
✗ Configuration file not found
Configuration file not found: session_configs/example_session.json
```

**Invalid JSON:**
```
✗ Configuration validation error
Configuration file contains invalid JSON: session_configs/example_session.json
```

**Validation Error:**
```
✗ Configuration validation error
Configuration validation failed: session_configs/example_session.json
Error: Invalid mode: invalid. Must be one of ['live', 'backtest']
```

## Files Modified

### 1. Interactive CLI (`app/cli/interactive.py`)
```python
# Use default config if not provided
config_path = args[1] if len(args) >= 2 else "session_configs/example_session.json"
```

### 2. System Commands (`app/cli/system_commands.py`)
```python
# Show which config is being used
if config_file_path == "session_configs/example_session.json":
    console.print(f"Starting system with default configuration: {config_file_path}")
```

### 3. Command Registry (`app/cli/command_registry.py`)
```python
usage="system start [config_file]",  # [config_file] indicates optional
description="Start the system run (defaults to example_session.json)",
examples=["system start", "system start session_configs/my_config.json"],
```

## Migration

No breaking changes! Existing usage still works:

```bash
# This still works exactly as before
system start session_configs/my_config.json

# This is new and convenient
system start
```

## Summary

✅ **Default config file** for quick starts  
✅ **Optional file path** parameter  
✅ **Clear visual feedback** for default vs custom  
✅ **Same validation** for all configs  
✅ **Backward compatible** - existing usage works  
✅ **Faster development** workflow  
✅ **Easier for beginners** to get started  

The system start command is now more convenient while maintaining all safety and validation!
