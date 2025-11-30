# Repositories Organization Plan

**Date:** 2025-11-29  
**Status:** 📋 PLANNED

---

## Current State

### Existing Repositories

**Top-level app/repositories/:**
- `trading_calendar_repository.py` - ❌ ASYNC (old, should replace with sync)
- `user_repository.py` - Need to check (async or sync?)

**Manager-specific repositories:**
- `app/managers/time_manager/repositories/trading_calendar_repo.py` - ✅ SYNC
- `app/managers/data_manager/repositories/` - Empty (__init__.py only)
- `app/managers/execution_manager/repositories/` - Empty (__init__.py only)
- `app/managers/analysis_engine/repositories/` - Empty (__init__.py only)

---

## Issues

1. **Duplicate TradingCalendarRepository**
   - app/repositories/trading_calendar_repository.py (ASYNC - old)
   - app/managers/time_manager/repositories/trading_calendar_repo.py (SYNC - correct)

2. **Scattered Locations**
   - Some in app/repositories/
   - Some in app/managers/*/repositories/

3. **Async vs Sync**
   - Architecture requires SYNC (SessionLocal, NOT AsyncSession)
   - Old async repositories should be removed/replaced

---

## Decision: Keep Manager-Specific Repositories

**Rationale:**
- TimeManager uses trading calendar repository (tightly coupled)
- DataManager may use bar/tick/quote repositories (tightly coupled)
- ExecutionManager may use order/position repositories (tightly coupled)
- Better encapsulation - manager owns its data access

**Pattern:**
```
app/managers/time_manager/
├── api.py                   # TimeManager class
├── repositories/            # Time-specific repositories
│   ├── __init__.py
│   └── trading_calendar_repo.py
```

---

## Reorganization Plan

### Option A: Keep Current Structure (RECOMMENDED)

**Keep repositories within manager packages:**
- ✅ Better encapsulation
- ✅ Clear ownership
- ✅ Easier to maintain
- ✅ Already matches current architecture

**Action Items:**
1. ✅ Keep `app/managers/time_manager/repositories/`
2. ❌ Delete `app/repositories/trading_calendar_repository.py` (old async version)
3. ✅ Keep `app/repositories/user_repository.py` (if used by auth/API layer)
4. ✅ Document pattern in ARCHITECTURE.md

### Option B: Move All to Top-Level

**Move all repositories to `app/repositories/`:**
- ❌ Less clear ownership
- ❌ Breaks encapsulation
- ❌ Requires more import updates
- ❌ Doesn't match our layered architecture

**NOT RECOMMENDED**

---

## Recommended Actions

### 1. Keep Manager Repositories

No changes needed. Current structure is correct:
```
app/managers/time_manager/repositories/
app/managers/data_manager/repositories/
app/managers/execution_manager/repositories/
app/managers/analysis_engine/repositories/
```

### 2. Top-Level app/repositories/

**Use for shared/cross-cutting repositories only:**
```
app/repositories/
├── __init__.py
└── user_repository.py       # Used by auth, not manager-specific
```

### 3. Delete Old Async Repository

```bash
# Remove old async version
rm app/repositories/trading_calendar_repository.py
```

### 4. Update ARCHITECTURE.md

Document repository organization pattern:

```markdown
## Repository Organization

Repositories are organized by their owning manager:

- **Manager-Specific**: `app/managers/{manager}/repositories/`
  - TimeManager → trading_calendar_repo.py
  - DataManager → bar_repo.py, tick_repo.py
  - ExecutionManager → order_repo.py, position_repo.py

- **Shared**: `app/repositories/`
  - user_repository.py (used by auth)
  - Other cross-cutting repositories

All repositories use synchronous `SessionLocal`, NOT `AsyncSession`.
```

---

## Verification

### Check Repository Pattern

```python
# ✅ CORRECT - Sync repository in manager package
from app.managers.time_manager.repositories.trading_calendar_repo import TradingCalendarRepository
from app.models.database import SessionLocal

with SessionLocal() as session:
    holidays = TradingCalendarRepository.get_holidays(session, exchange="NYSE")

# ❌ WRONG - Async repository
from app.repositories.trading_calendar_repository import TradingCalendarRepository
from app.models.database import AsyncSessionLocal  # ❌ Don't use async!

async with AsyncSessionLocal() as session:
    holidays = await TradingCalendarRepository.get_holidays(session)
```

---

## Status

**Decision:** Keep current manager-specific repository structure (Option A)

**Actions:**
- ✅ Keep manager repositories as-is
- 📋 Delete old async trading_calendar_repository.py
- 📋 Document pattern in ARCHITECTURE.md
- 📋 Verify user_repository.py is sync

---

## Next Steps

1. Verify `user_repository.py` is synchronous
2. Delete `app/repositories/trading_calendar_repository.py`
3. Document repository pattern in ARCHITECTURE.md
4. Move on to services organization
