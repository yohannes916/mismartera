#!/bin/bash
# Launcher script for Code-OSS using embedded Node.js

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMBEDDED_NODE="${SCRIPT_DIR}/.node/bin/node"
EMBEDDED_NPM="${SCRIPT_DIR}/.node/bin/npm"

# Check if embedded Node.js exists
if [ ! -f "${EMBEDDED_NODE}" ]; then
    echo "ERROR: Embedded Node.js not found!"
    echo "Please run setup first:"
    echo "  ./setup_embedded_node.sh"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "${SCRIPT_DIR}/node_modules" ]; then
    echo "ERROR: node_modules not found!"
    echo "Please run setup first:"
    echo "  ./setup_embedded_node.sh"
    exit 1
fi

echo "=================================="
echo "Launching Code-OSS"
echo "=================================="
echo ""
echo "Using Node.js: $("${EMBEDDED_NODE}" --version)"
echo "Using npm: $("${EMBEDDED_NPM}" --version)"
echo ""

# Export Node path for scripts
export PATH="${SCRIPT_DIR}/.node/bin:${PATH}"

# Handle different launch modes
case "$1" in
    --watch)
        echo "Starting in watch mode..."
        echo "This will compile TypeScript in watch mode."
        echo "Open another terminal and run ./launch_code.sh to start the app."
        echo ""
        exec "${EMBEDDED_NPM}" run watch
        ;;
    --compile)
        echo "Compiling Code-OSS..."
        exec "${EMBEDDED_NPM}" run compile
        ;;
    --test)
        echo "Running tests..."
        exec "${EMBEDDED_NPM}" test
        ;;
    --help|-h)
        echo "Usage: ./launch_code.sh [OPTIONS] [VSCODE_ARGS]"
        echo ""
        echo "Options:"
        echo "  --watch         Compile in watch mode (TypeScript)"
        echo "  --compile       One-time compilation"
        echo "  --test          Run tests"
        echo "  --help, -h      Show this help message"
        echo ""
        echo "Without options, launches Code-OSS directly."
        echo "Any other arguments are passed to Code-OSS."
        echo ""
        echo "Examples:"
        echo "  ./launch_code.sh                    # Launch Code-OSS"
        echo "  ./launch_code.sh --watch            # Start watch mode"
        echo "  ./launch_code.sh /path/to/project   # Open specific folder"
        echo "  ./launch_code.sh --help             # VS Code help"
        exit 0
        ;;
    *)
        # Launch Code-OSS using the scripts/code.sh wrapper
        echo "Launching Code-OSS application..."
        echo ""
        exec "${SCRIPT_DIR}/scripts/code.sh" "$@"
        ;;
esac
