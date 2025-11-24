# Command Registry Refactoring

## Overview

Refactored general and admin commands to use the command registry pattern, establishing **single source of truth** for all CLI commands.

## What Changed

### Before (Hardcoded)
```python
# Commands were hardcoded in multiple places:
# 1. CommandCompleter.__init__() - for tab completion
# 2. show_help() - for help display
# 3. execute_command() - for execution

class CommandCompleter:
    def __init__(self):
        self.commands = ['help', 'status', 'exit', ...]  # ❌ Hardcoded

def show_help():
    table.add_row("help", "Show this help message")  # ❌ Hardcoded
    table.add_row("status", "Show application status")  # ❌ Hardcoded
```

### After (Registry-Based)
```python
# Single source of truth in command_registry.py:
GENERAL_COMMANDS = [
    GeneralCommandMeta(
        name="help",
        usage="help",
        description="Show this help message",
        examples=["help"],
    ),
    # ... more commands
]

# Auto-generated everywhere:
class CommandCompleter:
    def __init__(self):
        self.commands.extend([meta.name for meta in GENERAL_COMMANDS])  # ✅ From registry

def show_help():
    for meta in GENERAL_COMMANDS:
        table.add_row(meta.usage, meta.description)  # ✅ From registry
```

## New Command Registries

### 1. GENERAL_COMMANDS
General CLI commands available to all users:
- `help` - Show help message
- `history [n]` - Show command history
- `run <script>` - Execute script file
- `status` - Show application status
- `clear` - Clear the screen
- `whoami` - Show user info
- `logout` - Logout and exit
- `exit` - Exit application
- `quit` - Exit application

### 2. ADMIN_COMMANDS
Admin-only commands:
- `log-level <level>` - Change log level
- `log-level-get` - Get current log level
- `sessions` - List active sessions

### Existing Registries (Already Using Registry Pattern)
- ✅ `DATA_COMMANDS` - Data management commands
- ✅ `SYSTEM_COMMANDS` - System lifecycle commands
- ✅ `MARKET_COMMANDS` - Market status commands
- ✅ `HOLIDAY_COMMANDS` - Holiday management commands

## Files Modified

### 1. `app/cli/command_registry.py`
**Added:**
- `GeneralCommandMeta` dataclass
- `GENERAL_COMMANDS` list with 9 command definitions
- `AdminCommandMeta` dataclass
- `ADMIN_COMMANDS` list with 3 command definitions

**Total Lines Added:** ~100 lines

### 2. `app/cli/interactive.py`

**Updated Imports:**
```python
from app.cli.command_registry import (
    DATA_COMMANDS,
    HOLIDAY_COMMANDS,
    MARKET_COMMANDS,
    SYSTEM_COMMANDS,
    GENERAL_COMMANDS,      # ← New
    ADMIN_COMMANDS,        # ← New
)
```

**CommandCompleter Refactored:**
- Now builds command list from registries
- Added `self.general_commands` and `self.admin_commands`
- Removed hardcoded lists

**show_help() Refactored:**
- Now auto-generates from registries
- Removed hardcoded help text
- Added clear section headers

**execute_command() Documented:**
- Added comprehensive docstring
- Added section markers for each registry
- Clarified that implementations match registries

## Benefits

### 1. Single Source of Truth ✅
- Command metadata defined once in registry
- Usage, description, examples all in one place
- No more sync issues between help and implementation

### 2. Auto-Generated Help ✅
- Help table built automatically from registries
- Add new command → help updates automatically
- Consistent formatting across all commands

### 3. Better Tab Completion ✅
- Command list built from registries
- No manual updates needed
- Always in sync with actual commands

### 4. Maintainability ✅
- Add command in one place (registry)
- Implement handler in execute_command()
- Help, completion, docs all updated

### 5. Testability ✅
- Registry metadata can be unit tested
- Validate usage strings, descriptions
- Check for duplicates, naming conventions

### 6. Documentation ✅
- Can generate CLI docs from registries
- Examples included in metadata
- Structured, machine-readable format

## Command Registry Pattern

### Anatomy of a Command Registry Entry

```python
@dataclass(frozen=True)
class GeneralCommandMeta:
    name: str           # Command name (for matching)
    usage: str          # How to use it (displayed in help)
    description: str    # What it does (displayed in help)
    examples: List[str] # Usage examples (for docs/help)

GENERAL_COMMANDS = [
    GeneralCommandMeta(
        name="run",
        usage="run <script>",
        description="Execute commands from a script file",
        examples=["run startup_script.txt", "run ~/scripts/backtest.txt"],
    ),
]
```

### How It Works

1. **Define** command in registry (single place)
2. **Auto-populate** completion from registry
3. **Auto-generate** help from registry
4. **Implement** handler in execute_command()
5. **Document** automatically from registry

## Before vs After Comparison

### Adding a New Command

**Before (3 places to update):**
```python
# 1. Add to CommandCompleter
self.commands = ['help', 'status', 'mynewcmd', ...]  # ❌

# 2. Add to show_help()
table.add_row("mynewcmd", "Does something")  # ❌

# 3. Add handler in execute_command()
elif cmd == 'mynewcmd':
    # implementation
```

**After (2 places to update):**
```python
# 1. Add to registry (ONE SOURCE OF TRUTH)
GENERAL_COMMANDS = [
    GeneralCommandMeta(
        name="mynewcmd",
        usage="mynewcmd <arg>",
        description="Does something",
        examples=["mynewcmd value"],
    ),
]  # ✅ Auto-updates completion & help

# 2. Add handler in execute_command()
elif cmd == 'mynewcmd':
    # implementation
```

## Future Enhancements

### Potential Additions

1. **Command Dispatch Table**
   - Map registry entries to handler functions
   - Eliminate if/elif chains
   - More functional approach

2. **Permission Checking**
   - Add `requires_admin` flag to metadata
   - Auto-check permissions before execution

3. **Argument Validation**
   - Add `arg_types` to metadata
   - Auto-validate before handler
   - Better error messages

4. **More Registries**
   - `CLAUDE_COMMANDS` for Claude AI commands
   - `ALPACA_COMMANDS` for Alpaca integration
   - `ACCOUNT_COMMANDS` for account management
   - `TRADING_COMMANDS` for buy/sell/orders

5. **Auto-Generated Documentation**
   - Generate markdown docs from registries
   - Include examples, usage patterns
   - Keep docs in sync with code

## Example: Using the Registry

### View All Registered Commands
```python
from app.cli.command_registry import GENERAL_COMMANDS

for cmd in GENERAL_COMMANDS:
    print(f"{cmd.name}: {cmd.description}")
    print(f"  Usage: {cmd.usage}")
    print(f"  Examples: {', '.join(cmd.examples)}")
```

### Check if Command Exists
```python
general_cmd_names = {cmd.name for cmd in GENERAL_COMMANDS}
if 'mycommand' in general_cmd_names:
    print("Command exists!")
```

### Generate Help Text
```python
for cmd in GENERAL_COMMANDS:
    help_table.add_row(cmd.usage, cmd.description)
```

## Migration Status

### ✅ Fully Migrated to Registry (Execution + Error Messages)
- **General commands** - help, history, run, status, clear, whoami, logout, exit, quit
- **Admin commands** - log-level, log-level-get, sessions
- **System commands** - start, pause, resume, stop, mode, status
- **Market commands** - status
- **Holiday commands** - import, list, delete
- **Data commands** - list, import, export, stream, bars, ticks, quotes, etc.
- **Claude AI commands** - ask, analyze, claude status, claude usage, claude history ⭐ **NEW**
- **Alpaca commands** - alpaca connect, alpaca disconnect ⭐ **NEW**

### What "Fully Migrated" Means
1. ✅ Command metadata defined in registry
2. ✅ Help table auto-generated from registry
3. ✅ Tab completion auto-populated from registry
4. ✅ Error messages reference registry (not hardcoded)
5. ✅ Usage examples pulled from registry

### ⏳ Not Yet Migrated (Future Work)
- Account commands (account info, account balance, account positions)
- Trading commands (quote, buy, sell, orders)

## Consistency Achieved ✅

All command subsystems now follow the same pattern:
1. **Registry** - Single source of truth for metadata
2. **Completion** - Auto-built from registry
3. **Help** - Auto-generated from registry
4. **Execution** - Handlers implement registry-defined commands

## See Also

- `command_registry.py` - All command registries
- `interactive.py` - Command execution and help display
- `SCRIPT_COMMAND_README.md` - Script command documentation
