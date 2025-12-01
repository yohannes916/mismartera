# Breaking Changes - Configuration v2.0.0

**Date:** 2025-11-30  
**Status:** ⚠️ **BREAKING CHANGE**  
**Impact:** All users must migrate `.env` files to nested structure

---

## What Changed

### ❌ REMOVED: Backward Compatibility

All legacy (flat) environment variables have been **completely removed**. The system now **only supports the nested structure**.

**Before (v1.x - REMOVED):**
```bash
# These NO LONGER WORK ❌
LOG_LEVEL=INFO
SCHWAB_APP_KEY=xxx
DATA_MANAGER_BACKTEST_DAYS=60
SYSTEM_OPERATING_MODE=backtest
```

**After (v2.0+ - REQUIRED):**
```bash
# You MUST use nested structure ✅
LOGGER__DEFAULT_LEVEL=INFO
SCHWAB__APP_KEY=xxx
DATA_MANAGER__BACKTEST_DAYS=60
SYSTEM__OPERATING_MODE=backtest
```

### What Was Removed

1. **All flat environment variables** (80+ legacy settings)
2. **`model_post_init()` compatibility layer** in `Settings` class
3. **Legacy fallback logic** in `LoggerManager`
4. **Deprecated Phase 2 settings** (DataUpkeepThread, PrefetchWorker, etc.)

---

## Migration Required

### Step 1: Check Your Current .env

```bash
cd backend

# Check if you have any old flat variables
grep -E "^(LOG_LEVEL|SCHWAB_APP_KEY|API_HOST|DATABASE_URL)" .env

# If ANY match, you MUST migrate
```

### Step 2: Convert to Nested Structure

Use this conversion table:

| OLD (❌ REMOVED) | NEW (✅ REQUIRED) |
|------------------|-------------------|
| `LOG_LEVEL` | `LOGGER__DEFAULT_LEVEL` |
| `LOG_FILE_PATH` | `LOGGER__FILE_PATH` |
| `SCHWAB_APP_KEY` | `SCHWAB__APP_KEY` |
| `ALPACA_API_KEY_ID` | `ALPACA__API_KEY_ID` |
| `API_HOST` | `API__HOST` |
| `DATABASE_URL` | `DATABASE__URL` |
| `SYSTEM_OPERATING_MODE` | `SYSTEM__OPERATING_MODE` |
| `PAPER_TRADING` | `TRADING__PAPER_TRADING` |
| `DATA_MANAGER_DATA_API` | `DATA_MANAGER__DATA_API` |
| `TRADING_TIMEZONE` | `TIMEZONE__TRADING_TIMEZONE` |

**Complete list:** See `docs/CONFIGURATION_MIGRATION.md`

### Step 3: Test

```bash
# Test config loads
python3 -c "from app.config import settings; print('✅ Config OK')"

# If error, check your .env file for old variable names
```

---

## Error Messages You'll See

### If Using Old Variables

```bash
# Old .env:
LOG_LEVEL=DEBUG

# Error on startup:
ValidationError: Field 'LOGGER__DEFAULT_LEVEL' not set
```

**Solution:** Rename `LOG_LEVEL` → `LOGGER__DEFAULT_LEVEL`

### If Config Missing

```bash
# Error:
ValidationError: Field 'SECURITY__SECRET_KEY' is required
```

**Solution:** Add `SECURITY__SECRET_KEY=your-key-here` to `.env`

---

## Breaking Changes Detail

### 1. No More Flat Variables

**REMOVED:**
```python
class Settings(BaseSettings):
    LOG_LEVEL: Optional[str] = None              # ❌ REMOVED
    SCHWAB_APP_KEY: Optional[str] = None         # ❌ REMOVED
    API_HOST: Optional[str] = None               # ❌ REMOVED
    # ... 80+ more removed
```

**ONLY THIS WORKS:**
```python
settings.LOGGER.default_level    # ✅
settings.SCHWAB.app_key          # ✅
settings.API.host                # ✅
```

### 2. No More Compatibility Layer

**REMOVED:**
```python
def model_post_init(self, __context):
    """Apply legacy settings as overrides if set."""
    if self.LOG_LEVEL is not None:              # ❌ REMOVED
        self.LOGGER.default_level = self.LOG_LEVEL
    # ... all removed
```

### 3. Logger Requires Nested Config

**REMOVED:**
```python
self.current_level = settings.LOG_LEVEL or settings.LOGGER.default_level  # ❌
```

**NOW:**
```python
self.current_level = settings.LOGGER.default_level  # ✅
```

### 4. Deprecated Phase 2 Settings Removed

These controlled OLD architecture components (removed in Phase 3):

**REMOVED:**
```bash
DATA_UPKEEP_ENABLED              # ❌ REMOVED
DATA_UPKEEP_CHECK_INTERVAL       # ❌ REMOVED
PREFETCH_ENABLED                 # ❌ REMOVED
HISTORICAL_BARS_ENABLED          # ❌ REMOVED
SESSION_BOUNDARY_CHECK_INTERVAL  # ❌ REMOVED
```

**USE INSTEAD:**
```bash
SESSION__QUALITY_CHECK_INTERVAL   # ✅
SESSION__HISTORICAL_ENABLED       # ✅
SESSION__AUTO_ROLL                # ✅
```

---

## Automated Migration Script

```bash
# Create migration script
cat > migrate_env.sh << 'EOF'
#!/bin/bash
# Migrate .env from v1.x to v2.0

cp .env .env.v1.backup

sed -i 's/^LOG_LEVEL=/LOGGER__DEFAULT_LEVEL=/g' .env
sed -i 's/^LOG_FILE_PATH=/LOGGER__FILE_PATH=/g' .env
sed -i 's/^LOG_ROTATION=/LOGGER__ROTATION=/g' .env
sed -i 's/^LOG_RETENTION=/LOGGER__RETENTION=/g' .env
sed -i 's/^LOG_DEDUP_ENABLED=/LOGGER__FILTER_ENABLED=/g' .env
sed -i 's/^LOG_DEDUP_HISTORY=/LOGGER__FILTER_MAX_HISTORY=/g' .env
sed -i 's/^LOG_DEDUP_THRESHOLD=/LOGGER__FILTER_TIME_THRESHOLD_SECONDS=/g' .env

sed -i 's/^SYSTEM_OPERATING_MODE=/SYSTEM__OPERATING_MODE=/g' .env
sed -i 's/^DISABLE_CLI_LOGIN_REQUIREMENT=/SYSTEM__DISABLE_CLI_LOGIN=/g' .env

sed -i 's/^API_HOST=/API__HOST=/g' .env
sed -i 's/^API_PORT=/API__PORT=/g' .env

sed -i 's/^SECRET_KEY=/SECURITY__SECRET_KEY=/g' .env
sed -i 's/^ALGORITHM=/SECURITY__ALGORITHM=/g' .env
sed -i 's/^ACCESS_TOKEN_EXPIRE_MINUTES=/SECURITY__ACCESS_TOKEN_EXPIRE_MINUTES=/g' .env

sed -i 's/^DATABASE_URL=/DATABASE__URL=/g' .env

sed -i 's/^SCHWAB_APP_KEY=/SCHWAB__APP_KEY=/g' .env
sed -i 's/^SCHWAB_APP_SECRET=/SCHWAB__APP_SECRET=/g' .env
sed -i 's/^SCHWAB_CALLBACK_URL=/SCHWAB__CALLBACK_URL=/g' .env
sed -i 's/^SCHWAB_API_BASE_URL=/SCHWAB__API_BASE_URL=/g' .env

sed -i 's/^ALPACA_API_KEY_ID=/ALPACA__API_KEY_ID=/g' .env
sed -i 's/^ALPACA_API_SECRET_KEY=/ALPACA__API_SECRET_KEY=/g' .env
sed -i 's/^ALPACA_API_BASE_URL=/ALPACA__API_BASE_URL=/g' .env
sed -i 's/^ALPACA_DATA_BASE_URL=/ALPACA__DATA_BASE_URL=/g' .env
sed -i 's/^ALPACA_PAPER_TRADING=/ALPACA__PAPER_TRADING=/g' .env

sed -i 's/^ANTHROPIC_API_KEY=/CLAUDE__API_KEY=/g' .env
sed -i 's/^CLAUDE_MODEL=/CLAUDE__MODEL=/g' .env

sed -i 's/^PAPER_TRADING=/TRADING__PAPER_TRADING=/g' .env
sed -i 's/^MAX_POSITION_SIZE=/TRADING__MAX_POSITION_SIZE=/g' .env
sed -i 's/^DEFAULT_ORDER_TIMEOUT=/TRADING__DEFAULT_ORDER_TIMEOUT=/g' .env

sed -i 's/^DATA_MANAGER_DATA_API=/DATA_MANAGER__DATA_API=/g' .env
sed -i 's/^DATA_MANAGER_BACKTEST_DAYS=/DATA_MANAGER__BACKTEST_DAYS=/g' .env
sed -i 's/^DATA_MANAGER_BACKTEST_SPEED=/DATA_MANAGER__BACKTEST_SPEED=/g' .env

sed -i 's/^EXECUTION_MANAGER_DEFAULT_BROKERAGE=/EXECUTION__DEFAULT_BROKERAGE=/g' .env

sed -i 's/^MISMARTERA_INITIAL_BALANCE=/MISMARTERA__INITIAL_BALANCE=/g' .env
sed -i 's/^MISMARTERA_BUYING_POWER_MULTIPLIER=/MISMARTERA__BUYING_POWER_MULTIPLIER=/g' .env
sed -i 's/^MISMARTERA_EXECUTION_COST_PCT=/MISMARTERA__EXECUTION_COST_PCT=/g' .env
sed -i 's/^MISMARTERA_SLIPPAGE_PCT=/MISMARTERA__SLIPPAGE_PCT=/g' .env

sed -i 's/^TRADING_TIMEZONE=/TIMEZONE__TRADING_TIMEZONE=/g' .env
sed -i 's/^LOCAL_TIMEZONE=/TIMEZONE__LOCAL_TIMEZONE=/g' .env
sed -i 's/^DISPLAY_LOCAL_TIMEZONE=/TIMEZONE__DISPLAY_LOCAL=/g' .env

echo "✅ Migration complete. Old .env backed up to .env.v1.backup"
echo "⚠️  Please review .env and test with: python3 -c \"from app.config import settings; print('OK')\""
EOF

chmod +x migrate_env.sh
```

**Run migration:**
```bash
cd backend
./migrate_env.sh
```

---

## Rollback (If Needed)

If you need to rollback to v1.x:

```bash
# Restore old config code
cd backend
git checkout v1.x -- app/config/settings.py
git checkout v1.x -- app/logger.py
git checkout v1.x -- .env.example

# Restore your old .env
mv .env.v1.backup .env
```

---

## FAQ

### Q: Can I use both old and new variables?

**A:** No. Backward compatibility has been **completely removed**. You **must use** the nested structure.

### Q: What if I forget to migrate?

**A:** The application will fail to start with a `ValidationError` telling you which fields are missing.

### Q: Do session config JSON files need to change?

**A:** No. Session config files (`.json`) are unchanged. This only affects `.env` files.

### Q: Will this break my deployment?

**A:** Yes, if you deploy without updating your `.env` file. **Update your `.env` before deploying v2.0+**.

### Q: Why remove backward compatibility?

**A:** 
1. **Cleaner code** - No more dual paths
2. **Type safety** - Pydantic validates directly
3. **Performance** - No runtime override logic
4. **Clarity** - One way to configure, less confusion

---

## Version Compatibility

| Version | Flat Variables | Nested Variables | Backward Compat |
|---------|----------------|------------------|-----------------|
| v1.x | ✅ Supported | ✅ Supported | ✅ Yes |
| v2.0+ | ❌ REMOVED | ✅ **REQUIRED** | ❌ **NO** |

---

## Support

**Migration issues?**

1. Check `.env.example` for correct format
2. See `docs/CONFIGURATION_MIGRATION.md` for complete table
3. Run migration script: `./migrate_env.sh`
4. Test config: `python3 -c "from app.config import settings; print('OK')"`

**Still stuck?**

Create a migration issue with:
- Your old .env structure (redacted)
- Error message
- What you've tried

---

## Summary

### ⚠️ **ACTION REQUIRED**

1. **Backup your `.env`:** `cp .env .env.backup`
2. **Run migration script:** `./migrate_env.sh` (or manual conversion)
3. **Test:** `python3 -c "from app.config import settings; print('OK')"`
4. **Deploy only after** confirming config works

### 📊 **Impact**

- **Breaking:** Yes - all flat variables removed
- **Effort:** Low - automated migration script provided
- **Risk:** Medium - deployment will fail if .env not updated
- **Benefit:** Clean code, type safety, better organization

---

**Version:** 2.0.0  
**Released:** 2025-11-30  
**Status:** ✅ Active  
**Migration Deadline:** Immediate (for v2.0+ users)
