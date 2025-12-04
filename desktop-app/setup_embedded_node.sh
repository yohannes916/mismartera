#!/bin/bash
# Setup script for embedded Node.js environment
# This creates a fully isolated Node.js installation independent of system Node.js

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_VERSION="22.20.0"
PLATFORM="linux-x64"

# Directory for embedded Node.js
EMBEDDED_DIR="${SCRIPT_DIR}/.node"
NODE_MODULES_DIR="${SCRIPT_DIR}/node_modules"

echo "=================================="
echo "Code-OSS Embedded Node.js Setup"
echo "=================================="
echo ""
echo "Node Version: ${NODE_VERSION}"
echo "Platform: ${PLATFORM}"
echo "Install Directory: ${EMBEDDED_DIR}"
echo ""

# Clean up old installations
if [ -d "${EMBEDDED_DIR}" ]; then
    echo "Removing old embedded Node.js installation..."
    rm -rf "${EMBEDDED_DIR}"
fi

if [ -d "${NODE_MODULES_DIR}" ]; then
    echo "Removing old node_modules..."
    rm -rf "${NODE_MODULES_DIR}"
fi

# Create directory structure
mkdir -p "${EMBEDDED_DIR}"
mkdir -p "${EMBEDDED_DIR}/downloads"

# Download standalone Node.js
NODE_TARBALL="node-v${NODE_VERSION}-${PLATFORM}.tar.xz"
DOWNLOAD_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"

echo "Downloading standalone Node.js build..."
echo "URL: ${DOWNLOAD_URL}"

cd "${EMBEDDED_DIR}/downloads"

if ! curl -L -o "${NODE_TARBALL}" "${DOWNLOAD_URL}"; then
    echo "ERROR: Failed to download Node.js"
    exit 1
fi

echo "Extracting Node.js..."
tar -xJf "${NODE_TARBALL}" -C "${EMBEDDED_DIR}" --strip-components=1

# Change back to script directory before cleanup
cd "${SCRIPT_DIR}"

# Cleanup download
rm -rf "${EMBEDDED_DIR}/downloads"

# Verify Node.js installation
NODE_BIN="${EMBEDDED_DIR}/bin/node"
NPM_BIN="${EMBEDDED_DIR}/bin/npm"

if [ ! -f "${NODE_BIN}" ]; then
    echo "ERROR: Node.js binary not found at ${NODE_BIN}"
    exit 1
fi

echo ""
echo "Verifying Node.js installation..."
"${NODE_BIN}" --version
"${NPM_BIN}" --version

# Configure npm to use embedded directory for global installs
echo ""
echo "Configuring npm prefix..."
"${NPM_BIN}" config set prefix "${EMBEDDED_DIR}"

# Ensure embedded Node.js is first in PATH for npm scripts
export PATH="${EMBEDDED_DIR}/bin:${PATH}"

# Verify that the correct Node.js will be used
echo ""
echo "Verifying PATH configuration..."
which node
which npm
node --version

# Install project dependencies using npm (VS Code no longer uses yarn)
# Note: npm 10.9.3 bundled with Node.js 22.20.0 is sufficient, no upgrade needed
echo ""
echo "Installing project dependencies (this may take 10-15 minutes)..."
echo "Note: VS Code uses npm, not yarn"
npm ci

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Embedded Node.js: ${EMBEDDED_DIR}"
echo "Node Modules: ${NODE_MODULES_DIR}"
echo ""
echo "To launch Code-OSS:"
echo "  ./launch_code.sh"
echo ""
echo "To compile in watch mode:"
echo "  ./launch_code.sh --watch"
echo ""
