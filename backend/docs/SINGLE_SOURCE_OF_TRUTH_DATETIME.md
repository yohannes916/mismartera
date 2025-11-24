# Single Source of Truth: Date/Time Information

## Summary

Removed hardcoded trading hours from `session_data` and enforced the pattern that **all date/time information must be queried from authoritative sources**, never stored or duplicated.

## The Problem

**Before:** Hardcoded times in session_data
```python
# session_data.py
self.start_time: time = time(9, 30)  # ET - HARDCODED!
self.end_time: time = time(16, 0)    # ET - HARDCODED!

# upkeep_thread.py
session_start = datetime.combine(
    current_date,
    self._session_data.start_time  # Uses hardcoded value
)
```

**Problems:**
- ❌ Doesn't account for holidays (market closed)
- ❌ Doesn't account for early closes (half-days: 9:30 - 1:00 PM)
- ❌ Duplicate source of truth (hardcoded vs trading calendar)
- ❌ Inconsistent with rest of system

## The Solution

**After:** Query from data_manager (trading calendar)
```python
# session_data.py
# NO start_time or end_time attributes!
# NOTE: Get trading hours from data_manager.get_trading_hours() instead.

# upkeep_thread.py
data_manager = self._system_manager.get_data_manager()
trading_hours = await data_manager.get_trading_hours(session, current_date)

if trading_hours is None:
    # Market closed today (holiday)
    return

session_start = datetime.combine(current_date, trading_hours.open_time)
session_end = datetime.combine(current_date, trading_hours.close_time)
```

**Benefits:**
- ✅ Accounts for holidays (returns None)
- ✅ Accounts for early closes (returns correct close time)
- ✅ Single source of truth (trading calendar database)
- ✅ Consistent with rest of system

## Architecture Pattern

### Sources of Truth

```
┌─────────────────────────────────────────────┐
│       AUTHORITATIVE SOURCES (Query)         │
├─────────────────────────────────────────────┤
│                                             │
│  1. Current Time                            │
│     TimeProvider.get_current_time()         │
│     • Live mode: Real-time                  │
│     • Backtest: Simulated time              │
│                                             │
│  2. Trading Hours                           │
│     data_manager.get_trading_hours(date)    │
│     • Queries trading calendar database     │
│     • Returns DayTradingHours or None       │
│     • Accounts for holidays & early closes  │
│                                             │
│  3. Session Date                            │
│     session_data.get_current_session_date() │
│     • Queries TimeProvider internally       │
│     • Returns current date                  │
│                                             │
└─────────────────────────────────────────────┘
```

### What NOT to Do

**❌ NEVER hardcode times:**
```python
# WRONG!
start_time = time(9, 30)
end_time = time(16, 0)
```

**❌ NEVER store time values:**
```python
# WRONG!
self.current_time = datetime.now()  # Gets stale!
self.session_start_time = time(9, 30)  # Doesn't handle early closes!
```

**❌ NEVER duplicate time logic:**
```python
# WRONG!
# In module A:
market_open = time(9, 30)

# In module B:
market_open = time(9, 30)  # Duplicate!

# What if we need to change it? Must update in 2 places!
```

### What TO Do

**✅ ALWAYS query from source:**
```python
# CORRECT!
current_time = time_provider.get_current_time()
trading_hours = await data_manager.get_trading_hours(session, date)
```

**✅ ALWAYS check for None (holidays):**
```python
# CORRECT!
if trading_hours is None:
    # Market closed today
    return

# Safe to use
open_time = trading_hours.open_time
close_time = trading_hours.close_time
```

**✅ ALWAYS query fresh each time:**
```python
# CORRECT!
def calculate_something():
    # Query every time (don't cache)
    current_time = time_provider.get_current_time()
    # ... use current_time
```

## Changes Made

### 1. Removed Hardcoded Times from SessionData

**File:** `app/managers/data_manager/session_data.py`

**Before (Lines 196-197):**
```python
self.start_time: time = time(9, 30)  # ET
self.end_time: time = time(16, 0)    # ET
```

**After:**
```python
# NOTE: Do NOT store start_time/end_time here!
# Get trading hours from data_manager.get_trading_hours() instead.
# Single source of truth: data_manager queries trading calendar for
# accurate hours (accounts for holidays, early closes, etc.)
```

### 2. Updated Upkeep Thread (Quality Check)

**File:** `app/managers/data_manager/data_upkeep_thread.py`

**Before (Lines 237-241):**
```python
current_date = self._session_data.get_current_session_date()
session_start_time = datetime.combine(
    current_date,
    self._session_data.start_time  # Hardcoded!
)
```

**After (Lines 242-255):**
```python
current_date = current_time.date()

from app.models.database import AsyncSessionLocal
async with AsyncSessionLocal() as session:
    data_manager = self._system_manager.get_data_manager()
    trading_hours = await data_manager.get_trading_hours(session, current_date)
    
    if trading_hours is None:
        # Market closed today (holiday)
        return
    
    session_start_time = datetime.combine(current_date, trading_hours.open_time)
```

### 3. Updated Upkeep Thread (Gap Detection)

**File:** `app/managers/data_manager/data_upkeep_thread.py`

**Before (Lines 285-290):**
```python
current_date = self._session_data.get_current_session_date()
session_start_time = datetime.combine(
    current_date,
    self._session_data.start_time  # Hardcoded!
)
```

**After (Lines 290-303):**
```python
current_date = current_time.date()

from app.models.database import AsyncSessionLocal
async with AsyncSessionLocal() as session:
    data_manager = self._system_manager.get_data_manager()
    trading_hours = await data_manager.get_trading_hours(session, current_date)
    
    if trading_hours is None:
        # Market closed today (holiday)
        return
    
    session_start_time = datetime.combine(current_date, trading_hours.open_time)
```

## data_manager.get_trading_hours() Details

### Function Signature

```python
async def get_trading_hours(
    self,
    session: AsyncSession,
    day: date,
) -> Optional[DayTradingHours]:
    """Get concrete trading hours for a specific date.
    
    Returns None if the market is fully closed that day.
    Otherwise returns a DayTradingHours with open_time and close_time.
    """
```

### Return Values

```python
@dataclass
class DayTradingHours:
    """Concrete trading hours for a specific date."""
    open_time: time      # Market open (usually 9:30 AM ET)
    close_time: time     # Market close (4:00 PM or early close)
```

### Behavior

| Scenario | Returns | Example |
|----------|---------|---------|
| Regular trading day | `DayTradingHours(9:30, 16:00)` | Monday |
| Early close day | `DayTradingHours(9:30, 13:00)` | Day before Thanksgiving |
| Holiday (closed) | `None` | Thanksgiving, Christmas |

### Usage Example

```python
from app.models.database import AsyncSessionLocal
from datetime import date

async with AsyncSessionLocal() as session:
    data_manager = system_manager.get_data_manager()
    
    # Regular day
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 18))
    # Returns: DayTradingHours(open_time=time(9, 30), close_time=time(16, 0))
    
    # Early close (day before Thanksgiving)
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 27))
    # Returns: DayTradingHours(open_time=time(9, 30), close_time=time(13, 0))
    
    # Holiday (Thanksgiving)
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 28))
    # Returns: None
    
    if hours:
        print(f"Market open: {hours.open_time}")
        print(f"Market close: {hours.close_time}")
    else:
        print("Market closed today")
```

## Testing Scenarios

### Test 1: Regular Trading Day
```python
async def test_regular_day():
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 18))
    assert hours is not None
    assert hours.open_time == time(9, 30)
    assert hours.close_time == time(16, 0)
```

### Test 2: Early Close Day
```python
async def test_early_close():
    # Day before Thanksgiving
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 27))
    assert hours is not None
    assert hours.open_time == time(9, 30)
    assert hours.close_time == time(13, 0)  # 1:00 PM
```

### Test 3: Holiday (Closed)
```python
async def test_holiday():
    # Thanksgiving
    hours = await data_manager.get_trading_hours(session, date(2025, 11, 28))
    assert hours is None  # Market closed
```

## Migration Checklist

When refactoring code that uses times/dates:

- [ ] Remove hardcoded time values (`time(9, 30)`, `time(16, 0)`)
- [ ] Remove stored time attributes (`self.start_time`, `self.end_time`)
- [ ] Add query to `data_manager.get_trading_hours()` for trading hours
- [ ] Add query to `time_provider.get_current_time()` for current time
- [ ] Add `if trading_hours is None:` check for holidays
- [ ] Update tests to verify holiday/early close handling
- [ ] Document why querying from source is necessary

## Common Patterns

### Pattern 1: Get Session Start Time

**WRONG:**
```python
session_start = datetime.combine(date, time(9, 30))  # Hardcoded!
```

**CORRECT:**
```python
trading_hours = await data_manager.get_trading_hours(session, date)
if trading_hours:
    session_start = datetime.combine(date, trading_hours.open_time)
```

### Pattern 2: Get Session End Time

**WRONG:**
```python
session_end = datetime.combine(date, time(16, 0))  # Hardcoded!
```

**CORRECT:**
```python
trading_hours = await data_manager.get_trading_hours(session, date)
if trading_hours:
    session_end = datetime.combine(date, trading_hours.close_time)
```

### Pattern 3: Calculate Expected Minutes

**WRONG:**
```python
expected_minutes = 390  # Always assumes full day!
```

**CORRECT:**
```python
trading_hours = await data_manager.get_trading_hours(session, date)
if trading_hours:
    open_dt = datetime.combine(date, trading_hours.open_time)
    close_dt = datetime.combine(date, trading_hours.close_time)
    expected_minutes = int((close_dt - open_dt).total_seconds() / 60)
```

## Summary

✅ **Removed hardcoded times** from session_data
✅ **Query trading hours** from data_manager (trading calendar)
✅ **Handle holidays** (returns None)
✅ **Handle early closes** (returns correct close time)
✅ **Single source of truth** - consistent across system
✅ **Updated upkeep thread** - both quality check and gap detection
✅ **Created memory** - remember this pattern forever

**Result:** All time information now comes from authoritative sources with proper holiday/early close handling! 🎯
