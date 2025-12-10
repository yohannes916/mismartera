# Session Lifecycle and Indicator Persistence

## When is `reset_session_metrics()` Called?

### Answer: BETWEEN Sessions (NOT Initially)

`reset_session_metrics()` is **NEVER called during initial setup**. It's only called **BETWEEN trading sessions** in multi-day backtests.

## Multi-Day Backtest Lifecycle

### First Day (Day 1)
```
1. _coordinator_loop() starts
2. PHASE 1: _initialize_session()
   - Validates streams (FIRST TIME ONLY)
   - Does NOT call reset_session_metrics
3. PHASE 2: _manage_historical_data()
   - PRE-REGISTERS symbols: session_data.register_symbol()
   - Loads historical bars
   - Calculates historical indicators
4. (Implicit) register_symbol() called for each symbol
   - Creates SymbolSessionData with indicators = {}
5. _register_symbol_indicators() called
   - Populates symbol_data.indicators with IndicatorData objects ✅
6. PHASE 3-5: Queue loading, activation, streaming
7. PHASE 6: _end_session()
   - session_data.clear_session_bars() ← Clears bars only
   - Advances to next trading day
```

### Between Days (Day 1 → Day 2)
```
_end_session() from Day 1:
  1. session_data.clear_session_bars()
     - Clears ALL bar intervals (symbol_data.bars)
     - Calls reset_session_metrics() ← THIS IS WHERE IT HAPPENS!
  2. Advances time to next trading day

reset_session_metrics() called:
  - Clears session metrics
  - WAS INCORRECTLY clearing indicators = {} ← THE BUG!
  - NOW CORRECTLY resets only indicator VALUES
```

### Second Day (Day 2)
```
1. Loop continues (doesn't restart)
2. PHASE 1: _initialize_session()
   - Skips stream validation (already done)
3. PHASE 2: _manage_historical_data()
   - Symbols ALREADY registered (from Day 1)
   - Loads new historical bars
   - Does NOT re-register indicators ← Key point!
4. PHASE 3-5: Queue loading, activation, streaming
5. PHASE 6: _end_session()
   - Clears bars, advances to Day 3
```

## What Persists vs What Clears?

### ✅ PERSISTS Across Sessions
These are **CONFIGURATION** - set once, never deleted:

1. **Symbols** (`session_data._symbols`)
   - Registered ONCE on first day
   - NOT cleared between sessions
   
2. **Indicators** (`symbol_data.indicators`)
   - Registered ONCE on first day
   - Structures persist (IndicatorData objects)
   - Only VALUES reset (current_value, valid, last_updated)

3. **Derived Interval Configs** (`symbol_data.bars` structure)
   - Interval keys persist (1m, 5m, 15m)
   - Only bar DATA cleared

4. **Historical Data** (`symbol_data.historical`)
   - Kept across sessions
   - Rolling window (trailing_days)

### ❌ CLEARS Between Sessions
These are **RUNTIME DATA** - cleared each day:

1. **Session Bars** (`symbol_data.bars[interval].data`)
   - All intervals (1m, 5m, derived) → `data.clear()`
   
2. **Quotes/Ticks** 
   - Cleared each session

3. **Session Metrics** (`symbol_data.metrics`)
   - Volume, high, low reset to defaults

4. **Indicator VALUES** (after fix)
   - `current_value` → None
   - `valid` → False
   - `last_updated` → None
   - Config/state PERSIST

## The clear_session_bars() Flow

```python
def clear_session_bars(self) -> None:
    """Called at end of each session."""
    for symbol, symbol_data in self._symbols.items():
        # 1. Clear bar data (all intervals)
        for interval_data in symbol_data.bars.values():
            interval_data.data.clear()  # Clear deque
            interval_data.updated = False
        
        # 2. Reset latest bar cache
        symbol_data._latest_bar = None
        
        # Note: Does NOT call reset_session_metrics here
```

This is called from `_end_session()` in session_coordinator.py line 2420.

## Where reset_session_metrics() is Actually Called

**File**: `session_data.py`

### Call Site 1: roll_session() (line 1646)
```python
def roll_session(self, new_session_date: date) -> None:
    """Move current to historical, clear current."""
    for symbol_data in self._symbols.values():
        # Move bars to historical
        # ...
        # Clear current
        for interval_data in symbol_data.bars.values():
            interval_data.data.clear()
        
        symbol_data.quotes.clear()
        symbol_data.ticks.clear()
        symbol_data.reset_session_metrics()  # ← HERE
```

**Status**: Currently NOT USED (no code calls `roll_session()`)

### Call Site 2: reset_session() (line 1674)
```python
def reset_session(self) -> None:
    """Clear session data but keep symbols."""
    for symbol_data in self._symbols.values():
        # Clear bars
        for interval_data in symbol_data.bars.values():
            interval_data.data.clear()
        
        symbol_data.quotes.clear()
        symbol_data.ticks.clear()
        symbol_data.reset_session_metrics()  # ← HERE
```

**Status**: Currently NOT USED (no code calls `reset_session()`)

### ❗ACTUAL Issue
The calls in `roll_session()` and `reset_session()` are **NOT actually being invoked** currently! 

Let me verify where it's REALLY called...

## Actually, Looking at clear_session_bars()

```python
def clear_session_bars(self) -> None:
    """Clear current session bars (not historical)."""
    for symbol, symbol_data in self._symbols.items():
        # Clear all bar intervals
        for interval_data in symbol_data.bars.values():
            interval_data.data.clear()
            interval_data.updated = False
        
        symbol_data._latest_bar = None
        # Does NOT call reset_session_metrics!
```

**Wait!** `clear_session_bars()` does NOT call `reset_session_metrics()`!

So when IS it called? Let me trace back...

## The Real Issue

Looking at the code:
- `_end_session()` calls `clear_session_bars()` (line 2420)
- `clear_session_bars()` does NOT call `reset_session_metrics()`
- `roll_session()` and `reset_session()` are NEVER called

**This means `reset_session_metrics()` is NEVER called in current code!**

But your JSON is still empty... which means:

## The ACTUAL Problem

If `reset_session_metrics()` isn't being called, then indicators should persist. The fact that they're empty means:

1. **Indicators ARE being registered** (logs confirm this)
2. **But they're not appearing in JSON**

This suggests either:
- Registration happens AFTER first `clear_session_bars()`
- OR the JSON export happens too early
- OR there's another place clearing indicators

Let me check when indicator registration happens relative to session lifecycle...

## Registration Timing

From `_manage_historical_data()` (Phase 2):
```python
# PRE-REGISTER symbols
for symbol in symbols_to_process:
    if symbol not in self.session_data._symbols:
        self.session_data.register_symbol(symbol)  # Creates empty indicators = {}
```

**Problem**: `register_symbol()` creates `SymbolSessionData` with empty `indicators = {}`

Then later, `_register_symbol_indicators()` would populate it... but WHERE is that called?

From `register_symbol()` unified routine (lines 303-308):
```python
# 4. Register indicators (unified)
if calculate_indicators:
    self._register_symbol_indicators(
        symbol=symbol,
        historical_bars=historical_bars
    )
```

But is this being called during `_manage_historical_data()`? No! It's not!

## The REAL Root Cause

**`_manage_historical_data()` only PRE-REGISTERS symbols**, it does NOT call the full `register_symbol()` routine!

```python
# In _manage_historical_data()
for symbol in symbols_to_process:
    if symbol not in self.session_data._symbols:
        self.session_data.register_symbol(symbol)  # ← Creates SymbolSessionData
        # But does NOT call register_symbol() from session_coordinator!
```

So indicators are NEVER registered because the unified `register_symbol()` method (with `calculate_indicators=True`) is never called during the session lifecycle!

This is the real bug - not `reset_session_metrics()`.
