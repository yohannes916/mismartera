# Timezone Architecture - Documentation Update

**Date:** 2025-11-29  
**Status:** ✅ COMPLETE

---

## Summary

Added comprehensive timezone handling documentation to ARCHITECTURE.md as a core architecture principle. Updated SystemManager to clearly document timezone derivation and boundary conversion principles.

---

## Key Principle

**Work in market timezone everywhere, convert only at boundaries.**

### Storage (Internal)
- TimeManager: Stores times in UTC
- Database: Stores timestamps in UTC
- DataManager: Queries/stores in UTC

### Return Values (External)
- TimeManager: Returns times in `system_manager.timezone` (market timezone)
- DataManager: Returns times in `system_manager.timezone` (market timezone)
- **Never specify timezone explicitly** - Always use system default

### Timezone Derivation

```python
# system_manager.timezone is derived from exchange_group + asset_class
exchange_group = "US_EQUITY"   # From session config
asset_class = "EQUITY"          # From session config
timezone = "America/New_York"   # Queried from MarketHours database
```

**SQL Query:**
```sql
SELECT timezone FROM market_hours 
WHERE exchange_group = 'US_EQUITY' AND asset_class = 'EQUITY'
```

---

## Boundary Conversion

**ONLY TimeManager and DataManager perform timezone conversions.**

```
┌─────────────────────────────────────────────────────────────┐
│  APPLICATION CODE (Works in Market Timezone)                │
│  • Never specify timezone                                   │
│  • Always use defaults                                      │
│  • current_time = time_mgr.get_current_time()              │
│  • bar.timestamp is already in market timezone              │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │ BOUNDARY      │ BOUNDARY      │
        ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ TimeManager  │  │ DataManager  │  │  Database    │
│              │  │              │  │              │
│ Converts:    │  │ Converts:    │  │ Stores:      │
│ UTC → Market │  │ UTC → Market │  │ UTC only     │
│ Market → UTC │  │ Market → UTC │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Rules

1. ✅ **DO**: Use `time_mgr.get_current_time()` (returns market timezone)
2. ✅ **DO**: Use `bar.timestamp` as-is (already market timezone)
3. ✅ **DO**: Use `session.regular_open` as-is (already market timezone)
4. ❌ **DON'T**: Call `.astimezone()` outside TimeManager/DataManager
5. ❌ **DON'T**: Specify timezone explicitly (breaks consistency)
6. ❌ **DON'T**: Convert timezones in application code

---

## Example: Correct Usage

```python
# ✅ CORRECT - Work in market timezone
time_mgr = system_mgr.get_time_manager()

# Get current time (in market timezone)
current_time = time_mgr.get_current_time()  # Already in market TZ

# Get trading session
with SessionLocal() as db:
    session = time_mgr.get_trading_session(db, current_time.date())
    
    # Times are in market timezone
    open_time = session.regular_open   # time(9, 30) in market TZ
    close_time = session.regular_close  # time(16, 0) in market TZ
    
    # Combine with date (market timezone implied)
    market_open_dt = datetime.combine(
        current_time.date(),
        open_time
    )  # Still in market timezone

# Get bars (timestamps already in market timezone)
bars = data_mgr.get_bars(symbol, interval, start_date, end_date)
for bar in bars:
    # bar.timestamp is already in market timezone
    print(f"Bar at {bar.timestamp}")  # No conversion needed!
```

---

## Example: Wrong Usage

```python
# ❌ WRONG - Don't convert timezones manually
current_time = time_mgr.get_current_time()
utc_time = current_time.astimezone(pytz.UTC)  # ❌ Don't do this!

# ❌ WRONG - Don't specify timezone explicitly
current_time = time_mgr.get_current_time("UTC")  # ❌ Breaks consistency!

# ❌ WRONG - Don't do timezone arithmetic
eastern = pytz.timezone("America/New_York")  # ❌ Don't do this!
local_time = eastern.localize(datetime.now())  # ❌ Use TimeManager!
```

---

## Time Objects with Timezone

TimeManager stores `time` objects (e.g., market open/close) with timezone metadata:

```python
# MarketHours table stores:
regular_open = time(9, 30)      # Not timezone-aware
timezone = "America/New_York"    # Separate field

# When returning, TimeManager combines:
trading_session.regular_open = time(9, 30)
trading_session.timezone = "America/New_York"

# Application code uses:
open_time = session.regular_open  # time(9, 30)
# Knows it's in market timezone (system_manager.timezone)
```

---

## Why This Matters

1. **Consistency**: All code sees times in same timezone (market)
2. **Simplicity**: No timezone conversions in application code
3. **Correctness**: Boundary conversion prevents timezone bugs
4. **Clarity**: Always work in market timezone (where trading happens)
5. **UTC Day Boundaries**: Extended hours can cross UTC midnight - handled at boundaries

---

## Documentation Updates

### 1. ARCHITECTURE.md

Added **Principle #5: Timezone Handling (CRITICAL)** with:
- Storage/Return principles
- Timezone derivation explanation
- Boundary conversion diagram
- Time objects with timezone
- Rules (DO/DON'T)
- Correct vs Wrong usage examples
- Why it matters

**Location:** Between "Configuration Philosophy" and "Layer Isolation"

### 2. SystemManager (app/managers/system_manager/api.py)

Updated class docstring with timezone handling section:
```python
class SystemManager:
    """
    ...
    Timezone Handling:
    - system_manager.timezone is derived from exchange_group + asset_class
    - This becomes the DEFAULT timezone for all time operations
    - TimeManager and DataManager convert to/from UTC at boundaries
    - Application code works in market timezone (never converts manually)
    ...
    """
```

Updated timezone attribute comments:
```python
# Timezone (derived from exchange_group + asset_class via MarketHours database)
# CRITICAL: This is the market timezone used by TimeManager and DataManager
# All timestamps returned by managers are in this timezone
self.timezone: Optional[str] = None
```

Updated `_update_timezone()` docstring with critical principle:
```python
def _update_timezone(self):
    """
    Derive timezone from exchange_group + asset_class.
    
    CRITICAL TIMEZONE PRINCIPLE:
    - This timezone (system_manager.timezone) becomes the DEFAULT timezone
    - TimeManager and DataManager store times in UTC internally
    - TimeManager and DataManager RETURN times in this timezone
    - Application code should NEVER specify timezone explicitly
    - All timestamp conversions happen at TimeManager/DataManager boundaries
    ...
    """
```

### 3. Common Mistakes Section

Added timezone-related mistakes to ARCHITECTURE.md quick reference:

| Mistake | Correct Approach |
|---------|------------------|
| Converting timezones manually | Let TimeManager/DataManager handle it |
| Specifying timezone explicitly | Use system default (never specify) |
| Calling `.astimezone()` in app code | Work in market timezone throughout |
| Creating timezone objects | Use `time_mgr.get_current_time()` which is already in market TZ |

---

## Implementation Verification

### SystemManager Already Compliant ✅

The `SystemManager._update_timezone()` method already:
1. ✅ Queries MarketHours database
2. ✅ Derives timezone from exchange_group + asset_class
3. ✅ Sets `system_manager.timezone`
4. ✅ Logs timezone derivation
5. ✅ Falls back to "America/New_York" if not found

**Code:**
```python
def _update_timezone(self):
    try:
        with SessionLocal() as session:
            from app.models.trading_calendar import MarketHours
            market_hours = session.query(MarketHours).filter_by(
                exchange_group=self.exchange_group,
                asset_class=self.asset_class
            ).first()
            
            if market_hours:
                self.timezone = market_hours.timezone
                logger.debug(f"Timezone set to: {self.timezone}")
            else:
                # Fallback to US Eastern
                self.timezone = "America/New_York"
                logger.warning(
                    f"No timezone found for {self.exchange_group}/{self.asset_class}, "
                    f"defaulting to {self.timezone}"
                )
    except Exception as e:
        # Fallback on error
        self.timezone = "America/New_York"
        logger.warning(f"Error looking up timezone: {e}, defaulting to {self.timezone}")
```

---

## Testing Checklist

### Verify Timezone Derivation

```python
# Test timezone is derived correctly
system_mgr = get_system_manager()
system_mgr.start("session_configs/example_session.json")

# Check timezone was derived
assert system_mgr.timezone is not None
assert system_mgr.timezone == "America/New_York"  # For US_EQUITY

# Check TimeManager uses it
time_mgr = system_mgr.get_time_manager()
current_time = time_mgr.get_current_time()
assert current_time.tzinfo is not None
```

### Verify Boundary Conversion

```python
# Verify TimeManager returns market timezone
time_mgr = system_mgr.get_time_manager()
current = time_mgr.get_current_time()
assert str(current.tzinfo) == "America/New_York"

# Verify DataManager returns market timezone
bars = data_mgr.get_bars("AAPL", "1m", start, end)
for bar in bars:
    assert bar.timestamp.tzinfo is not None
    # Should be in market timezone
```

### Verify No Explicit Timezone Specifications

```bash
# Search for timezone specifications in application code
# (Outside TimeManager and DataManager)
grep -r "get_current_time(" app/threads/
grep -r "get_current_time(" app/services/
grep -r "get_current_time(" app/strategies/

# Should NOT find any with explicit timezone argument
# ✅ Good: time_mgr.get_current_time()
# ❌ Bad: time_mgr.get_current_time("UTC")
```

---

## Benefits

1. **Clear Documentation**: Timezone handling is now a documented architecture principle
2. **Consistency**: Single pattern used throughout codebase
3. **No Confusion**: Clear boundary between UTC storage and market timezone usage
4. **Easy to Follow**: Developers know: "Work in market timezone, never convert"
5. **Fewer Bugs**: Boundary conversion prevents timezone-related bugs
6. **Better Debugging**: All times in logs are in market timezone (human-readable)

---

## Related Documentation

- `ARCHITECTURE.md` - Section: "Timezone Handling (CRITICAL)"
- `app/managers/system_manager/api.py` - Class and method docstrings
- `app/managers/time_manager/README.md` - TimeManager timezone handling
- Memory: "CRITICAL CODE WRITING RULES" - Timezone principles

---

## Status

**✅ COMPLETE**

Timezone handling is now clearly documented as a core architecture principle. SystemManager already implements correct timezone derivation. All timestamps returned by TimeManager and DataManager are in market timezone.

**No code changes needed** - only documentation updates to make the existing pattern explicit.

---

**Key Takeaway:** Work in market timezone everywhere. Only TimeManager and DataManager touch UTC.
