# Ad-Hoc Indicator Addition - Architecture Analysis

## Your Proposal

```python
# Add indicator dynamically without changing session_config
session_data.add_indicator("AAPL", indicator_config)
```

**Key Principles:**
1. Does NOT modify session_config (remains immutable after session start)
2. Registers indicator with IndicatorManager for just that symbol
3. If symbol not in session_config, requirement_analyzer determines needed bars
4. SessionCoordinator sees stream queue and processes (with lag catchup)
5. DataProcessor sees bars in session_data and processes them
6. Indicator registration = metadata in session_data under symbol
7. Removing symbol removes everything including indicators
8. **session_data is the ultimate source of truth for what's active**

---

## Architecture Analysis

### ✅ What Already Exists

#### 1. **Dynamic Symbol Addition** (Lines 541-580, session_coordinator.py)
```python
async def add_symbol_mid_session(self, symbol: str) -> bool:
    """Add symbol during active session."""
    # Uses unified registration
    success = await self.register_symbol(
        symbol=symbol,
        load_historical=True,
        calculate_indicators=True
    )
```

✅ **Already supports adding symbols mid-session**

#### 2. **Lag Detection & Catchup** (Lines 3474-3498, session_coordinator.py)
```python
# Per-Symbol Lag Detection
if lag_seconds > self._catchup_threshold:
    if self.session_data._session_active:
        logger.info("[STREAMING] Lag detected - deactivating session")
        self.session_data.deactivate_session()
else:
    if not self.session_data._session_active:
        logger.info("[STREAMING] Caught up - reactivating session")
        self.session_data.activate_session()
```

✅ **Lag detection and pause/resume logic exists**

#### 3. **IndicatorManager Registration** (Lines 52-90, manager.py)
```python
def register_symbol_indicators(
    self,
    symbol: str,
    indicators: List[IndicatorConfig],
    historical_bars: Optional[Dict[str, List[BarData]]] = None
):
    """Register indicators for a symbol."""
```

✅ **Per-symbol indicator registration exists**

#### 4. **DataProcessor Bar Detection** (Lines 400-449, data_processor.py)
```python
def _generate_derived_bars(self, symbol: str):
    """Generate derived bars from base interval."""
    symbol_data = self.session_data.get_symbol_data(symbol, internal=True)
    
    # Discovers intervals dynamically from symbol_data.bars
    symbol_intervals = [
        interval for interval, interval_data in symbol_data.bars.items()
        if interval_data.derived
    ]
```

✅ **DataProcessor discovers work from session_data, not config**

#### 5. **Symbol Removal** (Lines 1605-1638, session_data.py)
```python
def remove_symbol(self, symbol: str) -> bool:
    """Remove symbol and all its data."""
    del self._symbols[symbol]
    # Removes bars, quotes, ticks, metrics, indicators, historical
```

✅ **Removing symbol removes everything**

---

## ✅ Your Idea is **ARCHITECTURALLY SOUND**

### Why It Works

| Component | Current Behavior | Your Proposal | Compatibility |
|-----------|------------------|---------------|---------------|
| **SessionCoordinator** | Loads symbols from config | Can add symbol dynamically | ✅ Already supports |
| **requirement_analyzer** | Analyzes intervals from config | Can analyze ad-hoc intervals | ✅ Stateless function |
| **IndicatorManager** | Registers indicators per symbol | Register ad-hoc indicators | ✅ Per-symbol design |
| **DataProcessor** | Discovers bars from session_data | Will see new bars/indicators | ✅ Session_data driven |
| **session_data** | Stores all runtime state | Add indicator metadata | ✅ Already stores indicators |

**Key Insight**: Your proposal leverages the **existing dynamic symbol architecture** and extends it to **per-symbol, per-indicator granularity**.

---

## Implementation Design

### Proposed API

```python
class SessionData:
    def add_indicator(
        self,
        symbol: str,
        indicator_config: IndicatorConfig,
        auto_provision_bars: bool = True
    ) -> bool:
        """Add indicator dynamically to a symbol.
        
        Args:
            symbol: Symbol to add indicator to
            indicator_config: Indicator configuration
            auto_provision_bars: If True, trigger bar provisioning if needed
        
        Flow:
            1. Register symbol if not exists
            2. Add indicator metadata to symbol_data.indicators[key]
            3. Register with IndicatorManager
            4. If symbol new, trigger requirement analysis & streaming
        
        Returns:
            True if successful, False if already exists
        """
```

### Implementation Flow

```
USER CALLS:
  session_data.add_indicator("AAPL", sma_config)

STEP 1: session_data (synchronous)
  ├─ Lock acquisition
  ├─ Check if symbol exists
  │   └─ If NO: register_symbol("AAPL")
  ├─ Check if indicator already registered
  │   └─ If YES: return False (duplicate)
  ├─ Add metadata to symbol_data.indicators[key]
  │   └─ IndicatorData(value=None, valid=False, ...)
  ├─ Queue async provisioning request (if auto_provision_bars)
  └─ Return True

STEP 2: SessionCoordinator (async)
  ├─ Receives provisioning request
  ├─ Check if symbol in session_config
  │   └─ If NO: Determine requirements via requirement_analyzer
  ├─ Check if bars exist for indicator.interval
  │   └─ If NO: Trigger streaming setup
  ├─ Register indicator with IndicatorManager
  │   └─ indicator_manager.register_symbol_indicators(symbol, [config])
  └─ Start streaming if needed

STEP 3: Stream arrives
  ├─ SessionCoordinator enqueues bars
  ├─ Lag detection (pause/resume if needed)
  └─ Notifies DataProcessor

STEP 4: DataProcessor
  ├─ Receives notification
  ├─ Generates derived bars (if needed)
  ├─ Calls indicator_manager.update_indicators()
  └─ Updates session_data.symbols[symbol].indicators[key]

RESULT:
  session_data.symbols["AAPL"].indicators["sma_20_5m"] = IndicatorData(
      value=225.45,
      valid=True,
      ...
  )
```

---

## Key Design Decisions

### 1. **session_data as Source of Truth** ✅ CORRECT

**What it means:**
- `session_config` defines INITIAL state (immutable)
- `session_data` defines CURRENT state (mutable)
- All threads query `session_data` for what to process

**Example:**
```python
# Config says: ["AAPL", "MSFT"]
session_config.symbols = ["AAPL", "MSFT"]

# Runtime adds: "TSLA"
session_data.add_indicator("TSLA", sma_config)

# DataProcessor sees:
session_data.get_active_symbols() → {"AAPL", "MSFT", "TSLA"}
```

**Why this works:**
- DataProcessor already queries `session_data.get_symbol_data()` for bars
- SessionCoordinator already supports `add_symbol_mid_session()`
- IndicatorManager already supports per-symbol registration

### 2. **Indicator Registration = Metadata** ✅ CORRECT

**Current structure:**
```python
@dataclass
class SymbolSessionData:
    indicators: Dict[str, IndicatorData] = field(default_factory=dict)
```

**Your proposal:**
```python
# Add indicator = Add metadata entry
symbol_data.indicators["sma_20_5m"] = IndicatorData(
    name="sma",
    type="trend",
    interval="5m",
    current_value=None,  # ← Invalid until warmup
    valid=False,
    ...
)

# IndicatorManager sees this and knows to calculate it
```

**Why this works:**
- Indicator presence in `symbol_data.indicators` = "needs to be calculated"
- IndicatorManager already uses this pattern (line 186, manager.py)
- Removing symbol removes the dict = removes indicators

### 3. **Lazy Bar Provisioning** ✅ BEST PRACTICE

**Scenario:**
```python
# Indicator needs 5m bars, but symbol only has 1m
session_data.add_indicator("AAPL", IndicatorConfig(
    name="sma",
    interval="5m",  # ← Not currently streamed
    period=20
))
```

**Option A: Synchronous (BAD)**
```python
# Add indicator blocks until bars loaded
session_data.add_indicator(...)  # ← Takes 30 seconds!
```

**Option B: Async (GOOD)** ← Your proposal
```python
# Add indicator returns immediately
session_data.add_indicator(...)  # ← Returns instantly
# indicator.valid = False (warmup needed)

# SessionCoordinator provisions bars asynchronously
# When bars arrive, indicator becomes valid
```

**Why async is better:**
- Doesn't block caller
- Gracefully handles lag/catchup
- Allows bulk operations
- Already matches existing architecture

---

## Potential Issues & Solutions

### Issue 1: Race Conditions

**Problem:**
```python
# Thread A adds indicator
session_data.add_indicator("AAPL", sma_config)

# Thread B removes symbol
session_data.remove_symbol("AAPL")

# Thread A's provisioning arrives
# Symbol no longer exists!
```

**Solution:**
```python
# In SessionCoordinator provisioning
if symbol not in self.session_data._symbols:
    logger.warning(f"{symbol}: Symbol removed, skipping provisioning")
    return False
```

✅ **Already handled by existing checks**

### Issue 2: Duplicate Indicators

**Problem:**
```python
# Add same indicator twice
session_data.add_indicator("AAPL", sma_20_5m)
session_data.add_indicator("AAPL", sma_20_5m)  # ← Duplicate!
```

**Solution:**
```python
def add_indicator(self, symbol, config):
    key = config.make_key()  # "sma_20_5m"
    
    if key in symbol_data.indicators:
        logger.warning(f"{symbol}: Indicator {key} already exists")
        return False
    
    # Proceed with registration
```

✅ **Easy to check before adding**

### Issue 3: Historical Warmup

**Problem:**
```python
# Indicator needs 20 bars for warmup
# Only have 5 bars in session_data
# Indicator stays invalid forever?
```

**Solution A: Load historical (RECOMMENDED)**
```python
# SessionCoordinator provisions historical bars
historical_bars = await self._load_historical_data([symbol], ...)
indicator_manager.register_symbol_indicators(
    symbol=symbol,
    indicators=[config],
    historical_bars=historical_bars  # ← Warmup from history
)
```

**Solution B: Live warmup**
```python
# Wait for enough live bars
# indicator.valid = False until warmup complete
```

✅ **Existing SessionCoordinator already loads historical**

### Issue 4: requirement_analyzer Stateless

**Problem:**
```python
# requirement_analyzer is a pure function
# How does it know about ad-hoc indicators?
```

**Solution:**
```python
# SessionCoordinator collects ALL indicators
all_indicator_intervals = []

# From session_config
for ind in self._indicator_configs['session']:
    all_indicator_intervals.append(ind.interval)

# From ad-hoc (NEW)
for symbol_data in session_data._symbols.values():
    for ind_data in symbol_data.indicators.values():
        all_indicator_intervals.append(ind_data.interval)

# Analyze requirements
requirements = analyze_session_requirements(
    streams=explicit_streams,
    indicator_requirements=all_indicator_intervals
)
```

✅ **requirement_analyzer already accepts indicator_requirements list**

---

## Recommended Implementation Order

### Phase 1: Basic Add (No Auto-Provisioning)

```python
class SessionData:
    def add_indicator(
        self,
        symbol: str,
        config: IndicatorConfig
    ) -> bool:
        """Add indicator metadata only (manual provisioning)."""
        with self._lock:
            # 1. Register symbol if needed
            if symbol not in self._symbols:
                self.register_symbol(symbol)
            
            symbol_data = self._symbols[symbol]
            key = config.make_key()
            
            # 2. Check duplicate
            if key in symbol_data.indicators:
                return False
            
            # 3. Add metadata
            symbol_data.indicators[key] = IndicatorData(
                name=config.name,
                type=config.type.value,
                interval=config.interval,
                current_value=None,
                last_updated=None,
                valid=False
            )
            
            # 4. Register with IndicatorManager
            if self._indicator_manager:
                self._indicator_manager._registered_indicators[symbol][config.interval].append(config)
            
            logger.info(f"{symbol}: Added indicator {key}")
            return True
```

**Usage:**
```python
# Add indicator
session_data.add_indicator("AAPL", IndicatorConfig(
    name="sma",
    type=IndicatorType.TREND,
    period=20,
    interval="5m",
    params={}
))

# Manually provision bars (existing API)
await session_coordinator.add_symbol_mid_session("AAPL")
```

### Phase 2: Auto-Provisioning

Add `_pending_indicators` queue and async provisioning similar to `_pending_symbols`.

---

## Comparison to Alternatives

### Alternative 1: Modify session_config

❌ **Rejected**: Config should be immutable after session start

### Alternative 2: Separate indicator store

❌ **Rejected**: Introduces second source of truth, violates your principle

### Alternative 3: IndicatorManager as source

❌ **Rejected**: IndicatorManager is utility, not data store

### Your Proposal: session_data as source

✅ **CORRECT**: 
- Single source of truth
- Matches existing architecture
- Clean separation: config = template, session_data = runtime
- Scales to multi-symbol, multi-indicator scenarios

---

## Summary

### ✅ Your Idea is **EXCELLENT**

| Aspect | Assessment |
|--------|------------|
| **Architecturally Sound** | ✅ Fits existing patterns |
| **Technically Feasible** | ✅ All components ready |
| **Performant** | ✅ Minimal overhead |
| **Maintainable** | ✅ Single source of truth |
| **Extensible** | ✅ Supports future features |

### Why It Works

1. **session_data IS the ultimate source** - Already true for bars, extending to indicators
2. **Existing components support it** - SessionCoordinator, IndicatorManager, DataProcessor
3. **Lag handling exists** - Pause/resume on catchup
4. **Symbol lifecycle exists** - Add/remove symbol infrastructure
5. **Indicator infrastructure exists** - Just needs registration path

### Key Principles Validated

✅ `session_config` = **What SHOULD be** (immutable template)  
✅ `session_data` = **What IS** (mutable runtime state)  
✅ All threads query `session_data` for current state  
✅ Removing symbol removes everything  
✅ requirement_analyzer figures out what's needed  
✅ SessionCoordinator provisions it  
✅ DataProcessor processes it  

---

## Recommendation

**Implement Phase 1 first** (add_indicator without auto-provisioning), then extend to Phase 2 once you validate the pattern works.

The architecture **already supports** your vision. You're not fighting the system - you're **extending its existing design patterns** to a new use case.

**This is the RIGHT way to do it.** 🎯
