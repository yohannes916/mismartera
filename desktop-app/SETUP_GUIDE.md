# Code-OSS Development Setup

This guide explains how to set up and run Code-OSS with an embedded Node.js environment (similar to the backend's embedded Python setup).

## Prerequisites

- **Linux** (Ubuntu/Debian recommended)
- **Build tools**: `build-essential`, `libx11-dev`, `libxkbfile-dev`, `libsecret-1-dev`
- **10GB+ disk space** (for Node.js, dependencies, and compiled code)
- **8GB+ RAM** (16GB recommended for compilation)

Install system dependencies:
```bash
sudo apt-get update
sudo apt-get install -y build-essential g++ libx11-dev libxkbfile-dev \
  libsecret-1-dev libkrb5-dev python-is-python3
```

## Initial Setup

### 1. Run the Embedded Setup Script

This downloads Node.js v22.20.0 (as required by `.nvmrc`), upgrades npm, and installs all project dependencies:

```bash
./setup_embedded_node.sh
```

**This will take 10-15 minutes** on first run.

What it does:
- Downloads standalone Node.js build to `.node/`
- Upgrades npm to latest version within embedded Node
- Installs all dependencies to `node_modules/` using `npm ci`
- Creates isolated environment (doesn't use system Node.js)

**Note**: VS Code switched from Yarn to npm. Don't use Yarn.

### 2. Verify Setup

After setup completes, verify:
```bash
ls -la .node/bin/node    # Embedded Node.js
ls -la .node/bin/npm     # Embedded npm
ls -la node_modules/     # Project dependencies
```

## Running Code-OSS

### Launch the Application

```bash
./launch_code.sh
```

This will:
1. Pre-compile necessary files (via `build/lib/preLaunch.ts`)
2. Launch the Electron application

### First Launch Notes

On **first launch**, Code-OSS will:
- Download Electron binary (~100MB)
- Compile built-in extensions
- This may take 2-3 minutes

Subsequent launches are much faster.

## Development Workflow

### Watch Mode (Recommended for Development)

**Terminal 1** - Start TypeScript compiler in watch mode:
```bash
./launch_code.sh --watch
```

**Terminal 2** - Launch Code-OSS:
```bash
./launch_code.sh
```

With watch mode, code changes auto-compile and you just need to reload the window (Cmd/Ctrl+R).

### One-Time Compilation

```bash
./launch_code.sh --compile
```

### Open a Specific Folder

```bash
./launch_code.sh /path/to/your/project
```

### Pass VS Code Arguments

```bash
./launch_code.sh --verbose           # Verbose logging
./launch_code.sh --disable-gpu       # Disable GPU acceleration
./launch_code.sh --extensions-dir=/path  # Custom extensions directory
```

## Project Structure

```
frontend/desktop-app/
├── .node/              # Embedded Node.js (isolated)
├── node_modules/       # Project dependencies
├── src/                # TypeScript source code
├── extensions/         # Built-in extensions
├── out/                # Compiled JavaScript (generated)
├── scripts/            # Launch scripts
│   └── code.sh         # Main launch script (called by launch_code.sh)
├── setup_embedded_node.sh   # Setup script (run once)
└── launch_code.sh           # Launcher (run to start)
```

## Key Files

- **`product.json`** - Product configuration (name, version, etc.)
- **`package.json`** - Dependencies and npm scripts
- **`gulpfile.mjs`** - Build tasks
- **`src/`** - TypeScript source code
- **`out/`** - Compiled JavaScript output

## Troubleshooting

### "Embedded Node.js not found"

Run setup first:
```bash
./setup_embedded_node.sh
```

### "Failed to download Node.js"

Check your internet connection and proxy settings. The script downloads from:
```
https://nodejs.org/dist/v18.19.1/node-v18.19.1-linux-x64.tar.xz
```

### Compilation Errors

Clean and rebuild:
```bash
rm -rf .node node_modules out .build
./setup_embedded_node.sh
./launch_code.sh --compile
```

### Electron Download Issues

If Electron fails to download, set a mirror:
```bash
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
./setup_embedded_node.sh
```

### Out of Memory During Build

Increase Node memory:
```bash
# Edit launch_code.sh and add to yarn commands:
# --max-old-space-size=8192
```

Or close other applications to free up RAM.

## Comparison to Official Build

| Aspect | This Setup | Official VS Code |
|--------|-----------|------------------|
| **Node.js** | Embedded v18.19.1 | System Node.js |
| **Dependencies** | Local install | System or global |
| **Isolation** | Complete | Partial |
| **Like Backend?** | ✅ Yes (matches Python setup) | ❌ No |

## Next Steps

Once you can launch Code-OSS, you can:
1. Modify source code in `src/`
2. Add custom features
3. Build custom extensions
4. Create a custom branded editor

See official VS Code documentation:
- [How to Contribute](https://github.com/microsoft/vscode/wiki/How-to-Contribute)
- [Build and Run](https://github.com/microsoft/vscode/wiki/How-to-Contribute#build-and-run)

## Clean Uninstall

To remove everything:
```bash
rm -rf .node node_modules out .build
rm -rf .vscode-test .eslintcache
```

Then re-run `./setup_embedded_node.sh` if needed.
