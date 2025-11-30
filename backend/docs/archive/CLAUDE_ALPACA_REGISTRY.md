# Claude AI & Alpaca Commands: Registry Migration

## Overview

Added **Claude AI** and **Alpaca** commands to the command registry system, completing the migration of all major command categories to use registry-based metadata.

## New Registries Created

### 1. CLAUDE_COMMANDS Registry

**Commands Added:**
- `ask <question>` - Ask Claude a question
- `analyze <symbol>` - Analyze a stock with Claude AI
- `claude status` - Check Claude API configuration
- `claude usage` - View Claude API usage and costs
- `claude history` - View recent Claude API usage history

**Registry Definition:**
```python
@dataclass(frozen=True)
class ClaudeCommandMeta:
    """Metadata for Claude AI integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]

CLAUDE_COMMANDS: List[ClaudeCommandMeta] = [
    ClaudeCommandMeta(
        name="ask",
        usage="ask <question>",
        description="Ask Claude a question",
        examples=["ask What is the current market trend?", "ask Explain options trading"],
    ),
    # ... 4 more commands
]
```

### 2. ALPACA_COMMANDS Registry

**Commands Added:**
- `alpaca connect` - Test Alpaca API connectivity
- `alpaca disconnect` - Show how to logically disconnect Alpaca

**Registry Definition:**
```python
@dataclass(frozen=True)
class AlpacaCommandMeta:
    """Metadata for Alpaca integration commands."""
    name: str
    usage: str
    description: str
    examples: List[str]

ALPACA_COMMANDS: List[AlpacaCommandMeta] = [
    AlpacaCommandMeta(
        name="connect",
        usage="alpaca connect",
        description="Test Alpaca API connectivity",
        examples=["alpaca connect"],
    ),
    AlpacaCommandMeta(
        name="disconnect",
        usage="alpaca disconnect",
        description="Show how to logically disconnect Alpaca",
        examples=["alpaca disconnect"],
    ),
]
```

## Changes Made

### 1. Command Registry (`command_registry.py`)

**Added:**
- `ClaudeCommandMeta` dataclass
- `CLAUDE_COMMANDS` registry with 5 commands
- `AlpacaCommandMeta` dataclass
- `ALPACA_COMMANDS` registry with 2 commands

**Lines Added:** ~75 lines

### 2. Interactive CLI (`interactive.py`)

#### Imports Updated
```python
from app.cli.command_registry import (
    # ... existing imports ...
    CLAUDE_COMMANDS,    # ← NEW
    ALPACA_COMMANDS,    # ← NEW
)
```

#### CommandCompleter Updated
```python
# Before
self.commands.extend(['claude', 'ask', 'analyze', 'alpaca', ...])  # ❌ Hardcoded
self.claude_commands = ['ask', 'analyze', 'status', 'usage', 'llm-history']  # ❌ Hardcoded

# After
self.commands.extend(['claude', 'alpaca'])  # ✅ Namespaces from structure
self.commands.extend(['ask', 'analyze'])    # ✅ Standalone commands
self.claude_commands = [meta.name for meta in CLAUDE_COMMANDS]  # ✅ From registry
self.alpaca_commands = [meta.name for meta in ALPACA_COMMANDS]  # ✅ From registry
```

#### Help Display Updated
```python
# Before
table.add_row("ask <question>", "Ask Claude a question")  # ❌ Hardcoded
table.add_row("analyze <symbol>", "Analyze a stock with Claude AI")  # ❌ Hardcoded
# ... 5 more hardcoded lines

# After
for meta in CLAUDE_COMMANDS:
    table.add_row(meta.usage, meta.description)  # ✅ From registry
```

#### Error Messages Updated

**Claude Commands:**
```python
# Before
else:
    self.console.print("[red]Usage: ask <your question>[/red]")  # ❌ Hardcoded

# After
else:
    cmd_meta = next((m for m in CLAUDE_COMMANDS if m.name == 'ask'), None)
    usage = cmd_meta.usage if cmd_meta else "ask <question>"
    self.console.print(f"[red]Usage: {usage}[/red]")  # ✅ From registry
```

**Alpaca Commands:**
```python
# Before
else:
    self.console.print(f"[red]Unknown alpaca command: {subcmd}[/red]")
    self.console.print("[dim]Try: alpaca connect or alpaca disconnect[/dim]")  # ❌ Hardcoded

# After
else:
    self.console.print("[red]Unknown alpaca command. Available commands:[/red]\n")
    for meta in ALPACA_COMMANDS:
        self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")  # ✅ From registry
```

## Command Organization

### Standalone Commands (Direct Access)
- `ask <question>` - Direct shortcut to Claude AI
- `analyze <symbol>` - Direct shortcut to Claude AI analysis

### Namespaced Commands
- `claude status` - Claude API status
- `claude usage` - Claude API usage stats
- `claude history` - Claude API usage history
- `alpaca connect` - Test Alpaca connection
- `alpaca disconnect` - Disconnect instructions

**Rationale:** `ask` and `analyze` are frequently used, so they get direct shortcuts while administrative commands (`status`, `usage`, `history`) are namespaced under `claude`.

## Benefits Achieved

### 1. Single Source of Truth ✅
- Claude command metadata in one place
- Alpaca command metadata in one place
- No duplicate usage strings

### 2. Auto-Generated Help ✅
```bash
system@mismartera: help
# Claude AI section now auto-generated from CLAUDE_COMMANDS registry
# Alpaca section now auto-generated from ALPACA_COMMANDS registry
```

### 3. Auto-Updated Error Messages ✅
```bash
system@mismartera: claude invalid
# Shows all commands from CLAUDE_COMMANDS registry
# Add new command → error message updates automatically
```

### 4. Consistent Tab Completion ✅
```bash
system@mismartera: clau<TAB>
# Completes to 'claude' (from registry)
system@mismartera: claude <TAB>
# Shows: status, usage, history (from registry)
```

## Example Outputs

### Help Display (Auto-Generated)

```
┌─────────────────────────────────────────────────────────┬─────────────────────────────────┐
│ CLAUDE AI COMMANDS                                      │                                 │
├─────────────────────────────────────────────────────────┼─────────────────────────────────┤
│ ask <question>                                          │ Ask Claude a question           │
│ analyze <symbol>                                        │ Analyze a stock with Claude AI  │
│ claude status                                           │ Check Claude API configuration  │
│ claude usage                                            │ View your Claude API usage and  │
│                                                         │ costs                           │
│ claude history                                          │ View recent Claude API usage    │
│                                                         │ history                         │
├─────────────────────────────────────────────────────────┼─────────────────────────────────┤
│ ALPACA COMMANDS                                         │                                 │
├─────────────────────────────────────────────────────────┼─────────────────────────────────┤
│ alpaca connect                                          │ Test Alpaca API connectivity    │
│ alpaca disconnect                                       │ Show how to logically           │
│                                                         │ disconnect Alpaca               │
└─────────────────────────────────────────────────────────┴─────────────────────────────────┘
```

### Error Message (Registry-Based)

```bash
system@mismartera: claude invalid
Unknown claude command. Available commands:

  ask <question>                           Ask Claude a question
  analyze <symbol>                         Analyze a stock with Claude AI
  claude status                            Check Claude API configuration
  claude usage                             View your Claude API usage and costs
  claude history                           View recent Claude API usage history
```

### Usage Error (Registry-Based)

```bash
system@mismartera: ask
Usage: ask <question>

system@mismartera: alpaca
Usage: alpaca <connect | disconnect>
```

## Complete Registry Coverage

| Command Category | Registry | Help | Completion | Error Messages |
|------------------|----------|------|------------|----------------|
| General | ✅ GENERAL_COMMANDS | ✅ | ✅ | ✅ |
| Admin | ✅ ADMIN_COMMANDS | ✅ | ✅ | ✅ |
| System | ✅ SYSTEM_COMMANDS | ✅ | ✅ | ✅ |
| Data | ✅ DATA_COMMANDS | ✅ | ✅ | ✅ |
| Market | ✅ MARKET_COMMANDS | ✅ | ✅ | ✅ |
| Holiday | ✅ HOLIDAY_COMMANDS | ✅ | ✅ | ✅ |
| **Claude AI** | ✅ CLAUDE_COMMANDS | ✅ | ✅ | ✅ **NEW** |
| **Alpaca** | ✅ ALPACA_COMMANDS | ✅ | ✅ | ✅ **NEW** |

**Only Remaining (Not Critical):**
- Account commands (account info, balance, positions)
- Trading commands (quote, buy, sell, orders)

## Testing

### Test Claude Commands
```bash
# Valid commands
ask What is the market doing today?
analyze AAPL
claude status
claude usage
claude history

# Invalid command
claude invalid
# Should show all commands from registry

# No arguments
ask
# Should show usage from registry
```

### Test Alpaca Commands
```bash
# Valid commands
alpaca connect
alpaca disconnect

# Invalid command
alpaca invalid
# Should show all commands from registry

# No arguments
alpaca
# Should show usage from registry
```

## Files Modified

1. **`app/cli/command_registry.py`** (+75 lines)
   - Added `ClaudeCommandMeta` and `CLAUDE_COMMANDS`
   - Added `AlpacaCommandMeta` and `ALPACA_COMMANDS`

2. **`app/cli/interactive.py`** (modified)
   - Imported new registries
   - Updated `CommandCompleter` to use registries
   - Updated `show_help()` to auto-generate from registries
   - Updated error messages to reference registries
   - Added section markers for Claude and Alpaca commands

3. **`COMMAND_REGISTRY_REFACTOR.md`** (updated)
   - Added Claude and Alpaca to "Fully Migrated" list
   - Updated migration status

## Summary

✅ **Claude AI commands** now fully use command registry  
✅ **Alpaca commands** now fully use command registry  
✅ **Auto-generated help** for both command categories  
✅ **Registry-based error messages** for better consistency  
✅ **Tab completion** auto-populated from registries  
✅ **8 out of 10** command categories now fully registry-based  

All major command subsystems now follow the same registry pattern! 🎉
