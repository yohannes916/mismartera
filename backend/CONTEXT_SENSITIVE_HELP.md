# Context-Sensitive Help System

## Overview

Enhanced help system that provides three levels of detail:
1. **General help** - Shows all available commands
2. **Namespace help** - Shows commands in a specific namespace
3. **Command detail** - Shows detailed usage and examples for a specific command

## Usage

### Level 1: General Help (All Commands)
```bash
help
```
Shows all commands grouped by namespace with brief descriptions.

**Output includes**:
- General commands (help, history, status, etc.)
- Admin commands (log-level, sessions, etc.)
- System management (system start/stop/pause/resume)
- Data commands (data list/import/export/stream)
- Market commands (market status)
- Time commands (time current/session/holidays)
- Claude AI commands
- Alpaca/Schwab integration commands
- Execution/Trading commands

### Level 2: Namespace Help
```bash
help <namespace>
```

**Examples**:
```bash
help data         # Show all data commands
help time         # Show all time commands
help system       # Show all system commands
help execution    # Show all execution commands
help claude       # Show all claude commands
```

**Output**: Focused table showing only commands in that namespace.

### Level 3: Command Detail (with Examples)
```bash
help <namespace> <command>
```

**Examples**:
```bash
help data import-api       # Detailed help for data import-api
help time import-holidays  # Detailed help for time import-holidays
help system start          # Detailed help for system start
help data session          # Detailed help for data session
```

**Output**:
- Full command usage syntax
- Detailed description
- Multiple usage examples

## Implementation

### Files Modified
- `/app/cli/interactive.py` - Enhanced `show_help()` method
- `/app/cli/command_registry.py` - Updated help command metadata

### Key Features
1. **Auto-discovery**: Uses command registries as single source of truth
2. **Smart matching**: Finds commands by name within namespace
3. **Helpful errors**: Suggests available commands if not found
4. **Progressive disclosure**: Shows tips for deeper help at each level

### Command Registry Structure
Each command in the registry includes:
- `name` - Command identifier
- `usage` - Full usage syntax
- `description` - Brief description
- `examples` - List of usage examples (shown in Level 3 help)

## Example Session

```bash
# Get overview of all commands
$ help

# Focus on data commands only
$ help data

# Get detailed examples for specific command
$ help data import-api

Command: data import-api <type> <symbol> <start> <end>
Description: Import data from external API via DataManager (1m, tick, quote)

Examples:
  $ data import-api 1m AAPL 2025-11-01 2025-11-19

# Get time command details
$ help time import-holidays

Command: time import-holidays <file> [--exchange <group>] [--dry-run]
Description: Import holidays from JSON/CSV file (auto-uses configured exchange's group)

Examples:
  $ time import-holidays data/holidays/us_equity_2024.json
  $ time import-holidays holidays.csv --exchange US_EQUITY
  $ time import-holidays holidays.json --dry-run
```

## Available Namespaces

- `general` - Basic CLI commands
- `admin` - Administrative commands
- `system` - System management
- `data` - Market data operations
- `market` - Market status queries
- `time` - Time/calendar operations
- `claude` - Claude AI integration
- `alpaca` - Alpaca broker integration
- `schwab` - Schwab broker integration
- `execution` - Order execution/trading

## Benefits

1. **Discoverability**: Users can easily explore commands at their own pace
2. **Context**: Focus on relevant commands without information overload
3. **Examples**: Concrete usage examples for every command
4. **Consistency**: All help generated from same command registry
5. **Maintainability**: Update registry once, help updates everywhere
