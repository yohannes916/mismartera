# Script Command Feature

## Overview

The `run` command allows you to execute a series of CLI commands from a script file. This is useful for:
- Automating repetitive tasks
- Setting up a specific system state
- Running batch operations
- Testing command sequences
- Documenting workflows

## Usage

```bash
run <script_file>
```

### Arguments
- `script_file`: Path to the script file (supports tilde expansion for home directory)

## Script File Format

Script files are plain text files containing one command per line.

### Features
- **Comments**: Lines starting with `#` are treated as comments and skipped
- **Empty Lines**: Blank lines are ignored
- **Sequential Execution**: Commands are executed in order, one at a time
- **Error Handling**: Errors in individual commands are reported but don't stop execution
- **Exit/Logout**: Script execution stops if an `exit` or `logout` command is encountered

### Example Script

```bash
# Setup script for daily trading session
# File: daily_setup.txt

# Clear the screen first
clear

# Show system status
system status

# Initialize data
data init

# Start the system
system start

# Display market status
market status

# Show current positions
account positions
```

## Running a Script

From the MisMartera CLI:

```bash
# Run a script from current directory
run example_script.txt

# Run a script from home directory
run ~/scripts/daily_setup.txt

# Run a script with absolute path
run /path/to/script.txt
```

## Output

The command displays:
1. **Script header**: Shows the script path and line count
2. **Line-by-line execution**: Each command is displayed with its line number as it executes
3. **Comments**: Shown in dim text (not executed)
4. **Execution summary**: Shows count of executed commands, skipped lines, and errors

### Example Output

```
Running script: example_script.txt
Lines: 15

  1: # Example Script for MisMartera CLI
  2: # This script demonstrates how to use the 'run' command
  3: 
  5: clear
[Screen cleared...]

  8: system status
[System status display...]

  11: market status
[Market status display...]

Script execution completed
✓ Executed: 5
○ Skipped (comments/empty): 8
```

## Error Handling

- **File Not Found**: Error message displayed, execution stops
- **Permission Denied**: Error message displayed, execution stops
- **Command Errors**: Individual command errors are reported, execution continues
- **Keyboard Interrupt (Ctrl+C)**: Shows which line was interrupted, stops execution
- **Exit/Logout Commands**: Stops execution gracefully

## Best Practices

1. **Add Comments**: Document what each command does
2. **Test First**: Test commands individually before adding to scripts
3. **Use Descriptive Names**: Name scripts clearly (e.g., `daily_setup.txt`, `backtest_aapl.txt`)
4. **Start with Clear**: Begin scripts with `clear` for clean output
5. **Check Status**: Include status commands to verify system state
6. **Handle Errors**: Scripts continue on errors, but check output carefully

## Example Scripts

### Daily Setup Script
```bash
# daily_setup.txt - Initialize system for trading day
clear
system status
data init
system start
market status
```

### Backtest Script
```bash
# backtest.txt - Run a backtest scenario
clear
system stop
system mode backtest
data init
data stream bars AAPL TSLA MSFT
system start
```

### Status Check Script
```bash
# check_status.txt - Quick system health check
system status
market status
data list
account positions
```

## Command Availability

All CLI commands available in interactive mode can be used in scripts:
- General commands: `help`, `status`, `clear`, `whoami`
- System commands: `system start`, `system stop`, `system status`
- Data commands: `data init`, `data list`, `data stream`
- Market commands: `market status`
- Account commands: `account info`, `account positions`
- Trading commands: `buy`, `sell`, `orders`

## Limitations

1. Scripts cannot prompt for user input (use non-interactive commands only)
2. The `run` command cannot be nested (no script calling another script)
3. Commands that require confirmation will use default values
4. Interactive prompts in commands may cause scripts to hang

## See Also

- `help` - View all available commands
- `history` - View command history
- CLI Interactive Mode documentation
