#!/bin/bash
# Setup script for embedded Python environment
# This creates a fully isolated Python installation independent of system Python

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION="3.11.10"
PLATFORM="x86_64-unknown-linux-gnu"
PYTHON_BUILD_VERSION="20241016"

# Directory for embedded Python
EMBEDDED_DIR="${SCRIPT_DIR}/.python"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "=================================="
echo "MisMartera Embedded Python Setup"
echo "=================================="
echo ""
echo "Python Version: ${PYTHON_VERSION}"
echo "Platform: ${PLATFORM}"
echo "Install Directory: ${EMBEDDED_DIR}"
echo ""

# Clean up old installations
if [ -d "${EMBEDDED_DIR}" ]; then
    echo "Removing old embedded Python installation..."
    rm -rf "${EMBEDDED_DIR}"
fi

if [ -d "${VENV_DIR}" ]; then
    echo "Removing old virtual environment..."
    rm -rf "${VENV_DIR}"
fi

# Create directory structure
mkdir -p "${EMBEDDED_DIR}"
mkdir -p "${EMBEDDED_DIR}/downloads"

# Download standalone Python
PYTHON_TARBALL="cpython-${PYTHON_VERSION}+${PYTHON_BUILD_VERSION}-${PLATFORM}-install_only.tar.gz"
DOWNLOAD_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD_VERSION}/${PYTHON_TARBALL}"

echo "Downloading standalone Python build..."
echo "URL: ${DOWNLOAD_URL}"

cd "${EMBEDDED_DIR}/downloads"

if ! curl -L -o "${PYTHON_TARBALL}" "${DOWNLOAD_URL}"; then
    echo "ERROR: Failed to download Python"
    exit 1
fi

echo "Extracting Python..."
tar -xzf "${PYTHON_TARBALL}" -C "${EMBEDDED_DIR}" --strip-components=1

# Change back to script directory before cleanup
cd "${SCRIPT_DIR}"

# Cleanup download
rm -rf "${EMBEDDED_DIR}/downloads"

# Verify Python installation
PYTHON_BIN="${EMBEDDED_DIR}/bin/python3"

if [ ! -f "${PYTHON_BIN}" ]; then
    echo "ERROR: Python binary not found at ${PYTHON_BIN}"
    exit 1
fi

echo ""
echo "Verifying Python installation..."
"${PYTHON_BIN}" --version

# Create virtual environment using embedded Python
echo ""
echo "Creating virtual environment with embedded Python..."
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

# Activate virtual environment and install dependencies
echo ""
echo "Installing dependencies..."
source "${VENV_DIR}/bin/activate"

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install requirements
if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
    pip install -r "${SCRIPT_DIR}/requirements.txt"
else
    echo "WARNING: requirements.txt not found"
fi

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Embedded Python: ${EMBEDDED_DIR}"
echo "Virtual Environment: ${VENV_DIR}"
echo ""
echo "To activate the environment:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "Or use the provided launcher scripts:"
echo "  ./start_api.sh"
echo "  ./start_cli.sh"
echo ""
