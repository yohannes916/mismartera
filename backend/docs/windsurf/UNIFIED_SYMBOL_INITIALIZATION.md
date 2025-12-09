# Unified Symbol Initialization Design

**Date**: December 7, 2025  
**Status**: ✅ DESIGN COMPLETE  
**Goal**: Single parameterized routine for pre-session and mid-session symbol initialization

---

## **Design Principles**

### **1. Unified Routine** ✅
- Same function for pre-session and mid-session
- Parameterized for any symbol, any time
- No duplicate code paths

### **2. Clean Break** ✅
- No legacy code
- No special cases
- Consistent behavior

### **3. Interval Support** ✅
- Works for all intervals: seconds, minutes, days, weeks
- No hourly support
- Unified aggregation logic

### **4. Indicator Integration** ✅
- Registers indicators automatically
- Loads historical data for warmup
- Works for any indicator configuration

---

## **Unified Symbol Registration Flow**

```
┌─────────────────────────────────────────────────────────┐
│         UNIFIED SYMBOL REGISTRATION                      │
│  (Used by both pre-session and mid-session)             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │  1. Determine Requirements      │
        │  (requirement_analyzer)         │
        │  - Base interval                │
        │  - Derived intervals            │
        │  - Historical days needed       │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  2. Load Historical Data        │
        │  (if needed for warmup)         │
        │  - Load base interval bars      │
        │  - Generate derived bars        │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  3. Register with SessionData   │
        │  - Create SymbolSessionData     │
        │  - Store historical bars        │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  4. Register Indicators         │
        │  (indicator_manager)            │
        │  - Session indicators           │
        │  - Historical indicators        │
        │  - Calculate with warmup        │
        └────────────┬────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────────┐
        │  5. Start Streaming             │
        │  (if mid-session)               │
        │  - Add to stream queues         │
        │  - Continue bar processing      │
        └─────────────────────────────────┘
```

---

## **Implementation: Unified Registration Method**

### **Location**: `SessionCoordinator`

```python
async def register_symbol(
    self,
    symbol: str,
    load_historical: bool = True,
    calculate_indicators: bool = True
) -> bool:
    """Register symbol with unified routine.
    
    This single method handles:
    - Pre-session initialization (during coordinator startup)
    - Mid-session insertion (dynamic symbol addition)
    
    Args:
        symbol: Symbol to register
        load_historical: Load historical bars for warmup
        calculate_indicators: Register and calculate indicators
        
    Returns:
        True if successful
        
    Design:
        - Parameterized for reuse
        - Works for all intervals (s, m, d, w)
        - Uses requirement_analyzer for consistency
        - No special cases for pre vs mid-session
    """
    try:
        logger.info(f"{symbol}: Registering symbol (unified routine)")
        
        # 1. Determine requirements (unified)
        requirements = await self._determine_symbol_requirements(symbol)
        
        # 2. Load historical data (unified)
        historical_bars = {}
        if load_historical and requirements.needs_historical:
            historical_bars = await self._load_historical_bars(
                symbol=symbol,
                requirements=requirements
            )
        
        # 3. Register with SessionData (unified)
        self._register_symbol_data(
            symbol=symbol,
            requirements=requirements,
            historical_bars=historical_bars
        )
        
        # 4. Register indicators (unified)
        if calculate_indicators:
            self._register_symbol_indicators(
                symbol=symbol,
                historical_bars=historical_bars
            )
        
        # 5. Log success
        logger.info(
            f"{symbol}: Registration complete "
            f"(base: {requirements.base_interval}, "
            f"derived: {len(requirements.derived_intervals)})"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"{symbol}: Registration failed: {e}", exc_info=True)
        return False
```

---

## **Supporting Methods**

### **1. Determine Requirements**

```python
async def _determine_symbol_requirements(
    self,
    symbol: str
) -> SymbolRequirements:
    """Determine what's needed for this symbol.
    
    Uses requirement_analyzer to determine:
    - Base interval (1s, 1m, 1d)
    - Derived intervals (5m, 15m, 1w, etc.)
    - Historical days needed (for indicators)
    
    Returns:
        SymbolRequirements with all necessary info
    """
    from app.threads.quality.requirement_analyzer import analyze_session_requirements
    
    # Get all intervals needed (streams + indicators)
    all_intervals = set(self._streams)
    
    # Add indicator intervals
    for ind in self._indicator_configs['session']:
        all_intervals.add(ind.interval)
    for ind in self._indicator_configs['historical']:
        all_intervals.add(ind.interval)
    
    # Analyze requirements
    requirements = analyze_session_requirements(
        streams=list(all_intervals)
    )
    
    # Determine historical days needed
    max_historical_days = self._calculate_max_historical_days()
    
    return SymbolRequirements(
        symbol=symbol,
        base_interval=requirements.required_base_interval,
        derived_intervals=requirements.derivable_intervals,
        historical_days=max_historical_days,
        needs_historical=(max_historical_days > 0)
    )
```

### **2. Load Historical Bars**

```python
async def _load_historical_bars(
    self,
    symbol: str,
    requirements: SymbolRequirements
) -> Dict[str, List[BarData]]:
    """Load historical bars for symbol.
    
    Unified method that:
    - Loads base interval from parquet
    - Generates derived intervals
    - Works for all intervals (s, m, d, w)
    
    Args:
        symbol: Symbol to load
        requirements: Requirements from analyzer
        
    Returns:
        Dict of {interval: [bars]}
    """
    from app.managers.data_manager.derived_bars import compute_all_derived_intervals
    
    historical_bars = {}
    
    # Load base interval
    base_interval = requirements.base_interval
    base_bars = await self._data_manager.load_historical_bars(
        symbol=symbol,
        interval=base_interval,
        days=requirements.historical_days
    )
    
    if base_bars:
        historical_bars[base_interval] = base_bars
        logger.debug(
            f"{symbol}: Loaded {len(base_bars)} {base_interval} bars "
            f"({requirements.historical_days} days)"
        )
        
        # Generate derived intervals
        if requirements.derived_intervals:
            derived_data = compute_all_derived_intervals(
                base_bars=base_bars,
                base_interval=base_interval,
                target_intervals=requirements.derived_intervals
            )
            
            for interval, bars in derived_data.items():
                historical_bars[interval] = bars
                logger.debug(
                    f"{symbol}: Generated {len(bars)} {interval} bars "
                    f"from {base_interval}"
                )
    
    return historical_bars
```

### **3. Register Symbol Data**

```python
def _register_symbol_data(
    self,
    symbol: str,
    requirements: SymbolRequirements,
    historical_bars: Dict[str, List[BarData]]
):
    """Register symbol with SessionData.
    
    Creates SymbolSessionData and stores historical bars.
    
    Args:
        symbol: Symbol to register
        requirements: Requirements from analyzer
        historical_bars: Pre-loaded historical bars
    """
    from app.managers.data_manager.session_data import (
        SymbolSessionData,
        BarIntervalData
    )
    from collections import deque
    
    # Create symbol data
    symbol_data = SymbolSessionData(
        symbol=symbol,
        base_interval=requirements.base_interval
    )
    
    # Store historical bars
    for interval, bars in historical_bars.items():
        is_base = (interval == requirements.base_interval)
        
        symbol_data.bars[interval] = BarIntervalData(
            derived=(not is_base),
            base=requirements.base_interval if not is_base else None,
            data=deque(bars)  # Use deque for efficient append
        )
    
    # Register with SessionData
    self.session_data.register_symbol(symbol_data)
    
    logger.debug(
        f"{symbol}: Registered in SessionData with {len(historical_bars)} intervals"
    )
```

### **4. Register Indicators**

```python
def _register_symbol_indicators(
    self,
    symbol: str,
    historical_bars: Dict[str, List[BarData]]
):
    """Register indicators for symbol.
    
    Uses IndicatorManager to register all indicators.
    Historical bars used for warmup.
    
    Args:
        symbol: Symbol to register indicators for
        historical_bars: Pre-loaded bars for warmup
    """
    # Combine session + historical indicators
    all_indicators = (
        self._indicator_configs['session'] +
        self._indicator_configs['historical']
    )
    
    if not all_indicators:
        return  # No indicators configured
    
    # Register with indicator manager
    self.indicator_manager.register_symbol_indicators(
        symbol=symbol,
        indicators=all_indicators,
        historical_bars=historical_bars  # For warmup
    )
    
    indicator_count = len(all_indicators)
    ready_count = sum(
        1 for ind in all_indicators
        if self._is_indicator_ready(symbol, ind)
    )
    
    logger.info(
        f"{symbol}: Registered {indicator_count} indicators "
        f"({ready_count} ready after warmup)"
    )
```

---

## **Usage Patterns**

### **Pre-Session (Batch Registration)**

```python
async def _initialize_all_symbols(self):
    """Initialize all symbols at session start."""
    
    # Batch register all symbols (unified routine)
    for symbol in self._symbols:
        success = await self.register_symbol(
            symbol=symbol,
            load_historical=True,
            calculate_indicators=True
        )
        
        if not success:
            logger.error(f"{symbol}: Failed to register")
```

### **Mid-Session (Dynamic Insertion)**

```python
async def add_symbol_mid_session(self, symbol: str) -> bool:
    """Add symbol during active session.
    
    Uses SAME unified routine as pre-session!
    
    Args:
        symbol: Symbol to add
        
    Returns:
        True if successful
    """
    # Validate not already registered
    if self.session_data.get_symbol_data(symbol):
        logger.warning(f"{symbol}: Already registered")
        return False
    
    # Use unified registration (SAME CODE!)
    success = await self.register_symbol(
        symbol=symbol,
        load_historical=True,  # Need historical for indicator warmup
        calculate_indicators=True
    )
    
    if success:
        # Start streaming for this symbol
        await self._start_symbol_streaming(symbol)
        logger.info(f"{symbol}: Added mid-session successfully")
    
    return success
```

---

## **Data Classes**

```python
@dataclass
class SymbolRequirements:
    """Requirements for a symbol."""
    symbol: str
    base_interval: str              # e.g., "1m"
    derived_intervals: List[str]    # e.g., ["5m", "15m", "1d"]
    historical_days: int            # Days of historical data needed
    needs_historical: bool          # True if historical needed
```

---

## **Benefits of Unified Approach**

### **1. Code Reuse** ✅
- Single registration function
- No duplicate logic
- Easier to maintain

### **2. Consistency** ✅
- Same behavior pre-session and mid-session
- Same validation
- Same error handling

### **3. Interval Support** ✅
- Works for all intervals (s, m, d, w)
- No special cases
- Unified aggregation

### **4. Testability** ✅
- Single function to test
- Predictable behavior
- Easy to verify

### **5. Extensibility** ✅
- Easy to add new intervals
- Easy to add new requirements
- Clean interface

---

## **Validation**

### **Pre-Session Test**:
```python
# Register 3 symbols at startup
await coordinator.register_symbol("AAPL")
await coordinator.register_symbol("TSLA")
await coordinator.register_symbol("NVDA")

# All should have:
# - Historical bars loaded
# - Indicators registered and warmed up
# - Ready to stream
```

### **Mid-Session Test**:
```python
# Start session with 2 symbols
await coordinator.start_session()

# Add 3rd symbol mid-session (SAME CODE!)
await coordinator.add_symbol_mid_session("MSFT")

# Should behave identically to pre-session:
# - Historical bars loaded
# - Indicators registered and warmed up
# - Streaming started
```

---

## **Error Handling**

### **Graceful Degradation**:
```python
# If historical load fails
if not historical_bars:
    logger.warning(
        f"{symbol}: No historical data, "
        f"indicators will warm up from live data"
    )
    # Still register, indicators will warm up gradually

# If indicator registration fails
if not indicator_success:
    logger.warning(
        f"{symbol}: Indicator registration failed, "
        f"continuing without indicators"
    )
    # Symbol still registered, just no indicators
```

---

## **Performance Considerations**

### **Pre-Session (Batch)**:
- Can parallelize symbol loading
- All symbols initialized before streaming starts
- No rush

### **Mid-Session (Dynamic)**:
- Must be fast (< 1 second)
- Historical load is async (non-blocking)
- Streaming continues for other symbols

---

## **Status**

**Design**: ✅ COMPLETE  
**Implementation**: ⏳ NEXT  
**Testing**: ⏳ PENDING

**Progress**: 85% → 90% (after implementation)
