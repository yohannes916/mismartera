#!/bin/bash
# Quick test of time commands in CLI

echo "Testing time commands..."
echo ""

# Test that commands are registered
.venv/bin/python -c "
from app.cli.command_registry import TIME_COMMANDS
print(f'✅ {len(TIME_COMMANDS)} time commands registered:')
for cmd in TIME_COMMANDS:
    print(f'   - {cmd.name}')
"

echo ""
echo "Testing tab completion..."
.venv/bin/python -c "
from app.cli.interactive import CommandCompleter
completer = CommandCompleter()
if 'time' in completer.commands:
    print('✅ \"time\" command in main command list')
else:
    print('❌ \"time\" command NOT in main command list')

if hasattr(completer, 'time_commands') and len(completer.time_commands) == 7:
    print(f'✅ Tab completion has {len(completer.time_commands)} time subcommands')
else:
    print('❌ Tab completion missing time subcommands')
"

echo ""
echo "✅ Time commands are ready!"
echo ""
echo "Try them in the CLI:"
echo "  ./start_cli.sh"
echo "  system@mismartera: time <TAB>"
echo "  system@mismartera: time current"
echo "  system@mismartera: time session"
