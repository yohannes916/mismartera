#!/bin/bash
# Start the CLI application using embedded Python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# Check if virtual environment exists
if [ ! -d "${VENV_DIR}" ]; then
    echo "ERROR: Embedded Python environment not found!"
    echo "Please run: ./setup_embedded_python.sh"
    exit 1
fi

# Activate virtual environment and run CLI
source "${VENV_DIR}/bin/activate"

exec python run_cli.py "$@"
