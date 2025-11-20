#!/bin/bash
# Start the FastAPI server using embedded Python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# Check if virtual environment exists
if [ ! -d "${VENV_DIR}" ]; then
    echo "ERROR: Embedded Python environment not found!"
    echo "Please run: ./setup_embedded_python.sh"
    exit 1
fi

# Activate virtual environment and run API
source "${VENV_DIR}/bin/activate"

echo "Starting MisMartera API Server..."
echo "Environment: ${VENV_DIR}"
python --version

exec python run_api.py "$@"
