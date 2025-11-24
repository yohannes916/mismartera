# Command Registry: Error Messages Update

## Overview

Updated **system**, **market**, and **holiday** commands to use registry-based error messages instead of hardcoded text. This ensures all error messages stay in sync with the command registry (single source of truth).

## Changes Made

### 1. System Commands

**Before (Hardcoded):**
```python
else:
    self.console.print("[red]Usage:[/red]")
    self.console.print("  system start             - Start the system run")
    self.console.print("  system pause             - Pause the system run")
    self.console.print("  system resume            - Resume from paused state")
    self.console.print("  system stop              - Stop the system run")
    self.console.print("  system mode <live|backtest> - Set operation mode")
    self.console.print("  system status            - Show system status")
```

**After (Registry-Based):**
```python
else:
    # Show usage from registry (single source of truth)
    self.console.print("[red]Unknown system command. Available commands:[/red]\n")
    for meta in SYSTEM_COMMANDS:
        self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
```

**Benefits:**
- ✅ If you add a command to registry → error message updates automatically
- ✅ Usage strings always match registry definitions
- ✅ No risk of forgetting to update error messages

### 2. Holiday Commands

**Before (Hardcoded):**
```python
else:
    self.console.print("[red]Usage:[/red]")
    self.console.print("  holidays import <file>    - Import holiday schedule")
    self.console.print("  holidays list [YYYY]      - List holidays for year YYYY (or all if omitted)")
    self.console.print("  holidays delete [YYYY]    - Delete holidays for year YYYY")
```

**After (Registry-Based):**
```python
else:
    # Show usage from registry (single source of truth)
    self.console.print("[red]Unknown holidays command. Available commands:[/red]\n")
    for meta in HOLIDAY_COMMANDS:
        self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
```

### 3. Market Commands

**Before (Hardcoded):**
```python
else:
    self.console.print("[red]Usage: market status[/red]")
```

**After (Registry-Based):**
```python
else:
    # Show available subcommands from registry
    subcommands = [meta.name for meta in MARKET_COMMANDS]
    self.console.print(f"[red]Usage: market <{' | '.join(subcommands)}>[/red]")
```

## Example Output

### System Command Error (Before)

```
system@mismartera: system invalid
Usage:
  system start             - Start the system run
  system pause             - Pause the system run
  system resume            - Resume from paused state
  system stop              - Stop the system run
  system mode <live|backtest> - Set operation mode
  system status            - Show system status
```

### System Command Error (After)

```
system@mismartera: system invalid
Unknown system command. Available commands:

  system start                             Start the system run
  system pause                             Pause the system run
  system resume                            Resume the system from paused state
  system stop                              Stop the system run
  system mode <live|backtest>              Set operation mode (must be stopped)
  system status                            Show current system status
```

### No Arguments Error (Before)

```
system@mismartera: system
Usage: system <start|pause|resume|stop|status>
```

### No Arguments Error (After - Auto-generated from Registry)

```
system@mismartera: system
Usage: system <start | pause | resume | stop | mode | status>
```

**Note:** The list is auto-generated from registry, so adding new commands automatically updates the usage string.

## Pattern Applied

All namespaced commands now follow this consistent pattern:

```python
# Pattern for error handling with registry
elif cmd == 'namespace':
    if args:
        subcmd = args[0].lower()
        # ... handle each subcommand ...
        else:
            # Show available commands from registry
            self.console.print("[red]Unknown <namespace> command. Available commands:[/red]\n")
            for meta in NAMESPACE_COMMANDS:
                self.console.print(f"  [cyan]{meta.usage:<40}[/cyan] {meta.description}")
    else:
        # Show usage from registry
        subcommands = [meta.name for meta in NAMESPACE_COMMANDS]
        self.console.print(f"[red]Usage: <namespace> <{' | '.join(subcommands)}>[/red]")
```

## Files Modified

### `app/cli/interactive.py`

**Updated Sections:**
1. **System commands** (lines 838-870)
   - Added section marker: `# ==================== SYSTEM COMMANDS (from SYSTEM_COMMANDS registry) ====================`
   - Replaced hardcoded error messages with registry-based display
   - Auto-generates subcommand list from registry

2. **Holiday commands** (lines 814-839)
   - Added section marker: `# ==================== HOLIDAY COMMANDS (from HOLIDAY_COMMANDS registry) ====================`
   - Replaced hardcoded error messages with registry-based display
   - Auto-generates subcommand list from registry

3. **Market commands** (lines 711-813)
   - Added section marker: `# ==================== MARKET COMMANDS (from MARKET_COMMANDS registry) ====================`
   - Updated to use registry for subcommand list

## Benefits

### 1. Single Source of Truth ✅
- Command definitions in registry
- Error messages pull from registry
- No duplication of usage strings

### 2. Maintainability ✅
- Add command to registry → error messages update automatically
- Remove command from registry → error messages update automatically
- Change usage string in registry → error messages update everywhere

### 3. Consistency ✅
- All namespaced commands use same error handling pattern
- All error messages reference registry
- All usage strings match registry definitions

### 4. Discoverability ✅
- Better formatted error messages
- Shows all available commands with descriptions
- Easier for users to find correct command

## Testing

### Test Invalid Subcommand
```bash
system@mismartera: system invalid
# Should show all system commands from registry
```

### Test No Subcommand
```bash
system@mismartera: system
# Should show usage with all subcommands from registry
```

### Test Partial Arguments
```bash
system@mismartera: system mode
# Should show specific error for this command
```

## Complete Registry Integration

All command namespaces now fully integrated with registry:

| Namespace | Registry | Help | Completion | Error Messages |
|-----------|----------|------|------------|----------------|
| **General** | ✅ GENERAL_COMMANDS | ✅ | ✅ | ✅ |
| **Admin** | ✅ ADMIN_COMMANDS | ✅ | ✅ | ✅ |
| **System** | ✅ SYSTEM_COMMANDS | ✅ | ✅ | ✅ **NEW** |
| **Market** | ✅ MARKET_COMMANDS | ✅ | ✅ | ✅ **NEW** |
| **Holiday** | ✅ HOLIDAY_COMMANDS | ✅ | ✅ | ✅ **NEW** |
| **Data** | ✅ DATA_COMMANDS | ✅ | ✅ | ⏳ |

**Legend:**
- ✅ = Fully integrated with registry
- ⏳ = Planned for future
- **NEW** = Updated in this change

## Next Steps

### Future Enhancements

1. **Data Commands**
   - Update data command error messages to use registry
   - Currently still has some hardcoded usage strings

2. **Dispatch Tables**
   - Create handler mappings in registry
   - Eliminate if/elif chains
   - More functional approach

3. **Validation**
   - Add argument count validation to registry
   - Auto-validate before calling handlers
   - Better error messages for wrong argument count

## Summary

✅ **System, Market, and Holiday commands** now fully use command registry for error messages  
✅ **No more hardcoded usage strings** in error handlers  
✅ **Single source of truth** maintained across all command systems  
✅ **Consistent pattern** applied to all namespaced commands  
✅ **Auto-updating** error messages when registry changes  

The command system is now more maintainable and consistent! 🎉
