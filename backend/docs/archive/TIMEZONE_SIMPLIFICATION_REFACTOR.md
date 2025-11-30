# Timezone Simplification Refactor

**Date:** 2025-11-26  
**Objective:** Remove all timezone conversions and parameters - assume system timezone everywhere

---

## Principle

**All dates/times are in system timezone (from system_manager.timezone)**
- No timezone parameters in function signatures
- No timezone conversions (no `.astimezone()` calls)
- No hardcoded timezones (not even "UTC" or "America/New_York")
- Get timezone from `time_manager.default_timezone` only when absolutely needed

---

## Changes Required

### 1. TimeManager API (time_manager/api.py)

**Remove timezone parameter from:**
- `get_current_time(timezone=None)` → `get_current_time()`
- `convert_timezone(dt, to_timezone)` → DELETE METHOD
- `to_utc(dt)` → DELETE METHOD

**Update methods:**
- All timezone conversions removed
- All timezone parameters removed
- Always use `self.default_timezone` internally

### 2. ParquetStorage (data_manager/parquet_storage.py)

**Remove:**
- `request_timezone` parameter from `read_bars()`, `read_quotes()`
- `source_timezone` parameter from `_convert_dates_to_utc()`
- All `.astimezone()` calls

**Simplify:**
- Assume input dates are in system timezone
- Return timestamps in system timezone
- Internal UTC handling only (no conversions exposed)

### 3. TradingSession Model (time_manager/models.py)

**Remove methods:**
- `get_regular_open_utc()` - not needed
- `get_regular_close_utc()` - not needed

**Keep methods (but simplify):**
- `get_regular_open_datetime()` - returns system timezone
- `get_regular_close_datetime()` - returns system timezone

### 4. Data Integrations

**Alpaca (integrations/alpaca_data.py):**
- Remove timezone conversions in `_to_alpaca_ts()`
- Assume all timestamps are system timezone

**Schwab (integrations/schwab_data.py):**
- Remove hardcoded `ZoneInfo("America/New_York")`
- Use system timezone from TimeManager

### 5. Background Threads

**data_upkeep_thread.py:**
- Remove `pytz.timezone()` calls
- Remove `.astimezone()` conversions
- Use TimeManager for all time operations

**backtest_stream_coordinator.py:**
- Remove timezone conversions
- Assume all timestamps are system timezone

### 6. CLI Display

**Remove:**
- Hardcoded timezone strings in display
- Get timezone from TimeManager for display labels only

---

## Implementation Strategy

### Phase 1: TimeManager (Core)
1. Remove timezone parameter from `get_current_time()`
2. Delete `convert_timezone()` and `to_utc()` methods
3. Simplify all internal timezone handling

### Phase 2: Storage Layer
1. Remove `request_timezone` from ParquetStorage
2. Remove all `.astimezone()` calls
3. Assume system timezone everywhere

### Phase 3: Integrations
1. Update Alpaca integration
2. Update Schwab integration
3. Remove hardcoded timezones

### Phase 4: Background Threads
1. Update upkeep thread
2. Update stream coordinator
3. Remove all timezone conversions

### Phase 5: Testing
1. Compile check
2. Run timezone tests
3. Verify system timezone used everywhere

---

## Files to Modify

1. `app/managers/time_manager/api.py`
2. `app/managers/time_manager/models.py`
3. `app/managers/data_manager/parquet_storage.py`
4. `app/managers/data_manager/integrations/alpaca_data.py`
5. `app/managers/data_manager/integrations/schwab_data.py`
6. `app/managers/data_manager/data_upkeep_thread.py`
7. `app/managers/data_manager/backtest_stream_coordinator.py`
8. `app/managers/data_manager/api.py`
9. CLI display files (for timezone labels only)

---

## Breaking Changes

**API Changes:**
- `time_mgr.get_current_time(timezone="UTC")` → `time_mgr.get_current_time()` (no param)
- `storage.read_bars(..., request_timezone="UTC")` → `storage.read_bars(...)` (no param)
- `time_mgr.convert_timezone(dt, "UTC")` → METHOD DELETED
- `time_mgr.to_utc(dt)` → METHOD DELETED

**Behavior:**
- All timestamps now in system timezone (no conversion options)
- Advanced users cannot override timezone
- Simpler but less flexible

**Migration:**
```python
# OLD
time = time_mgr.get_current_time(timezone="UTC")
utc_time = time_mgr.to_utc(et_time)
df = storage.read_bars(..., request_timezone="UTC")

# NEW
time = time_mgr.get_current_time()  # Always system timezone
# No timezone conversions needed
df = storage.read_bars(...)  # Always system timezone
```

---

## Benefits

1. **Simpler API** - No timezone parameters to worry about
2. **Less Code** - No conversion logic scattered everywhere
3. **Consistent** - Everything in same timezone
4. **Fewer Bugs** - No timezone mismatch errors
5. **Clearer Intent** - System timezone is explicit default

---

## Status

- [ ] Phase 1: TimeManager
- [ ] Phase 2: Storage Layer
- [ ] Phase 3: Integrations
- [ ] Phase 4: Background Threads
- [ ] Phase 5: Testing

**Next:** Execute refactor systematically
