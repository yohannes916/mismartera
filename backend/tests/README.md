# Tests

Tests will be written after architecture refactoring is complete.

## Structure

```
tests/
├── unit/          # Unit tests (services, utilities)
├── integration/   # Integration tests (managers, threads)
└── e2e/           # End-to-end tests (full system)
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test type
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=app tests/
```

## Test Guidelines

- Unit tests should be fast and isolated
- Integration tests use test database
- E2E tests test full system workflows
- Follow naming convention: `test_*.py`
- Use fixtures for common setup
