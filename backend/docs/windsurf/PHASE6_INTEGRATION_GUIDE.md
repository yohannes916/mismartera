# Phase 6: SessionCoordinator Integration Guide

**Date**: December 7, 2025  
**Status**: ⏳ READY TO IMPLEMENT  
**Goal**: Integrate indicator system with SessionCoordinator

---

## Integration Points

### **1. Import Indicator Components**

**File**: `/app/threads/session_coordinator.py`

**Add to imports** (around line 50):
```python
# Indicator system
from app.indicators import (
    IndicatorManager,
    IndicatorConfig,
    IndicatorType,
    list_indicators
)
from app.models.indicator_config import (
    SessionIndicatorConfig,
    HistoricalIndicatorConfig
)
```

---

### **2. Initialize IndicatorManager**

**Location**: `SessionCoordinator.__init__()` (around line 104)

**Add after**: `self.session_data = get_session_data()`

```python
# Indicator manager (NEW)
self.indicator_manager = IndicatorManager(self.session_data)
logger.info(f"IndicatorManager initialized with {len(list_indicators())} registered indicators")
```

---

### **3. Parse Indicator Configs from Session Config**

**Location**: `SessionCoordinator.__init__()` (after IndicatorManager init)

```python
# Parse indicator configs from session config
self._indicator_configs = self._parse_indicator_configs()
logger.info(
    f"Loaded {len(self._indicator_configs.get('session', []))} session indicators, "
    f"{len(self._indicator_configs.get('historical', []))} historical indicators"
)
```

**Add helper method**:
```python
def _parse_indicator_configs(self) -> Dict[str, List[IndicatorConfig]]:
    """Parse indicator configs from session config.
    
    Returns:
        Dict with 'session' and 'historical' indicator configs
    """
    session_config = self._system_manager.session_config
    indicators_config = session_config.session_data_config.indicators
    
    result = {
        'session': [],
        'historical': []
    }
    
    # Parse session indicators
    for ind_cfg in indicators_config.session:
        try:
            # Convert SessionIndicatorConfig to IndicatorConfig
            config = IndicatorConfig(
                name=ind_cfg.name,
                type=IndicatorType(ind_cfg.type),
                period=ind_cfg.period,
                interval=ind_cfg.interval,
                params=ind_cfg.params.copy()
            )
            result['session'].append(config)
        except Exception as e:
            logger.error(f"Failed to parse session indicator {ind_cfg.name}: {e}")
    
    # Parse historical indicators
    for ind_cfg in indicators_config.historical:
        try:
            # Convert HistoricalIndicatorConfig to IndicatorConfig
            config = IndicatorConfig(
                name=ind_cfg.name,
                type=IndicatorType(ind_cfg.type),
                period=ind_cfg.period,
                interval=ind_cfg.interval,
                params=ind_cfg.params.copy()
            )
            result['historical'].append(config)
        except Exception as e:
            logger.error(f"Failed to parse historical indicator {ind_cfg.name}: {e}")
    
    return result
```

---

### **4. Register Indicators on Symbol Registration**

**Location**: Find symbol registration method (likely `_register_symbol()` or similar)

**Example location**: Wherever symbols are registered with SessionData

```python
def _register_symbol(self, symbol: str, historical_bars: Optional[Dict] = None):
    """Register symbol with SessionData and indicators.
    
    Args:
        symbol: Symbol to register
        historical_bars: Pre-loaded historical bars (for warmup)
    """
    # Existing symbol registration code...
    symbol_data = SymbolSessionData(symbol=symbol, ...)
    self.session_data.register_symbol(symbol_data)
    
    # NEW: Register indicators for this symbol
    all_indicator_configs = (
        self._indicator_configs['session'] + 
        self._indicator_configs['historical']
    )
    
    if all_indicator_configs:
        self.indicator_manager.register_symbol_indicators(
            symbol=symbol,
            indicators=all_indicator_configs,
            historical_bars=historical_bars  # For warmup
        )
        
        logger.info(
            f"{symbol}: Registered {len(all_indicator_configs)} indicators"
        )
```

---

### **5. Update Indicators on New Bars**

**Location**: Find where new bars are added to SessionData

**Option A: In DataProcessor** (more likely):

**File**: `/app/threads/data_processor.py`

**Find**: Method that adds bars to SessionData (likely `_process_bar()` or similar)

```python
def _process_bar(self, symbol: str, interval: str, bar: BarData):
    """Process incoming bar and update indicators.
    
    Args:
        symbol: Stock symbol
        interval: Bar interval
        bar: Bar data
    """
    # Existing bar processing...
    symbol_data = self.session_data.get_symbol_data(symbol)
    symbol_data.bars[interval].add_bar(bar)
    
    # NEW: Update indicators for this interval
    bars = symbol_data.bars[interval].get_bars()  # All bars
    self.indicator_manager.update_indicators(
        symbol=symbol,
        interval=interval,
        bars=bars
    )
```

**Option B: In SessionCoordinator** (if bars added there):

Find where bars are added during historical load or streaming, add:

```python
# After adding bar to SessionData
self.indicator_manager.update_indicators(
    symbol=symbol,
    interval=interval,
    bars=self.session_data.get_bars(symbol, interval)
)
```

---

### **6. Mid-Session Symbol Insertion**

**Add method to SessionCoordinator**:

```python
async def add_symbol_mid_session(
    self,
    symbol: str,
    load_historical: bool = True
) -> bool:
    """Add symbol during active session.
    
    This reuses the same logic as pre-session initialization:
    1. Load historical bars
    2. Register with SessionData
    3. Register indicators (with warmup)
    4. Start streaming
    
    Args:
        symbol: Symbol to add
        load_historical: Load historical data for warmup
        
    Returns:
        True if successful
    """
    try:
        logger.info(f"{symbol}: Adding symbol mid-session")
        
        # 1. Load historical bars (for indicator warmup)
        historical_bars = {}
        if load_historical:
            historical_bars = await self._load_historical_bars_for_symbol(symbol)
            logger.info(
                f"{symbol}: Loaded historical bars for "
                f"{list(historical_bars.keys())} intervals"
            )
        
        # 2. Register symbol with SessionData
        self._register_symbol(symbol, historical_bars)
        
        # 3. Start streaming for this symbol
        await self._start_symbol_stream(symbol)
        
        logger.info(f"{symbol}: Successfully added mid-session")
        return True
        
    except Exception as e:
        logger.error(f"{symbol}: Failed to add mid-session: {e}", exc_info=True)
        return False

async def _load_historical_bars_for_symbol(
    self,
    symbol: str
) -> Dict[str, List[BarData]]:
    """Load historical bars for a symbol.
    
    Uses requirement analyzer to determine which bars needed.
    
    Args:
        symbol: Symbol to load
        
    Returns:
        Dict of {interval: [bars]}
    """
    from app.threads.quality.requirement_analyzer import analyze_session_requirements
    
    # Analyze requirements (same as initial symbols)
    requirements = analyze_session_requirements(
        streams=self._streams,
        indicator_requirements=[
            ind.interval for ind in (
                self._indicator_configs['session'] + 
                self._indicator_configs['historical']
            )
        ]
    )
    
    # Load historical bars for base interval and historical indicators
    # (Implementation depends on your data loading logic)
    historical_bars = {}
    
    # Load base interval (e.g., 1m)
    base_interval = requirements.required_base_interval
    bars = await self._data_manager.load_historical_bars(
        symbol=symbol,
        interval=base_interval,
        days=20  # Or from config
    )
    historical_bars[base_interval] = bars
    
    # Generate derived intervals if needed
    for interval in requirements.derivable_intervals:
        derived_bars = self._generate_derived_bars(
            bars=historical_bars[base_interval],
            target_interval=interval
        )
        historical_bars[interval] = derived_bars
    
    return historical_bars
```

---

### **7. Integration with StreamRequirementsCoordinator**

**Location**: Where StreamRequirementsCoordinator is used

**Update**: Include indicator requirements in analysis

```python
def _validate_stream_requirements(self):
    """Validate stream requirements including indicators."""
    
    # Add indicator interval requirements
    indicator_intervals = set()
    for ind in self._indicator_configs['session']:
        indicator_intervals.add(ind.interval)
    for ind in self._indicator_configs['historical']:
        indicator_intervals.add(ind.interval)
    
    # Combine with explicit streams
    all_requirements = list(set(self._streams) | indicator_intervals)
    
    # Use StreamRequirementsCoordinator with combined requirements
    requirements_coordinator = StreamRequirementsCoordinator(
        session_config=self.session_config,
        data_manager=self._data_manager,
        required_intervals=all_requirements  # Include indicators
    )
    
    # Validate...
```

---

### **8. Logging and Monitoring**

**Add logging at key points**:

```python
# After indicator registration
logger.info(
    f"{symbol}: Indicators registered - "
    f"{self.indicator_manager.get_indicator_count(symbol)} total"
)

# After indicator update
indicator_count = len(
    self.indicator_manager.get_indicator_configs(symbol, interval)
)
if indicator_count > 0:
    logger.debug(
        f"{symbol}: Updated {indicator_count} indicators on {interval}"
    )

# Show ready indicators
ready_count = sum(
    1 for ind_key in self.session_data.get_symbol_data(symbol).indicators.keys()
    if self.session_data.get_symbol_data(symbol).indicators[ind_key].valid
)
logger.info(
    f"{symbol}: {ready_count} indicators ready (warmup complete)"
)
```

---

## Testing Strategy

### **Unit Tests**

**File**: `tests/test_indicator_integration.py`

```python
import pytest
from app.indicators import IndicatorManager, IndicatorConfig, IndicatorType
from app.managers.data_manager.session_data import SessionData, SymbolSessionData

def test_indicator_manager_initialization():
    """Test IndicatorManager initializes correctly."""
    session_data = SessionData()
    manager = IndicatorManager(session_data)
    assert manager is not None

def test_register_symbol_indicators():
    """Test registering indicators for a symbol."""
    session_data = SessionData()
    manager = IndicatorManager(session_data)
    
    # Register symbol
    symbol_data = SymbolSessionData(symbol="AAPL", base_interval="1m")
    session_data.register_symbol(symbol_data)
    
    # Register indicators
    indicators = [
        IndicatorConfig("sma", IndicatorType.TREND, 20, "5m"),
        IndicatorConfig("rsi", IndicatorType.MOMENTUM, 14, "5m")
    ]
    
    manager.register_symbol_indicators("AAPL", indicators)
    
    assert manager.get_indicator_count("AAPL") == 2

def test_indicator_calculation():
    """Test indicator calculation on new bars."""
    # Create test bars
    # Calculate indicators
    # Verify results
    pass
```

### **Integration Tests**

**File**: `tests/test_session_coordinator_indicators.py`

```python
def test_session_coordinator_with_indicators():
    """Test SessionCoordinator loads and uses indicators."""
    # Create config with indicators
    # Initialize SessionCoordinator
    # Verify indicators registered
    # Simulate bar arrival
    # Verify indicators updated
    pass

def test_mid_session_symbol_insertion_with_indicators():
    """Test adding symbol mid-session with indicators."""
    # Start session
    # Add symbol mid-session
    # Verify indicators registered with warmup
    # Verify indicators update on new bars
    pass
```

### **End-to-End Tests**

**File**: `tests/test_e2e_indicators.py`

```python
def test_full_backtest_with_indicators():
    """Test complete backtest with indicators."""
    # Load unified_config_example.json
    # Run backtest
    # Verify all indicators calculated
    # Verify AnalysisEngine can access indicators
    pass
```

---

## Performance Considerations

### **Indicator Calculation Overhead**

**Per Symbol**:
- 8 session indicators × 390 bars/day ≈ 3,120 calculations
- Most calculations O(N) where N = period (typically 20-30)
- Stateful indicators (EMA, OBV) are O(1) per update

**Total** (10 symbols):
- ~31,200 indicator calculations per day
- Negligible compared to bar processing overhead
- <1ms per indicator calculation

### **Memory Usage**

**Per Symbol**:
- IndicatorData: ~100-200 bytes per indicator
- 10 indicators × 200 bytes = 2KB per symbol
- 10 symbols = 20KB total

**Negligible** compared to bar data (~MBs)

### **Optimization Tips**

1. **Batch Updates**: Update all indicators for an interval at once
2. **Stateful Indicators**: Use previous_result for O(1) updates
3. **Lazy Calculation**: Only calculate if interval has new bars
4. **Caching**: IndicatorManager already caches state

---

## Rollout Plan

### **Phase 6a: Basic Integration** (2-3 hours)
- [ ] Add imports
- [ ] Initialize IndicatorManager
- [ ] Parse indicator configs
- [ ] Register indicators on symbol registration

### **Phase 6b: Bar Updates** (1-2 hours)
- [ ] Find bar addition points
- [ ] Add indicator update calls
- [ ] Test with simple config

### **Phase 6c: Mid-Session Insertion** (2-3 hours)
- [ ] Implement add_symbol_mid_session()
- [ ] Test dynamic symbol addition
- [ ] Verify warmup works

### **Phase 6d: Testing** (3-4 hours)
- [ ] Unit tests
- [ ] Integration tests
- [ ] End-to-end test
- [ ] Performance testing

**Total Estimate**: 8-12 hours (1-2 days)

---

## Verification Checklist

After integration, verify:

### **Config Loading** ✅
- [ ] Config loads without errors
- [ ] Indicators parsed correctly
- [ ] Validation catches errors

### **Initialization** ✅
- [ ] IndicatorManager created
- [ ] Indicator configs loaded
- [ ] All indicators registered

### **Symbol Registration** ✅
- [ ] Indicators registered per symbol
- [ ] Historical warmup works
- [ ] Indicator count correct

### **Bar Updates** ✅
- [ ] Indicators update on new bars
- [ ] Stateful indicators work (EMA, OBV)
- [ ] Multi-value indicators work (BB, MACD)

### **SessionData Access** ✅
- [ ] get_indicator_value() works
- [ ] is_indicator_ready() works
- [ ] get_all_indicators() works

### **Mid-Session Insertion** ✅
- [ ] Symbol adds successfully
- [ ] Indicators register with warmup
- [ ] Indicators update on subsequent bars

### **AnalysisEngine** ✅
- [ ] Can access all indicators
- [ ] Values are correct
- [ ] Performance acceptable

---

## Documentation Updates

After Phase 6 complete, update:

1. **SESSION_ARCHITECTURE.md** - Add indicator integration section
2. **README.md** - Add indicator usage examples
3. **DEPLOYMENT.md** - Add indicator config guidelines

---

## Status

**Current**: Phase 6 integration guide complete ✅  
**Next**: Implement integration following this guide  
**After**: Phase 7 testing and validation

**Overall Progress**: 75% → 90% (after Phase 6)
