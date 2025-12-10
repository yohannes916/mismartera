# Adhoc API - Quick Reference Card

## API Signatures

### Adhoc Data APIs (Lightweight)

```python
# Add real-time/intraday bars (no historical)
session_data.add_session_bars(
    symbol: str,
    interval: str
) → bool

# Add historical bars for warmup
session_data.add_historical_bars(
    symbol: str,
    interval: str,
    period: int  # days
) → bool

# Add indicator
session_data.add_indicator(
    symbol: str,
    indicator_type: str,  # "sma", "rsi", etc.
    config: dict  # {"period": 20, "interval": "1d", "params": {}}
) → bool
```

### Symbol Management APIs (Full-Featured)

```python
# Add full strategy symbol (IDEMPOTENT)
session_data.add_symbol(
    symbol: str
) → bool  # True if new, False if exists

# Remove symbol (lock-protected)
session_data.remove_symbol(
    symbol: str
) → bool  # True if removed, False if locked/not found

# Lock symbol (prevent removal)
session_data.lock_symbol(
    symbol: str,
    reason: str  # "open_position", "pending_order", etc.
) → bool

# Unlock symbol
session_data.unlock_symbol(
    symbol: str
) → bool

# Check if locked
session_data.is_symbol_locked(
    symbol: str
) → bool
```

---

## Usage Patterns

### Scanner Setup (Lightweight)

```python
# Provision 500 symbols with minimal data
for symbol in sp500:
    session_data.add_historical_bars(symbol, "1d", period=5)
    session_data.add_indicator(symbol, "sma", {
        "period": 20,
        "interval": "1d"
    })
```

### Scanner Scan (Promote)

```python
# Find and promote qualifying symbols
for symbol in universe:
    bar = session_data.get_latest_bar(symbol, "1d")
    sma = session_data.get_indicator(symbol, "sma_20_1d")
    
    if meets_criteria(bar, sma):
        # Upgrade to full symbol (idempotent)
        session_data.add_symbol(symbol)  # Can call repeatedly ✅
```

### Position Management

```python
# Lock when opening position
def on_position_open(symbol):
    session_data.lock_symbol(symbol, "open_position")

# Unlock when closing position
def on_position_close(symbol):
    session_data.unlock_symbol(symbol)

# Try to clean up
def cleanup_unused_symbols():
    for symbol in session_data.get_active_symbols():
        if not analysis_engine.has_position(symbol):
            session_data.remove_symbol(symbol)  # Fails if locked ✅
```

---

## What Triggers What

### add_session_bars()
```
✓ Registers symbol (if needed)
✓ Adds interval structure
✓ Starts streaming queue
✗ Does NOT load historical
✗ Does NOT trigger session_config
```

### add_historical_bars()
```
✓ Registers symbol (if needed)
✓ Queues historical load
✓ Loads N days of history
✗ Does NOT start streaming
✗ Does NOT trigger session_config
```

### add_indicator()
```
✓ Registers symbol (if needed)
✓ Creates indicator metadata
✓ Registers with IndicatorManager
✓ Calculates when bars available
✗ Does NOT load bars
✗ Does NOT trigger session_config
```

### add_symbol()
```
✓ Adds to session_config.symbols
✓ Calls SessionCoordinator.add_symbol_mid_session()
✓ Loads ALL streams from config
✓ Loads ALL indicators from config
✓ Loads FULL historical from config
✓ Registers with AnalysisEngine
✓ IDEMPOTENT (safe to call multiple times)
```

### remove_symbol()
```
✓ Checks lock status (fails if locked)
✓ Removes from session_config
✓ Removes from session_data
✓ Cleans up ALL data (bars, indicators, historical)
✗ Does NOT remove if locked
```

---

## Return Values

| API | Returns True | Returns False |
|-----|-------------|---------------|
| `add_session_bars()` | New interval added | Already exists |
| `add_historical_bars()` | Queued for loading | Already exists |
| `add_indicator()` | New indicator added | Already exists |
| `add_symbol()` | Newly added | Already exists (IDEMPOTENT ✅) |
| `remove_symbol()` | Successfully removed | Locked or not found |
| `lock_symbol()` | Successfully locked | - |
| `unlock_symbol()` | Successfully unlocked | Not locked |
| `is_symbol_locked()` | Is locked | Not locked |

---

## Common Patterns

### Pattern 1: Scanner Screening

```python
# Setup (ONCE)
for symbol in universe:
    add_historical_bars(symbol, "1d", 5)
    add_indicator(symbol, "sma", {...})

# Scan (PERIODIC)
for symbol in universe:
    if meets_criteria(...):
        add_symbol(symbol)  # Idempotent ✅
```

### Pattern 2: Dynamic Indicator

```python
# Analysis engine wants custom indicator
add_session_bars("AAPL", "1m")
add_indicator("AAPL", "custom_rsi", {
    "period": 14,
    "interval": "1m"
})
```

### Pattern 3: Protected Removal

```python
# Open position
lock_symbol("AAPL", "open_position")

# Later: Try to clean up
if not is_symbol_locked("AAPL"):
    remove_symbol("AAPL")  # Safe ✅
```

---

## Error Handling

```python
# Idempotent (no errors on duplicates)
if session_data.add_symbol("AAPL"):
    print("Added")
else:
    print("Already exists")  # Not an error ✅

# Lock-protected (returns False if locked)
if session_data.remove_symbol("AAPL"):
    print("Removed")
else:
    print("Locked or not found")  # Not an error ✅

# Adhoc (returns False if exists)
if session_data.add_indicator("AAPL", "sma", {...}):
    print("Added")
else:
    print("Already exists")  # Not an error ✅
```

---

## Resource Costs

| Operation | Cost | Use Case |
|-----------|------|----------|
| `add_session_bars("AAPL", "1m")` | Low | Live bars only, no history |
| `add_historical_bars("AAPL", "1d", 5)` | Low | 5 days × 1 interval |
| `add_indicator("AAPL", "sma", {...})` | Low | 1 indicator |
| `add_symbol("AAPL")` | **HIGH** | All streams + all indicators + full history |

**Strategy**: Use adhoc APIs for screening (cheap), `add_symbol()` for trading (expensive).

---

## Best Practices

### ✅ DO

- Use adhoc APIs for scanner universe (500 symbols)
- Use `add_symbol()` for strategy symbols (3-5 symbols)
- Call `add_symbol()` repeatedly (idempotent)
- Lock symbols with open positions
- Check lock before removing

### ❌ DON'T

- Don't call `add_symbol()` for entire universe (expensive!)
- Don't track state in scanner (idempotent handles it)
- Don't remove symbols with positions (lock prevents it)
- Don't use adhoc APIs for strategy symbols (use `add_symbol()`)

---

## Complete Example

```python
class GapScanner:
    def setup(self, context):
        # Lightweight: 500 symbols
        for symbol in sp500:
            context.session_data.add_historical_bars(symbol, "1d", 5)
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20, "interval": "1d"
            })
    
    def scan(self, context):
        results = []
        
        for symbol in sp500:
            bar = context.session_data.get_latest_bar(symbol, "1d")
            sma = context.session_data.get_indicator(symbol, "sma_20_1d")
            
            if bar and sma and sma.valid:
                gap = ((bar.close - sma.value) / sma.value) * 100
                
                if gap >= 2.0:
                    results.append(symbol)
                    
                    # Promote to full symbol (idempotent)
                    context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)


class AnalysisEngine:
    def on_position_open(self, symbol):
        self.session_data.lock_symbol(symbol, "open_position")
    
    def on_position_close(self, symbol):
        self.session_data.unlock_symbol(symbol)
```

---

## Quick Decision Tree

```
Need to screen large universe (500+ symbols)?
├─ YES → Use adhoc APIs
│         add_historical_bars()
│         add_indicator()
│
└─ NO → Need full symbol for trading?
        ├─ YES → Use add_symbol()
        │
        └─ NO → Need custom data?
                └─ Use adhoc APIs
                          add_session_bars()
                          add_indicator()
```

---

**That's it! Simple, clean, efficient.** 🎯
