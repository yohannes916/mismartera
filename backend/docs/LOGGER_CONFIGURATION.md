# Logger Configuration

## Overview

The logging system now uses a **nested configuration structure** for better organization and clarity. All logger settings are grouped under the `LOGGER` section.

## Configuration Structure

### New Structure (Recommended)

Settings are defined in `app/config/settings.py` using the `LoggerConfig` model:

```python
class LoggerConfig(BaseModel):
    """Logger configuration settings."""
    # Core logging settings
    default_level: str = "INFO"                      # Log level
    file_path: str = "./data/logs/app.log"          # Log file location
    rotation: str = "10 MB"                          # File rotation size
    retention: str = "30 days"                       # Log retention period
    
    # Deduplication filter settings
    filter_enabled: bool = True                      # Enable deduplication
    filter_max_history: int = 5                      # Track N recent locations
    filter_time_threshold_seconds: float = 1.0       # Time window in seconds
```

## Usage

### Via Environment Variables (Recommended)

Set nested configuration using double underscore (`__`) syntax:

```bash
# .env file
LOGGER__DEFAULT_LEVEL=DEBUG
LOGGER__FILE_PATH=./custom/logs/app.log
LOGGER__ROTATION=5 MB
LOGGER__RETENTION=7 days

# Deduplication settings
LOGGER__FILTER_ENABLED=true
LOGGER__FILTER_MAX_HISTORY=10
LOGGER__FILTER_TIME_THRESHOLD_SECONDS=2.0
```

### Via Python Code

```python
from app.config import settings

# Access logger configuration
log_level = settings.LOGGER.default_level
log_path = settings.LOGGER.file_path
dedup_enabled = settings.LOGGER.filter_enabled
dedup_history = settings.LOGGER.filter_max_history
dedup_threshold = settings.LOGGER.filter_time_threshold_seconds
```

## Settings Reference

### Core Logging Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `default_level` | `str` | `"INFO"` | Log level: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL |
| `file_path` | `str` | `"./data/logs/app.log"` | Path to log file (relative or absolute) |
| `rotation` | `str` | `"10 MB"` | Rotate log when file reaches this size |
| `retention` | `str` | `"30 days"` | How long to keep old log files |

### Deduplication Filter Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `filter_enabled` | `bool` | `True` | Enable/disable log deduplication filter |
| `filter_max_history` | `int` | `5` | Number of recent log locations to track |
| `filter_time_threshold_seconds` | `float` | `1.0` | Suppress duplicates within this time window |

## Examples

### Example 1: Development (Verbose Logging)

```bash
# .env
LOGGER__DEFAULT_LEVEL=DEBUG
LOGGER__FILTER_ENABLED=false  # See all logs during development
```

### Example 2: Production (Quiet Logging)

```bash
# .env
LOGGER__DEFAULT_LEVEL=WARNING
LOGGER__FILTER_ENABLED=true
LOGGER__FILTER_TIME_THRESHOLD_SECONDS=5.0  # More aggressive deduplication
```

### Example 3: Debugging Loops (No Deduplication)

```bash
# .env
LOGGER__DEFAULT_LEVEL=DEBUG
LOGGER__FILTER_ENABLED=false  # Need to see every iteration
```

### Example 4: High-Volume System (Aggressive Deduplication)

```bash
# .env
LOGGER__DEFAULT_LEVEL=INFO
LOGGER__FILTER_ENABLED=true
LOGGER__FILTER_MAX_HISTORY=20        # Track more locations
LOGGER__FILTER_TIME_THRESHOLD_SECONDS=10.0  # Longer time window
```

### Example 5: Small Log Files

```bash
# .env
LOGGER__ROTATION=1 MB      # Rotate at 1 MB
LOGGER__RETENTION=7 days   # Keep only 1 week
```

## Backward Compatibility

### Legacy Environment Variables (Deprecated)

The old flat structure is still supported but **deprecated**:

```bash
# OLD (still works but deprecated)
LOG_LEVEL=INFO
LOG_FILE_PATH=./data/logs/app.log
LOG_ROTATION=10 MB
LOG_RETENTION=30 days
LOG_DEDUP_ENABLED=true
LOG_DEDUP_HISTORY=5
LOG_DEDUP_THRESHOLD=1.0
```

**Priority:** Legacy env vars override nested config if both are set.

### Migration Path

**Step 1:** Check if you have any of these env vars set:
```bash
grep "^LOG_" .env
```

**Step 2:** Convert to new structure:
```bash
# OLD → NEW
LOG_LEVEL                → LOGGER__DEFAULT_LEVEL
LOG_FILE_PATH           → LOGGER__FILE_PATH
LOG_ROTATION            → LOGGER__ROTATION
LOG_RETENTION           → LOGGER__RETENTION
LOG_DEDUP_ENABLED       → LOGGER__FILTER_ENABLED
LOG_DEDUP_HISTORY       → LOGGER__FILTER_MAX_HISTORY
LOG_DEDUP_THRESHOLD     → LOGGER__FILTER_TIME_THRESHOLD_SECONDS
```

**Step 3:** Test the new configuration:
```bash
python3 test_log_dedup.py
tail -f data/logs/app.log
```

**Step 4:** Remove old env vars once confirmed working.

## Configuration Validation

The configuration is validated at startup using Pydantic. Invalid values will raise clear errors:

```python
# Invalid log level
LOGGER__DEFAULT_LEVEL=INVALID  # ❌ Will fail validation

# Invalid types
LOGGER__FILTER_MAX_HISTORY=not_a_number  # ❌ Will fail validation

# Valid
LOGGER__DEFAULT_LEVEL=DEBUG  # ✅
LOGGER__FILTER_MAX_HISTORY=10  # ✅
```

## Runtime Changes

Log level can be changed at runtime (other settings require restart):

```python
from app.logger import logger_manager

# Change log level dynamically
new_level = logger_manager.set_level("DEBUG")
print(f"Log level now: {new_level}")

# Get current level
current = logger_manager.get_level()

# Get available levels
levels = logger_manager.get_available_levels()
```

## Accessing Configuration in Code

### Recommended Pattern

```python
from app.config import settings

def setup_logging():
    """Setup custom logging behavior."""
    logger_config = settings.LOGGER
    
    if logger_config.default_level == "DEBUG":
        print("Debug mode enabled")
    
    if logger_config.filter_enabled:
        print(f"Deduplication: {logger_config.filter_max_history} history, "
              f"{logger_config.filter_time_threshold_seconds}s threshold")
```

### Type Safety

The nested structure provides **type safety** via Pydantic:

```python
# ✅ Type checking works
level: str = settings.LOGGER.default_level
history: int = settings.LOGGER.filter_max_history
threshold: float = settings.LOGGER.filter_time_threshold_seconds

# ❌ IDE will warn about type mismatch
wrong: int = settings.LOGGER.default_level  # Type error!
```

## Benefits of Nested Structure

### 1. **Organization**
All logger settings grouped under `LOGGER.*` prefix

### 2. **Discoverability**
IDE autocomplete shows all logger options:
```python
settings.LOGGER.  # IDE shows: default_level, file_path, rotation, etc.
```

### 3. **Type Safety**
Pydantic validates types and provides clear error messages

### 4. **Documentation**
Settings are self-documenting with inline comments in the model

### 5. **Extensibility**
Easy to add new logger settings without cluttering root config

## Common Patterns

### Pattern 1: Environment-Specific Configs

```bash
# .env.development
LOGGER__DEFAULT_LEVEL=DEBUG
LOGGER__FILTER_ENABLED=false

# .env.production
LOGGER__DEFAULT_LEVEL=WARNING
LOGGER__FILTER_ENABLED=true
LOGGER__FILTER_TIME_THRESHOLD_SECONDS=5.0
```

### Pattern 2: Conditional Deduplication

```python
from app.config import settings

# Disable deduplication for specific operations
if debugging_mode:
    settings.LOGGER.filter_enabled = False
```

### Pattern 3: Dynamic Threshold

```python
# Adjust threshold based on system load
if high_volume_traffic:
    settings.LOGGER.filter_time_threshold_seconds = 10.0
    settings.LOGGER.filter_max_history = 20
```

## Troubleshooting

### Config Not Loading

**Problem:** Changes to `.env` not reflected

**Solution:**
```bash
# Restart the application
# Pydantic only loads env vars at startup
```

### Legacy Vars Override New Config

**Problem:** Setting `LOGGER__DEFAULT_LEVEL` but `LOG_LEVEL` wins

**Solution:**
```bash
# Check for legacy env vars
grep "^LOG_" .env

# Remove them - they take priority
```

### Invalid Configuration

**Problem:** Pydantic validation error on startup

**Solution:**
```bash
# Check types match expected values
LOGGER__FILTER_MAX_HISTORY=5      # ✅ int
LOGGER__FILTER_MAX_HISTORY=five   # ❌ not an int

LOGGER__FILTER_ENABLED=true       # ✅ bool
LOGGER__FILTER_ENABLED=yes        # ❌ not a bool (use true/false)
```

## Related Documentation

- [Log Deduplication Feature](LOG_DEDUPLICATION.md) - Details on the deduplication filter
- [Settings Configuration](../app/config/settings.py) - Full settings structure
- [Logger Implementation](../app/logger.py) - Logger manager code

---

**Status:** ✅ Active (nested structure available, legacy vars still supported)

**Recommendation:** Migrate to nested structure (`LOGGER__*`) for better organization
