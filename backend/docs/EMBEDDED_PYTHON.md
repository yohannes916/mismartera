# Embedded Python Setup

This backend uses a fully isolated embedded Python environment that is completely independent from your system Python installation.

## Why Embedded Python?

- ✅ **Complete Isolation** - No interference with system Python
- ✅ **Version Control** - Specific Python version guaranteed
- ✅ **Portability** - Same Python environment across all systems
- ✅ **No System Dependencies** - Self-contained Python installation
- ✅ **Production Ready** - Consistent behavior from dev to production

## Quick Start

### 1. Setup (First Time Only)

```bash
cd backend
make setup
```

This will:
- Download a standalone Python build (Python 3.11.10)
- Extract it to `.python/` directory
- Create a virtual environment in `.venv/`
- Install all dependencies from `requirements.txt`

**Note:** The download is ~50MB and setup takes 2-3 minutes.

### 2. Run the API Server

```bash
make run-api
```

Or use the direct script:
```bash
./start_api.sh
```

### 3. Run the CLI

```bash
make run-cli ARGS="init-db"
```

Or use the direct script:
```bash
./start_cli.sh init-db
```

## Directory Structure

```
backend/
├── .python/          # Embedded Python installation (gitignored)
├── .venv/            # Virtual environment (gitignored)
├── setup_embedded_python.sh  # Setup script
├── start_api.sh      # API launcher
├── start_cli.sh      # CLI launcher
├── Makefile          # Build system
└── ...
```

## Make Commands

```bash
make help         # Show all available commands
make setup        # Setup embedded Python (first time)
make install-deps # Update dependencies
make run-api      # Start API server
make run-cli      # Run CLI commands
make test         # Run tests
make format       # Format code with black
make lint         # Run linting
make clean        # Remove Python environment
make clean-cache  # Remove Python cache files
```

## Manual Activation

If you need to run Python commands directly:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Now you can use python, pip, etc.
python --version
pip list

# When done
deactivate
```

## Updating Dependencies

When you modify `requirements.txt`:

```bash
make install-deps
```

Or manually:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Customizing Python Version

Edit `setup_embedded_python.sh` and change these variables:

```bash
PYTHON_VERSION="3.11.10"
PYTHON_BUILD_VERSION="20241016"
```

Available versions: https://github.com/astral-sh/python-build-standalone/releases

## Troubleshooting

### Setup fails to download Python

Check your internet connection and try again. The script downloads from GitHub releases.

### Permission denied errors

Make scripts executable:
```bash
chmod +x setup_embedded_python.sh start_api.sh start_cli.sh
```

### Environment not found

Run the setup again:
```bash
make clean
make setup
```

### System Python is still being used

Verify you're using the embedded Python:
```bash
source .venv/bin/activate
which python
# Should show: /path/to/backend/.venv/bin/python
```

## For Production Deployment

The embedded Python approach makes deployment simple:

1. Copy the entire `backend/` directory to your server
2. Run `make setup` on the server
3. Use `start_api.sh` or `start_cli.sh` to run the application

No system Python dependencies required!

## Alternative: Development with pyenv

For development, you can also use `pyenv` for Python version management:

```bash
# Install pyenv (one time)
curl https://pyenv.run | bash

# Install Python 3.11.7
pyenv install 3.11.7

# Set local Python version
cd backend
pyenv local 3.11.7

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## CI/CD Integration

For GitHub Actions or other CI/CD:

```yaml
- name: Setup Embedded Python
  run: |
    cd backend
    ./setup_embedded_python.sh

- name: Run Tests
  run: |
    cd backend
    make test
```
