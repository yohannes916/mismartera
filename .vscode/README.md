# VS Code Configuration

Workspace-level VS Code configuration for the Mismartera project.

## Files

- **launch.json** - Debug/run configurations
- **settings.json** - Workspace settings (Python, testing, formatting)

## Launch Configurations (Press F5)

### CLI & Application
1. **CLI: Interactive Mode** - Start interactive CLI
2. **CLI: Single Command** - Run single CLI command
3. **CLI: Init Database** - Initialize database
4. **API: Start Server** - Start API server
5. **Python: Current File** - Run current Python file

### Test Runners
6. **Pytest: All Unit Tests** - Run all unit tests (241 tests)
7. **Pytest: All Integration Tests** - Run all integration tests (253 tests)
8. **Tests: Run Current Test File** - Run tests in current file
9. **Tests: Run Failed Tests Only** - Re-run only failed tests (--lf)

### Coverage Configurations
10. **Pytest: DataManager Coverage** - Unit tests with DataManager coverage
11. **Pytest: All Tests with Full Coverage** - All tests with app coverage

### Specific Test Groups
12. **Tests: All Quality Tests** - All quality-related tests
13. **Tests: Quality Unit Tests** - Quality unit tests only
14. **Tests: Quality Integration Tests** - Quality integration tests only
15. **Tests: All Backend Tests** - All tests (unit + integration)

### Advanced
16. **Pytest: Current Test Function** - Run specific test (select function name first)

## Project Structure

```
mismartera/
├── backend/
│   ├── .venv/              # Python virtual environment
│   ├── app/                # Source code
│   │   └── managers/
│   │       └── data_manager/
│   ├── tests/              # ✅ All tests are here
│   │   ├── unit/           # 241 unit tests
│   │   └── integration/    # 253 integration tests
│   ├── .env                # Environment variables
│   └── htmlcov/            # Coverage reports
└── .vscode/                # ✅ Workspace config (this directory)
    ├── launch.json
    ├── settings.json
    └── README.md
```

## Test Status (Dec 10, 2025)

- ✅ **Unit Tests**: 241/241 (100%)
- ✅ **Integration Tests**: 204/253 (80.6%)
- **Total**: 445/494 tests passing (90.1%)

## How to Use

### Run Tests with Debugger
1. Open Run and Debug panel: `Ctrl+Shift+D` (or `Cmd+Shift+D` on Mac)
2. Select configuration from dropdown
3. Press `F5` or click green play button
4. Set breakpoints by clicking left of line numbers

### Run Specific Test Function
1. Open a test file
2. **Select (highlight)** the test function name (e.g., `test_register_single_symbol`)
3. Choose "Pytest: Current Test Function" from dropdown
4. Press `F5`

### View Coverage Reports
After running coverage configurations:
```bash
# From backend directory
cd backend
xdg-open htmlcov/index.html
# or
firefox htmlcov/index.html
```

## Common Terminal Commands

```bash
# Navigate to backend
cd backend

# All unit tests
.venv/bin/python -m pytest tests/unit/ -v

# All integration tests
.venv/bin/python -m pytest tests/integration/ -v

# All tests with coverage
.venv/bin/python -m pytest tests/ -v --cov=app --cov-report=html

# Specific test file
.venv/bin/python -m pytest tests/unit/test_session_data_operations.py -v

# Specific test function
.venv/bin/python -m pytest tests/unit/test_session_data_operations.py::TestSymbolRegistration::test_register_single_symbol -v

# Run only failed tests
.venv/bin/python -m pytest --lf -v
```

## Settings Highlights

### Python Testing
- Test framework: **pytest**
- Test discovery: `backend/tests/`
- Auto-discover on save: **enabled**

### Formatting
- Formatter: **Black**
- Line length: **120 characters**
- Format on save: **enabled**

### Linting
- Linter: **flake8**
- Max line length: **120**
- Ignored rules: `E203`, `W503`

## Coverage Targets

### DataManager Coverage
Current: ~9% overall
- `session_data.py`: 17%
- `symbol_exchange_mapping.py`: 60%
- `interval_storage.py`: 34%

Run "Pytest: DataManager Coverage" to update.

### Full App Coverage
Run "Pytest: All Tests with Full Coverage" to see complete coverage across all modules.

## Troubleshooting

### Tests Not Found
- ✅ Tests are in `backend/tests/`, not `app/managers/data_manager/tests/`
- Ensure workspace folder is opened at `mismartera/` level

### Coverage Not Working
- Ensure `pytest-cov` is installed: `pip install pytest-cov`
- Coverage reports save to `backend/htmlcov/`

### Import Errors
- PYTHONPATH is set to `backend/` in all configurations
- Virtual environment: `backend/.venv/bin/python`

## Recent Changes

**Dec 10, 2025**:
- ✅ Moved configurations from `backend/.vscode/` to workspace level
- ✅ Fixed all test paths (removed stale `app/managers/data_manager/tests/`)
- ✅ Added correct pytest configurations
- ✅ Updated coverage targets
- ✅ Added 241 unit tests (100% passing)
- ✅ Fixed integration tests (204/253 passing, 80.6%)
