#!/usr/bin/env python
"""
Start the Interactive CLI Application
"""
import sys
from app.cli.interactive import start_interactive_cli
from app.cli.main import app

if __name__ == "__main__":
    # Check if running in interactive mode (default) or single-command mode
    if len(sys.argv) == 1:
        # No arguments - start interactive REPL
        start_interactive_cli()
    else:
        # Arguments provided - run as single command (for scripts/automation)
        app()
