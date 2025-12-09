# Mid-Session Symbol Insertion Design

**Date**: December 7, 2025  
**Critical Question**: When adding a symbol mid-session, what data/indicators does it get?  
**Answer**: ALL requirements from session-config, analyzed through requirement_analyzer

---

## Core Principle

### **Session-Config is the Source of Truth** ✅

When you add a symbol mid-session, it gets **EXACTLY** the same data and indicators as the original symbols from the session-config:

```json
{
  "data_requirements": {
    "symbols": ["AAPL", "TSLA"],  // Initial symbols
    "bars": ["5m", "15m", "1d"],
    "indicators": {
      "session": [
        {"name": "sma", "period": 20, "interval": "5m"},
        {"name": "rsi", "period": 14, "interval": "15m"}
      ],
      "historical": [
        {"name": "high_low", "period": 20, "interval": "1d"}
      ]
    }
  }
}
```

**Mid-session**: Add "NVDA"

**Result**: NVDA gets:
- ✅ Same bars: 5m, 15m, 1d
- ✅ Same session indicators: SMA(20) on 5m, RSI(14) on 15m
- ✅ Same historical indicators: 20-day high/low
- ✅ **PLUS**: All implicit requirements determined by requirement_analyzer

---

## Requirement Analyzer Integration

### **Step 1: Extract Session-Config Requirements**

```python
def add_symbol_mid_session(self, symbol: str):
    """Add new symbol during session.
    
    Uses session-config requirements + requirement_analyzer.
    """
    
    # Extract requirements from session-config
    session_config = self._system_manager.session_config
    data_reqs = session_config.data_requirements
    
    # Build requirement input (same as original symbols)
    requirements = {
        "session_bars": data_reqs.bars.session,
        "historical_bars": data_reqs.bars.historical.intervals,
        "trailing_days": data_reqs.bars.historical.trailing_days,
        "session_indicators": data_reqs.indicators.session,
        "historical_indicators": data_reqs.indicators.historical
    }
```

### **Step 2: Run Through Requirement Analyzer**

```python
    # Analyze requirements (SAME as initial symbols)
    from app.threads.quality.requirement_analyzer import analyze_data_requirements
    
    unified_reqs = analyze_data_requirements(
        config=requirements,
        storage_available=self._check_storage_for_symbol(symbol)
    )
    
    # Result includes:
    # - base_interval: "1m" (automatically determined)
    # - stream_intervals: ["1m"]
    # - derived_intervals: ["5m", "15m", "1d"] (automatically determined)
    # - historical_lookback: {"1d": 20} (from indicators)
    # - indicators: [all session indicators]
    # - historical_indicators: [all historical indicators]
```

### **Step 3: Load Historical Data**

```python
    # Load historical data based on lookback requirements
    historical_data = await self._load_historical_data(
        symbol=symbol,
        intervals=unified_reqs.all_required_intervals(),
        lookback=unified_reqs.historical_lookback
    )
    
    # historical_data includes:
    # - 1m bars for past 1 day (to generate 5m, 15m, 1d)
    # - 1d bars for past 20 days (for 20-day high/low indicator)
```

### **Step 4: Generate Derived Intervals**

```python
    # Generate derived intervals from historical 1m bars
    # (Same logic as pre-session initialization)
    from app.managers.data_manager.derived_bars import compute_all_derived_intervals
    
    for interval in unified_reqs.derived_intervals:
        if interval in ["5m", "15m", "1d"]:
            # Generate from 1m base
            derived_bars = compute_all_derived_intervals(
                base_bars=historical_data["1m"],
                target_intervals=[interval]
            )
            historical_data[interval] = derived_bars[interval]
```

### **Step 5: Calculate Indicators**

```python
    # Calculate all indicators (warmup phase)
    indicator_manager = self._get_indicator_manager()
    
    for ind_config in unified_reqs.indicators:
        # Get bars for this indicator's interval
        bars = historical_data[ind_config.interval]
        
        # Calculate indicator (warmup)
        result = calculate_indicator(
            bars=bars,
            config=ind_config,
            symbol=symbol,
            previous_result=None  # First calculation
        )
        
        # Store in SessionData
        indicator_manager.store_indicator(symbol, ind_config, result)
```

### **Step 6: Register for Real-Time Updates**

```python
    # Register symbol for real-time streaming
    # (Same as original symbols)
    await self._session_coordinator.register_symbol(
        symbol=symbol,
        base_interval=unified_reqs.base_interval,  # "1m"
        derived_intervals=unified_reqs.derived_intervals  # ["5m", "15m", "1d"]
    )
    
    logger.info(
        f"Added {symbol} mid-session with same requirements as session-config: "
        f"base={unified_reqs.base_interval}, "
        f"derived={unified_reqs.derived_intervals}, "
        f"indicators={len(unified_reqs.indicators)}"
    )
```

---

## Complete Flow Diagram

```
User Action: Add "NVDA" mid-session
    ↓
Session-Config (source of truth)
    ├─ bars: ["5m", "15m", "1d"]
    ├─ indicators.session: [SMA(20) on 5m, RSI(14) on 15m]
    └─ indicators.historical: [20-day high/low]
    ↓
Requirement Analyzer (automatic determination)
    ├─ Determines base: "1m" (needed for 5m, 15m, 1d)
    ├─ Determines derived: ["5m", "15m", "1d"]
    ├─ Calculates lookback: {"1d": 20} (for 20-day high/low warmup)
    ├─ Validates indicators
    └─ Checks storage availability
    ↓
Historical Data Loader
    ├─ Load 1m bars for past 1 day (390 bars)
    └─ Load 1d bars for past 20 days
    ↓
Derived Bar Generator (if needed)
    ├─ Generate 5m from 1m (78 bars)
    ├─ Generate 15m from 1m (26 bars)
    └─ Generate 1d from 1m (1 bar)
    ↓
Indicator Calculator (warmup)
    ├─ Calculate SMA(20) on 5m bars (warmup complete if 20+ bars)
    ├─ Calculate RSI(14) on 15m bars (warmup complete if 15+ bars)
    └─ Calculate 20-day high/low on 1d bars (warmup complete if 20+ days)
    ↓
SessionData Storage
    ├─ bars: {1m: [...], 5m: [...], 15m: [...], 1d: [...]}
    ├─ indicators: {
    │     "sma_20_5m": IndicatorData(...),
    │     "rsi_14_15m": IndicatorData(...),
    │     "high_low_20_1d": IndicatorData(...)
    │   }
    └─ Ready for real-time updates
    ↓
Stream Registration
    ├─ Subscribe to 1m stream for NVDA
    ├─ Auto-generate 5m, 15m, 1d on new 1m bars
    └─ Update all indicators on new bars
    ↓
✅ NVDA now has EXACT SAME data as AAPL and TSLA
```

---

## Key Behaviors

### **1. Consistency Across Symbols** ✅

All symbols (initial + mid-session) have:
- Same bar intervals
- Same indicators
- Same historical context
- Same warmup state (if enough historical data)

**Why**: AnalysisEngine expects uniform data across symbols

### **2. Automatic Interval Determination** ✅

User specifies: `["5m", "15m", "1d"]`  
Requirement analyzer automatically adds:
- Base interval: `"1m"` (implicit, needed to generate 5m, 15m, 1d)
- Intermediate intervals: None needed (5m, 15m, 1d all derive from 1m)

User specifies: `["5s", "10s", "1m"]`  
Requirement analyzer automatically adds:
- Base interval: `"1s"` (needed for 5s, 10s)
- Keep: `"1m"` (explicit request)

### **3. Historical Lookback Calculation** ✅

Indicators drive historical data loading:

```json
{
  "indicators": {
    "session": [
      {"name": "sma", "period": 20, "interval": "5m"}
    ]
  }
}
```

**Requirement analyzer calculates**:
- SMA(20) on 5m needs 20 bars of 5m
- 5m derived from 1m
- 20 bars of 5m = ~100 bars of 1m (20 * 5)
- Need ~1 day of 1m historical data

**Loads automatically**:
- 1 day of 1m bars from parquet
- Generates 5m from 1m
- Calculates SMA(20) for warmup

### **4. Storage Optimization** ✅

If parquet already has the data:

```python
# Check storage before loading
storage_available = {
    "NVDA": ["1m", "1d"]  # Already in parquet
}

# Requirement analyzer optimizes:
unified_reqs = analyze_data_requirements(
    config=requirements,
    storage_available=storage_available
)

# Result:
# - Load 1m from storage (don't stream)
# - Load 1d from storage (don't recompute)
# - Generate 5m, 15m from 1m (not in storage)
```

---

## Usage Examples

### **Example 1: Simple Mid-Session Addition**

```python
# In SessionCoordinator or command handler
async def add_symbol_command(self, symbol: str):
    """Add symbol mid-session - uses session-config requirements."""
    
    # ONE function call - everything handled automatically
    await self._session_coordinator.add_symbol_mid_session(symbol)
    
    # Behind the scenes:
    # 1. Reads session-config requirements
    # 2. Runs requirement_analyzer
    # 3. Loads historical data
    # 4. Generates derived intervals
    # 5. Calculates indicators
    # 6. Registers for real-time updates
    
    logger.info(f"Added {symbol} with full session-config requirements")
```

### **Example 2: Verify Same Requirements**

```python
# After adding NVDA mid-session
def verify_consistency(self):
    """Verify all symbols have same data/indicators."""
    
    symbols = ["AAPL", "TSLA", "NVDA"]  # NVDA added mid-session
    
    for symbol in symbols:
        symbol_data = self.session_data.get_symbol_data(symbol)
        
        # Check bars
        assert "5m" in symbol_data.bars
        assert "15m" in symbol_data.bars
        assert "1d" in symbol_data.bars
        
        # Check indicators
        assert "sma_20_5m" in symbol_data.indicators
        assert "rsi_14_15m" in symbol_data.indicators
        assert "high_low_20_1d" in symbol_data.indicators
        
        # Check warmup state
        sma = symbol_data.indicators["sma_20_5m"]
        assert sma.valid  # Should be ready (warmup complete)
    
    logger.info("✅ All symbols have identical data structure")
```

### **Example 3: Mid-Session with Multiple Intervals**

```python
# Session config has complex requirements
config = {
    "data_requirements": {
        "bars": ["1m", "5m", "15m", "1d", "1w"],
        "indicators": {
            "session": [
                {"name": "sma", "period": 20, "interval": "5m"},
                {"name": "ema", "period": 12, "interval": "15m"},
                {"name": "vwap", "interval": "1m"}
            ],
            "historical": [
                {"name": "high_low", "period": 20, "interval": "1d"},
                {"name": "high_low", "period": 4, "interval": "1w"},
                {"name": "avg_volume", "period": 10, "interval": "1d"}
            ]
        }
    }
}

# Add MSFT mid-session
await add_symbol_mid_session("MSFT")

# Requirement analyzer determines:
# - Base: 1m (smallest needed)
# - Derive: 5m, 15m, 1d from 1m
# - Derive: 1w from 1d
# - Historical: 20 days of 1d, 4 weeks of 1w
# - All indicators calculated
```

---

## API Signature

### **SessionCoordinator.add_symbol_mid_session()**

```python
async def add_symbol_mid_session(
    self,
    symbol: str,
    override_requirements: Optional[DataRequirements] = None
) -> None:
    """Add symbol mid-session with session-config requirements.
    
    Args:
        symbol: Symbol to add
        override_requirements: Optional custom requirements 
                              (if None, uses session-config)
    
    Process:
        1. Extract requirements from session-config (or override)
        2. Run through requirement_analyzer to determine:
           - Base interval (e.g., "1m")
           - Derived intervals (e.g., ["5m", "15m", "1d"])
           - Historical lookback (e.g., 20 days for indicators)
           - Storage optimization
        3. Load historical data (from parquet or API)
        4. Generate derived intervals
        5. Calculate indicators (warmup)
        6. Register for real-time streaming
        7. Update SessionData
    
    Result:
        Symbol has EXACT same data/indicators as original symbols
    
    Example:
        >>> # Uses session-config requirements
        >>> await coordinator.add_symbol_mid_session("NVDA")
        
        >>> # Custom requirements (rare)
        >>> custom = DataRequirements(
        >>>     session_bars=["1m"],
        >>>     indicators=[]
        >>> )
        >>> await coordinator.add_symbol_mid_session("MSFT", custom)
    """
```

---

## Implementation Notes

### **Phase 3: Indicator Manager** (includes mid-session)

```python
class IndicatorManager:
    """Manages indicators for all symbols."""
    
    def register_symbol_indicators(
        self,
        symbol: str,
        indicators: List[IndicatorConfig],
        historical_bars: Dict[str, List[BarData]]
    ):
        """Register indicators for symbol (pre-session or mid-session).
        
        This is the SAME function used for:
        - Pre-session initialization (all symbols)
        - Mid-session insertion (new symbol)
        
        Parameterized - works for any symbol, any time.
        """
        # Initialize indicator state
        self._indicator_state[symbol] = {}
        
        # Calculate warmup for all indicators
        for config in indicators:
            interval = config.interval
            bars = historical_bars.get(interval, [])
            
            # Calculate indicator
            result = calculate_indicator(
                bars=bars,
                config=config,
                symbol=symbol,
                previous_result=None
            )
            
            # Store in SessionData
            self._store_indicator(symbol, config, result)
```

### **Phase 6: Session Coordinator Integration**

```python
class SessionCoordinator:
    """Session coordinator with mid-session insertion."""
    
    async def add_symbol_mid_session(self, symbol: str):
        """Add symbol using session-config requirements."""
        
        # 1. Get session-config requirements
        data_reqs = self._system_manager.session_config.data_requirements
        
        # 2. Analyze requirements (same as initial symbols)
        unified_reqs = analyze_data_requirements(
            config=data_reqs,
            storage_available=await self._check_storage(symbol)
        )
        
        # 3. Load historical data
        historical_data = await self._data_manager.load_historical_data(
            symbol=symbol,
            intervals=unified_reqs.all_intervals(),
            lookback=unified_reqs.historical_lookback
        )
        
        # 4. Generate derived intervals
        for interval in unified_reqs.derived_intervals:
            if self._needs_generation(interval, historical_data):
                base = unified_reqs.base_interval
                derived = compute_all_derived_intervals(
                    historical_data[base],
                    [interval]
                )
                historical_data[interval] = derived[interval]
        
        # 5. Register indicators (warmup)
        self._indicator_manager.register_symbol_indicators(
            symbol=symbol,
            indicators=unified_reqs.indicators,
            historical_bars=historical_data
        )
        
        # 6. Register for streaming
        await self._register_symbol_streaming(
            symbol=symbol,
            base_interval=unified_reqs.base_interval,
            derived_intervals=unified_reqs.derived_intervals
        )
        
        logger.info(f"✅ Added {symbol} mid-session with full requirements")
```

---

## Summary

### **Questions Answered** ✅

**Q1: When we add a symbol mid-session, do all of the historical data and indicators specified in the initial session-config get generated?**

**A1**: YES! ✅
- All bars from session-config
- All session indicators from session-config
- All historical indicators from session-config
- All historical data loaded for warmup

**Q2: Does requirement_analyzer get used to figure out all the additional intervals needed (not explicitly mentioned in the original session_config)?**

**A2**: YES! ✅
- Requirement analyzer runs for mid-session symbol
- Determines base interval automatically (e.g., 1m for 5m, 15m)
- Determines derived intervals automatically
- Calculates historical lookback automatically
- Optimizes with storage if available

### **Key Principle** ✅

**Mid-session insertion = Pre-session initialization**
- Same requirements (from session-config)
- Same requirement_analyzer logic
- Same data loading
- Same indicator calculation
- **Result**: Perfect consistency across all symbols

---

## **Status**: ✅ DESIGN CLARIFIED

Mid-session insertion fully integrated with:
- Session-config as source of truth
- Requirement analyzer for automatic determination
- Unified, parameterized code
- Perfect consistency with original symbols
