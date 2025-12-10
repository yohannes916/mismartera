# Adhoc API & Scanner Framework - Final Summary

## The Complete Picture

```
┌──────────────────────────────────────────────────────────────┐
│                    SESSION ARCHITECTURE                       │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SESSION CONFIG (Immutable Template)                          │
│   symbols: ["AAPL", "MSFT"]  ← Static strategy symbols      │
│   streams: ["1m", "5m", "15m"]                               │
│   indicators: [20+ indicators]                               │
│   scanners: [gap_scanner, momentum_scanner, ...]             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ SESSION DATA (Mutable Runtime State) ← ULTIMATE SOURCE       │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ CONFIG SYMBOLS (Full-Featured)                         │ │
│ │   AAPL: {                                              │ │
│ │     bars: [1m, 5m, 15m, 1d]                            │ │
│ │     indicators: [sma_20_5m, ema_9_5m, rsi_14_5m, ...]  │ │
│ │     historical: 30 days                                │ │
│ │   }                                                    │ │
│ │   MSFT: { ... }                                        │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ SCANNER UNIVERSE (Lightweight Screening)               │ │
│ │   SPY: {                                               │ │
│ │     bars: [1d] only          ← Adhoc                   │ │
│ │     indicators: [sma_20_1d]  ← Minimal                 │ │
│ │     historical: 5 days       ← Short                   │ │
│ │   }                                                    │ │
│ │   ... (499 more symbols)                               │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ PROMOTED SYMBOLS (Scanner Findings → Full Strategy)    │ │
│ │   TSLA: {                                              │ │
│ │     bars: [1m, 5m, 15m, 1d]      ← UPGRADED            │ │
│ │     indicators: [20+ indicators]  ← FULL               │ │
│ │     historical: 30 days           ← EXTENSIVE          │ │
│ │     locked: true                  ← Position open      │ │
│ │   }                                                    │ │
│ └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## API Categories

### 1. Adhoc APIs (Lightweight - No Config Modification)

```python
# For scanner screening (500 symbols)
session_data.add_session_bars(symbol, interval)
session_data.add_historical_bars(symbol, interval, period)
session_data.add_indicator(symbol, type, config)
```

### 2. Symbol Management APIs (Full-Featured - Config Modification)

```python
# For strategy symbols (3-5 symbols)
session_data.add_symbol(symbol)        # IDEMPOTENT ✅
session_data.remove_symbol(symbol)     # Lock-protected ✅
session_data.lock_symbol(symbol, reason)
session_data.unlock_symbol(symbol)
session_data.is_symbol_locked(symbol)
```

---

## Scanner Flow (Complete Example)

### Step 1: Setup (Lightweight Provisioning)

```python
def setup(self, context):
    """Provision minimal data for 500 symbols."""
    
    for symbol in sp500_universe:
        # Adhoc APIs (lightweight)
        context.session_data.add_historical_bars(symbol, "1d", period=5)
        context.session_data.add_indicator(symbol, "sma", {
            "period": 20,
            "interval": "1d"
        })
    
    # Result: 500 symbols with minimal data
    # Cost: 500 × 5 bars × 1 indicator = 2,500 data points
```

### Step 2: Scan (Find & Upgrade)

```python
def scan(self, context):
    """Find qualifying symbols and upgrade to full."""
    
    results = []
    
    for symbol in self._universe:
        # Query adhoc data (lightweight)
        bar = context.session_data.get_latest_bar(symbol, "1d")
        sma = context.session_data.get_indicator(symbol, "sma_20_1d")
        
        # Apply criteria
        gap = ((bar.close - sma.value) / sma.value) * 100
        
        if gap >= 2.0:
            results.append(symbol)
            
            # UPGRADE to full strategy symbol
            # IDEMPOTENT - safe to call multiple times!
            context.session_data.add_symbol(symbol)
            # ↑ This triggers:
            #   - Add to session_config
            #   - Load ALL streams (1m, 5m, 15m, ...)
            #   - Load ALL indicators (20+)
            #   - Load FULL historical (30 days)
    
    return ScanResult(symbols=results)
```

### Step 3: Position Management (Lock/Unlock)

```python
class AnalysisEngine:
    def on_position_open(self, symbol):
        """Lock symbol when position opens."""
        self.session_data.lock_symbol(symbol, "open_position")
    
    def on_position_close(self, symbol):
        """Unlock symbol when position closes."""
        self.session_data.unlock_symbol(symbol)
```

---

## Resource Comparison

### Scanner Universe (Lightweight)

```
500 symbols × 5 days × 1 interval × 1 indicator
= 2,500 data points

Cost: LOW
Purpose: Fast screening
```

### Strategy Symbols (Full)

```
5 symbols × 30 days × 4 intervals × 20 indicators
= 12,000 data points

Cost: HIGH  
Purpose: Trading ready
```

**Total**: 14,500 data points (instead of 600,000 if all SP500 were full!)

---

## Idempotent add_symbol() - No State Tracking!

```python
# Scanner runs every 5 minutes
# Same symbol might qualify each time

# 09:35 - First scan
session_data.add_symbol("TSLA")  # ✅ TRUE - Newly added, triggers loading

# 09:40 - Second scan  
session_data.add_symbol("TSLA")  # ✅ FALSE - Already exists, IGNORED

# 09:45 - Third scan
session_data.add_symbol("TSLA")  # ✅ FALSE - Already exists, IGNORED

# No duplicate work!
# No state tracking needed!
# Scanner doesn't care!
```

---

## Lock Protection - Safe Removal

```python
# Add symbol
session_data.add_symbol("AAPL")  # ✅ Added

# Open position (lock)
session_data.lock_symbol("AAPL", "open_position")  # ✅ Locked

# Try to remove (BLOCKED)
session_data.remove_symbol("AAPL")  # ❌ FALSE - Locked!

# Close position (unlock)
session_data.unlock_symbol("AAPL")  # ✅ Unlocked

# Now can remove
session_data.remove_symbol("AAPL")  # ✅ TRUE - Removed
```

---

## Complete Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│ 1. SCANNER SETUP (Pre-session, ONCE)                     │
└────────────┬─────────────────────────────────────────────┘
             │
             ▼
    add_historical_bars() × 500 symbols
    add_indicator() × 500 symbols
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│ session_data: 500 symbols with minimal data              │
└────────────┬─────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│ 2. PRE-SESSION SCAN (Before trading, ONCE)               │
└────────────┬─────────────────────────────────────────────┘
             │
             ▼
    Scan 500 symbols (lightweight data)
    Find 3 qualifying: ["TSLA", "NVDA", "AMD"]
             │
             ▼
    add_symbol("TSLA")  ← Triggers full loading
    add_symbol("NVDA")  ← Triggers full loading
    add_symbol("AMD")   ← Triggers full loading
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│ session_data: 500 screening + 3 strategy symbols         │
└────────────┬─────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│ 3. SESSION START (Activate streaming)                    │
└────────────┬─────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│ 4. MID-SESSION SCANS (Every 5m)                          │
└────────────┬─────────────────────────────────────────────┘
             │
             ├─ 09:35: Find ["TSLA", "NVDA"]
             │    add_symbol("TSLA")   # Ignored (exists) ✅
             │    add_symbol("NVDA")   # Ignored (exists) ✅
             │
             ├─ 09:40: Find ["TSLA", "INTC"]
             │    add_symbol("TSLA")   # Ignored (exists) ✅
             │    add_symbol("INTC")   # New! Triggers load ✅
             │
             ├─ 09:45: Find ["TSLA", "NVDA", "AMD", "INTC"]
             │    add_symbol("TSLA")   # Ignored ✅
             │    add_symbol("NVDA")   # Ignored ✅
             │    add_symbol("AMD")    # Ignored ✅
             │    add_symbol("INTC")   # Ignored ✅
             │
             └─ ... continues
```

---

## Key Architectural Principles

### ✅ session_data is Ultimate Source
```
session_config  = WHAT SHOULD BE (template)
session_data    = WHAT IS (runtime state)

All threads query session_data, not config!
```

### ✅ Separation of Concerns
```
Adhoc APIs           = Lightweight screening (scanner universe)
Symbol Management    = Full-featured trading (strategy symbols)
```

### ✅ Idempotent Operations
```
add_symbol() safe to call repeatedly
No state tracking needed
No duplicate work
```

### ✅ Lock Protection
```
AnalysisEngine locks symbols with open positions
Cannot remove locked symbols
Clean lifecycle management
```

### ✅ Resource Efficiency
```
500 screening symbols: Minimal data (2,500 points)
5 strategy symbols: Full data (12,000 points)
Total: 14,500 instead of 600,000 ✅
```

---

## Implementation Checklist

### Phase 1: Adhoc APIs
- [ ] `add_session_bars(symbol, interval)`
- [ ] `add_historical_bars(symbol, interval, period)`
- [ ] `add_indicator(symbol, type, config)`

### Phase 2: Symbol Management
- [ ] `add_symbol(symbol)` with idempotent logic
- [ ] `remove_symbol(symbol)` with lock check
- [ ] `lock_symbol(symbol, reason)`
- [ ] `unlock_symbol(symbol)`
- [ ] `is_symbol_locked(symbol)`

### Phase 3: Scanner Integration
- [ ] ScannerManager loads scanners
- [ ] ScannerManager.setup_all() calls scanner.setup()
- [ ] ScannerManager.execute_scans() calls scanner.scan()
- [ ] Scanner uses adhoc APIs for screening
- [ ] Scanner uses add_symbol() for promotion

### Phase 4: Testing
- [ ] Test adhoc APIs with single symbol
- [ ] Test add_symbol() idempotency
- [ ] Test lock/unlock protection
- [ ] Test scanner with small universe (10 symbols)
- [ ] Test scanner with large universe (500 symbols)
- [ ] Test position management integration

---

## Files Created

1. **`ADHOC_API_DESIGN.md`** - Complete API specifications
2. **`scanners/examples/gap_scanner_complete.py`** - Full scanner example
3. **`ADHOC_API_SUMMARY.md`** - This summary (overview)

---

## Ready to Implement! 🎯

All design work complete:
- ✅ Clean API separation
- ✅ Idempotent operations
- ✅ Lock protection
- ✅ Resource efficient
- ✅ Stateless scanners
- ✅ Complete examples

Next step: Start implementing Phase 1 (Adhoc APIs)!
