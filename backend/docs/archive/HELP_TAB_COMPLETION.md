# Help Command with Tab Completion

## Overview
The `help` command now supports intelligent tab completion that suggests namespaces and commands as you type.

## Tab Completion Behavior

### Level 1: Namespace Suggestions
When typing `help <TAB>`, you'll see available namespaces:
```bash
system@mismartera: help <TAB>
admin      alpaca     claude     data       execution  
general    market     schwab     system     time
```

### Level 2: Command Suggestions
When typing `help <namespace> <TAB>`, you'll see commands in that namespace:
```bash
system@mismartera: help time <TAB>
advance          current          holidays         list-groups      session
backtest-window  days             holidays delete  market           
config           exchange         import-holidays  next             reset

system@mismartera: help data <TAB>
api               delete-all        import-api        list              session-high-low
avg-volume        export-csv        import-file       quality           session-volume
backtest-speed    high-low          info              session           snapshot
backtest-window   import            latest-bar        session-high-low  stop-all-streams
bars              import-api        latest-quote      stream-bars       ticks
delete            import-file       latest-tick       stream-quotes     validate
                                                     stream-ticks
```

### Level 3: Command Detail (with Examples)
```bash
help <namespace> <command>
```

**Examples**:
```bash
help data import-api        # Detailed help for data import-api
help time holidays import   # Detailed help for time holidays import
help system start           # Detailed help for system start
help data session           # Detailed help for data session
help time holidays          # Shows holidays command + related commands
help time holidays delete   # Multi-word command support!
help time holidays import   # Multi-word command support!
```

**Output**:
- Full command usage syntax
- Detailed description
- Multiple usage examples
- **Related commands** (if any commands share the same prefix)

### Multi-Word Command Support

The help system now intelligently handles multi-word commands:

```bash
$ help time holidays

Command: time holidays [--year <year>] [--exchange <exch>]
Description: List holidays for a year

Examples:
  $ time holidays
  $ time holidays --year 2024
  $ time holidays --year 2025 --exchange NASDAQ

Related commands:
  time holidays delete - Delete holidays for a specific year and exchange
  time holidays import - Import holidays from JSON/CSV file

Tip: Use 'help time <command>' to see details
```

When you look up a command, the help system shows related commands that start with the same prefix!

## Usage Examples

### Exploring Time Commands
```bash
# Start typing and tab complete
system@mismartera: help ti<TAB>
system@mismartera: help time <TAB>
# Shows: advance, backtest-window, config, current, days, exchange, holidays, etc.

system@mismartera: help time hol<TAB>
# Shows both: holidays, holidays delete

system@mismartera: help time holidays<TAB>
# Completes to: help time holidays 
# Or shows: holidays, holidays delete

system@mismartera: help time holidays <ENTER>

Command: time holidays [--year <year>] [--exchange <exch>]
Description: List holidays for a year
...
Related commands:
  time holidays delete - Delete holidays for year

# For multi-word command:
system@mismartera: help time holidays delete <ENTER>

Command: time holidays delete <year> [--exchange <exch>]
Description: Delete holidays for a specific year and exchange
...
```

### Exploring Data Commands
```bash
system@mismartera: help data <TAB>
# Shows all data commands

system@mismartera: help data import-<TAB>
# Shows: import-api, import-file

system@mismartera: help data import-api <ENTER>

Command: data import-api <type> <symbol> <start> <end>
Description: Import data from external API via DataManager (1m, tick, quote)

Examples:
  $ data import-api 1m AAPL 2025-11-01 2025-11-19
```

## Implementation Details

### File Modified
- `/app/cli/interactive.py` - Added help completion logic in `CommandCompleter.complete()`

### How It Works
1. **Detects `help` command**: When first word is "help"
2. **Level 1 (namespaces)**: If only 1 word typed, suggests namespace list
3. **Level 2 (commands)**: If 2 words typed (`help <namespace>`), suggests commands from that namespace's registry
4. **Filtering**: Matches are filtered by what user has typed so far

### Namespace-to-Registry Mapping
```python
'data' → DATA_COMMANDS
'time' → TIME_COMMANDS
'system' → SYSTEM_COMMANDS
'execution' → EXECUTION_COMMANDS
'claude' → CLAUDE_COMMANDS
'alpaca' → ALPACA_COMMANDS
'schwab' → SCHWAB_COMMANDS
'market' → MARKET_COMMANDS
'general' → GENERAL_COMMANDS
'admin' → ADMIN_COMMANDS
```

## Benefits

1. **Discoverability**: Tab completion helps users find commands without memorizing
2. **Speed**: Quickly navigate to the help you need
3. **Accuracy**: Reduces typos by auto-completing command names
4. **Progressive Learning**: Start with broad namespace, drill down to specific commands
5. **Consistency**: Uses same command registries as the actual help system

## Bug Fixes

- Fixed `HOLIDAY_COMMANDS` error by clearing Python bytecode cache
- Removed all references to old holiday command namespace
- Cleaned up `.pyc` files and `__pycache__` directories

## Testing

Verified working with:
```bash
./start_cli.sh
system@mismartera: help <TAB>
system@mismartera: help time <TAB>
system@mismartera: help time holidays <ENTER>
```

All three levels work correctly with proper tab completion!
