.PHONY: help setup clean run-api run-cli test format lint install-deps

# Default target
help:
	@echo "MisMartera Backend - Embedded Python Build System"
	@echo ""
	@echo "Available targets:"
	@echo "  make setup        - Setup embedded Python environment"
	@echo "  make install-deps - Install/update Python dependencies"
	@echo "  make run-api      - Start the FastAPI server"
	@echo "  make run-cli      - Start the CLI (pass ARGS='command' for CLI commands)"
	@echo "  make test         - Run tests"
	@echo "  make format       - Format code with black"
	@echo "  make lint         - Run linting checks"
	@echo "  make clean        - Remove embedded Python and virtual environment"
	@echo "  make clean-cache  - Remove Python cache files"
	@echo ""

# Setup embedded Python environment
setup:
	@echo "Setting up embedded Python environment..."
	@chmod +x setup_embedded_python.sh
	@./setup_embedded_python.sh

# Install or update dependencies
install-deps:
	@if [ ! -d ".venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Installing dependencies..."
	@.venv/bin/pip install -r requirements.txt

# Run API server
run-api:
	@chmod +x start_api.sh
	@./start_api.sh

# Run CLI
run-cli:
	@chmod +x start_cli.sh
	@./start_cli.sh $(ARGS)

# Run tests
test:
	@if [ ! -d ".venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@.venv/bin/pytest

# Format code
format:
	@if [ ! -d ".venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Formatting code with black..."
	@.venv/bin/black app/ run_api.py run_cli.py

# Lint code
lint:
	@if [ ! -d ".venv" ]; then \
		echo "ERROR: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running flake8..."
	@.venv/bin/flake8 app/ run_api.py run_cli.py --max-line-length=100

# Clean everything
clean:
	@echo "Removing embedded Python and virtual environment..."
	@rm -rf .python .venv
	@echo "Cleanup complete!"

# Clean Python cache
clean-cache:
	@echo "Removing Python cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cache cleanup complete!"
