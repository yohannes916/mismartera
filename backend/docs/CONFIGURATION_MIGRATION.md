# Configuration Migration Guide - Nested Structure

## ⚠️ **BREAKING CHANGE - v2.0.0**

**Date:** 2025-11-30  
**Status:** ❌ **BACKWARD COMPATIBILITY REMOVED**

All flat (legacy) environment variables have been **completely removed**. You **MUST** migrate to the nested structure.

## Overview

The configuration system has been **completely refactored** to use a clean nested structure with Pydantic models. This provides better organization, type safety, and IDE support.

**Migration Status:** ✅ Complete (2025-11-30)  
**Backward Compatibility:** ❌ **REMOVED** - v2.0.0+ requires nested structure only

---

## What Changed

### Before (Flat Structure)
```bash
# Flat, hard to organize
LOG_LEVEL=INFO
SCHWAB_APP_KEY=xxx
DATA_MANAGER_DATA_API=alpaca
SESSION_TIMEOUT_SECONDS=300
```

### After (Nested Structure)
```bash
# Organized into logical sections
LOGGER__DEFAULT_LEVEL=INFO
SCHWAB__APP_KEY=xxx
DATA_MANAGER__DATA_API=alpaca
SESSION__TIMEOUT_SECONDS=300
```

---

## Benefits of Nested Structure

### 1. **Better Organization**
All related settings grouped under section prefixes:
- `LOGGER__*` - All logging settings
- `SCHWAB__*` - All Schwab API settings  
- `SESSION__*` - All session management settings

### 2. **IDE Autocomplete**
```python
from app.config import settings

# IDE shows all logger options
settings.LOGGER.  # ← autocomplete: default_level, file_path, rotation, etc.
```

### 3. **Type Safety**
```python
# Pydantic validates types at startup
level: str = settings.LOGGER.default_level  # ✅ Type-safe
history: int = settings.LOGGER.filter_max_history  # ✅ Type-safe
```

### 4. **Self-Documenting**
```python
class LoggerConfig(BaseModel):
    """Logger configuration settings."""
    default_level: str = "INFO"  # Log level (inline docs)
    file_path: str = "./data/logs/app.log"  # Path to log file
```

### 5. **Easy Extension**
Adding new settings is clean and doesn't clutter root namespace

---

## Migration Steps

### Step 1: Check Your Current .env

```bash
cd backend
cat .env | grep -E "^[A-Z]"  # Show all current env vars
```

### Step 2: Use Migration Table

| Old (Flat) | New (Nested) | Section |
|-----------|--------------|---------|
| `SYSTEM_OPERATING_MODE` | `SYSTEM__OPERATING_MODE` | System |
| `DISABLE_CLI_LOGIN_REQUIREMENT` | `SYSTEM__DISABLE_CLI_LOGIN` | System |
| `API_HOST` | `API__HOST` | API |
| `API_PORT` | `API__PORT` | API |
| `SECRET_KEY` | `SECURITY__SECRET_KEY` | Security |
| `ALGORITHM` | `SECURITY__ALGORITHM` | Security |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `SECURITY__ACCESS_TOKEN_EXPIRE_MINUTES` | Security |
| `DATABASE_URL` | `DATABASE__URL` | Database |
| `SCHWAB_APP_KEY` | `SCHWAB__APP_KEY` | Schwab |
| `SCHWAB_APP_SECRET` | `SCHWAB__APP_SECRET` | Schwab |
| `SCHWAB_CALLBACK_URL` | `SCHWAB__CALLBACK_URL` | Schwab |
| `SCHWAB_API_BASE_URL` | `SCHWAB__API_BASE_URL` | Schwab |
| `ALPACA_API_KEY_ID` | `ALPACA__API_KEY_ID` | Alpaca |
| `ALPACA_API_SECRET_KEY` | `ALPACA__API_SECRET_KEY` | Alpaca |
| `ALPACA_API_BASE_URL` | `ALPACA__API_BASE_URL` | Alpaca |
| `ALPACA_DATA_BASE_URL` | `ALPACA__DATA_BASE_URL` | Alpaca |
| `ALPACA_PAPER_TRADING` | `ALPACA__PAPER_TRADING` | Alpaca |
| `ANTHROPIC_API_KEY` | `CLAUDE__API_KEY` | Claude |
| `CLAUDE_MODEL` | `CLAUDE__MODEL` | Claude |
| `LOG_LEVEL` | `LOGGER__DEFAULT_LEVEL` | Logger |
| `LOG_FILE_PATH` | `LOGGER__FILE_PATH` | Logger |
| `LOG_ROTATION` | `LOGGER__ROTATION` | Logger |
| `LOG_RETENTION` | `LOGGER__RETENTION` | Logger |
| `LOG_DEDUP_ENABLED` | `LOGGER__FILTER_ENABLED` | Logger |
| `LOG_DEDUP_HISTORY` | `LOGGER__FILTER_MAX_HISTORY` | Logger |
| `LOG_DEDUP_THRESHOLD` | `LOGGER__FILTER_TIME_THRESHOLD_SECONDS` | Logger |
| `PAPER_TRADING` | `TRADING__PAPER_TRADING` | Trading |
| `MAX_POSITION_SIZE` | `TRADING__MAX_POSITION_SIZE` | Trading |
| `DEFAULT_ORDER_TIMEOUT` | `TRADING__DEFAULT_ORDER_TIMEOUT` | Trading |
| `DATA_MANAGER_DATA_API` | `DATA_MANAGER__DATA_API` | Data Manager |
| `DATA_MANAGER_BACKTEST_DAYS` | `DATA_MANAGER__BACKTEST_DAYS` | Data Manager |
| `DATA_MANAGER_BACKTEST_SPEED` | `DATA_MANAGER__BACKTEST_SPEED` | Data Manager |
| `EXECUTION_MANAGER_DEFAULT_BROKERAGE` | `EXECUTION__DEFAULT_BROKERAGE` | Execution |
| `MISMARTERA_INITIAL_BALANCE` | `MISMARTERA__INITIAL_BALANCE` | Mismartera |
| `MISMARTERA_BUYING_POWER_MULTIPLIER` | `MISMARTERA__BUYING_POWER_MULTIPLIER` | Mismartera |
| `MISMARTERA_EXECUTION_COST_PCT` | `MISMARTERA__EXECUTION_COST_PCT` | Mismartera |
| `MISMARTERA_SLIPPAGE_PCT` | `MISMARTERA__SLIPPAGE_PCT` | Mismartera |
| `TRADING_TIMEZONE` | `TIMEZONE__TRADING_TIMEZONE` | Timezone |
| `LOCAL_TIMEZONE` | `TIMEZONE__LOCAL_TIMEZONE` | Timezone |
| `DISPLAY_LOCAL_TIMEZONE` | `TIMEZONE__DISPLAY_LOCAL` | Timezone |

### Step 3: Update Your .env File

**Option A: Manual Migration**
```bash
# Edit .env manually using the table above
nano .env
```

**Option B: Automated Script** (coming soon)
```bash
# Run migration script
python3 scripts/migrate_env.py
```

**Option C: Start Fresh**
```bash
# Copy example and fill in your values
cp .env.example .env
nano .env
```

### Step 4: Test Configuration

```bash
# Test that config loads without errors
python3 -c "from app.config import settings; print('Config OK')"
```

### Step 5: Remove Old Env Vars (Optional)

Once you've verified the new structure works:
```bash
# Comment out or remove old flat variables from .env
# Keep both during transition for safety
```

---

## Deprecated Settings (Phase 2 OLD Architecture)

These settings controlled the **OLD architecture** (DataUpkeepThread, PrefetchWorker, SessionBoundaryManager) which was **completely replaced in Phase 3**.

### ❌ REMOVED - Data Upkeep Thread

**Old Settings (DEPRECATED):**
```bash
DATA_UPKEEP_ENABLED=True
DATA_UPKEEP_CHECK_INTERVAL_SECONDS=60
DATA_UPKEEP_RETRY_MISSING_BARS=True
DATA_UPKEEP_MAX_RETRIES=5
DATA_UPKEEP_DERIVED_INTERVALS=5,15
DATA_UPKEEP_AUTO_COMPUTE_DERIVED=True
```

**New Settings (Phase 3):**
```bash
# Split between DataProcessor and DataQualityManager
SESSION__QUALITY_CHECK_INTERVAL=60
SESSION__QUALITY_RETRY_GAPS=true
SESSION__QUALITY_MAX_RETRIES=5
SESSION__DERIVED_INTERVALS=5,15
SESSION__DERIVED_AUTO_COMPUTE=true
```

### ❌ REMOVED - Historical Bars

**Old Settings (DEPRECATED):**
```bash
HISTORICAL_BARS_ENABLED=True
HISTORICAL_BARS_TRAILING_DAYS=5
HISTORICAL_BARS_INTERVALS=1m,5m,1d
HISTORICAL_BARS_AUTO_LOAD=True
```

**New Settings (Phase 3):**
```bash
# Moved to SESSION section
SESSION__HISTORICAL_ENABLED=true
SESSION__HISTORICAL_TRAILING_DAYS=5
SESSION__HISTORICAL_INTERVALS=1m,5m,1d
SESSION__HISTORICAL_AUTO_LOAD=true
```

### ❌ REMOVED - Prefetch Worker

**Old Settings (DEPRECATED - No replacement):**
```bash
PREFETCH_ENABLED=True
PREFETCH_WINDOW_MINUTES=60
PREFETCH_CHECK_INTERVAL_MINUTES=5
PREFETCH_AUTO_ACTIVATE=True
```

**Replacement:** Handled internally by `SessionCoordinator` (no config needed)

### ❌ REMOVED - Session Boundary Manager

**Old Settings (DEPRECATED):**
```bash
SESSION_AUTO_ROLL=True
SESSION_TIMEOUT_SECONDS=300
SESSION_BOUNDARY_CHECK_INTERVAL=60  # Removed (no replacement)
SESSION_POST_MARKET_ROLL_DELAY=30
```

**New Settings (Phase 3):**
```bash
SESSION__AUTO_ROLL=true
SESSION__TIMEOUT_SECONDS=300
# SESSION_BOUNDARY_CHECK_INTERVAL removed (not needed)
SESSION__POST_MARKET_ROLL_DELAY=30
```

---

## ❌ Backward Compatibility - REMOVED

### Breaking Change (v2.0.0)

**Status:** Backward compatibility has been **completely removed** as of 2025-11-30.

**What This Means:**
1. ❌ **Old env vars DO NOT work** - flat variables removed entirely
2. ❌ **No priority system** - only nested structure accepted
3. ❌ **No gradual migration** - immediate migration required

### What Was Removed

```python
# ❌ ALL OF THIS WAS REMOVED:

# Legacy env vars (80+ settings)
LOG_LEVEL: Optional[str] = None
SCHWAB_APP_KEY: Optional[str] = None
API_HOST: Optional[str] = None
# ... all removed

# Compatibility layer
def model_post_init(self, __context):
    if self.LOG_LEVEL is not None:
        self.LOGGER.default_level = self.LOG_LEVEL
    # ... all removed

# Logger fallbacks
self.current_level = settings.LOG_LEVEL or settings.LOGGER.default_level  # removed
```

### Migration Required

**You MUST update your `.env` file to use nested structure:**

```bash
# ❌ OLD (will not work)
LOG_LEVEL=DEBUG

# ✅ NEW (required)
LOGGER__DEFAULT_LEVEL=DEBUG
```

See `docs/BREAKING_CHANGES.md` for:
- Complete migration guide
- Automated migration script
- Error messages and solutions

---

## Code Usage Examples

### ❌ Old Way (NO LONGER WORKS)
```python
from app.config import settings

# Flat access (REMOVED - will cause AttributeError)
log_level = settings.LOG_LEVEL  # ❌ AttributeError
api_key = settings.SCHWAB_APP_KEY  # ❌ AttributeError
```

### ✅ New Way (REQUIRED)
```python
from app.config import settings

# Nested access (ONLY way)
log_level = settings.LOGGER.default_level  # ✅ Type-safe
api_key = settings.SCHWAB.app_key  # ✅ Organized
backtest_days = settings.DATA_MANAGER.backtest_days  # ✅ Clear
```

### Type Safety Benefits

```python
# Old way - no type safety
if settings.LOG_LEVEL.lower() == "debug":  # Might be None!
    ...

# New way - type-safe with defaults
if settings.LOGGER.default_level.lower() == "debug":  # Never None
    ...
```

---

## Common Migration Scenarios

### Scenario 1: Development Environment

```bash
# .env.development (new structure)
SYSTEM__OPERATING_MODE=backtest
LOGGER__DEFAULT_LEVEL=DEBUG
LOGGER__FILTER_ENABLED=false  # See all logs
SESSION__HISTORICAL_TRAILING_DAYS=2  # Faster startup
DATA_MANAGER__BACKTEST_SPEED=0  # Max speed
```

### Scenario 2: Production Environment

```bash
# .env.production (new structure)
SYSTEM__OPERATING_MODE=live
LOGGER__DEFAULT_LEVEL=WARNING
LOGGER__FILTER_ENABLED=true
LOGGER__FILTER_TIME_THRESHOLD_SECONDS=5.0  # Aggressive dedup
SESSION__QUALITY_CHECK_INTERVAL=30  # More frequent checks
```

### Scenario 3: Testing Environment

```bash
# .env.test (new structure)
SYSTEM__OPERATING_MODE=backtest
LOGGER__DEFAULT_LEVEL=ERROR  # Quiet
SESSION__HISTORICAL_ENABLED=false  # Skip historical data
DATA_MANAGER__BACKTEST_DAYS=1  # Minimal data
```

---

## Troubleshooting

### Config Not Loading

**Problem:** Changes to `.env` not reflected

**Solution:**
```bash
# Restart the application (Pydantic loads env vars at startup only)
./start_cli.sh
```

### Legacy Vars Override New Ones

**Problem:** Setting `LOGGER__DEFAULT_LEVEL=DEBUG` but `LOG_LEVEL=INFO` wins

**Solution:**
```bash
# Check for legacy env vars
grep "^LOG_LEVEL" .env

# Remove or comment out legacy vars
#LOG_LEVEL=INFO
```

### Validation Errors

**Problem:** `ValidationError` on startup

**Solution:**
```bash
# Check types match expected values
LOGGER__FILTER_MAX_HISTORY=5      # ✅ int
LOGGER__FILTER_MAX_HISTORY=five   # ❌ not an int

LOGGER__FILTER_ENABLED=true       # ✅ bool
LOGGER__FILTER_ENABLED=yes        # ❌ not a bool (use true/false)
```

### Missing Required Fields

**Problem:** `SECURITY__SECRET_KEY` required but not set

**Solution:**
```bash
# Set required fields in .env
SECURITY__SECRET_KEY=your-secret-key-change-me-in-production
```

---

## Quick Reference

### All Configuration Sections

| Section | Prefix | Description |
|---------|--------|-------------|
| **System** | `SYSTEM__*` | System-level config (operating mode, CLI login) |
| **API** | `API__*` | HTTP API server (host, port) |
| **Security** | `SECURITY__*` | JWT secrets, tokens, algorithms |
| **Database** | `DATABASE__*` | Database connection string |
| **Schwab** | `SCHWAB__*` | Schwab API credentials |
| **Alpaca** | `ALPACA__*` | Alpaca API credentials |
| **Claude** | `CLAUDE__*` | Claude API credentials |
| **Logger** | `LOGGER__*` | Logging config (level, file, dedup) |
| **Trading** | `TRADING__*` | Trading execution (paper trading, limits) |
| **Data Manager** | `DATA_MANAGER__*` | Data provider, backtest config |
| **Execution** | `EXECUTION__*` | Execution manager config |
| **Mismartera** | `MISMARTERA__*` | Simulated trading config |
| **Session** | `SESSION__*` | Session management (Phase 3) |
| **Timezone** | `TIMEZONE__*` | Timezone config |

### Example .env with All Sections

See: `.env.example` for complete example with all sections and settings

---

## Related Documentation

- [Complete Configuration Guide](CONFIGURATION.md) - Comprehensive docs
- [Logger Configuration](LOGGER_CONFIGURATION.md) - Logger-specific docs
- [Log Deduplication](LOG_DEDUPLICATION.md) - Dedup filter details
- [Phase 3 Architecture](SESSION_ARCHITECTURE.md) - New session architecture

---

**Status:** ✅ Migration complete, backward compatible, ready for use

**Recommendation:** Migrate to nested structure (`SECTION__SETTING`) for better organization and type safety

**Support:** See docs or check `.env.example` for examples of all settings
