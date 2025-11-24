# Phase 3: Historical Bars - Implementation Plan

## Objective

Implement support for loading and maintaining trailing days of historical bar data to enable analysis requiring multiple days of history.

---

## Timeline

**Duration**: 2 weeks  
**Complexity**: Medium  
**Dependencies**: Phases 1 & 2 ✅

---

## Overview

Phase 3 adds the ability to automatically load N trailing days of historical bars when a session starts, maintaining a rolling window of historical data for technical analysis that requires multiple days.

### Use Cases

1. **Multi-day indicators**: SMA-200, volume analysis
2. **Pattern recognition**: Multi-day patterns
3. **Baseline comparison**: Compare today vs historical average
4. **Backtesting warmup**: Provide historical context

---

## Architecture

### Historical Data Storage

```python
# In SymbolSessionData
historical_bars: Dict[int, Dict[date, List[BarData]]]

# Structure: {interval: {date: [bars]}}
# Example:
{
    1: {  # 1-minute bars
        date(2025, 1, 1): [bar1, bar2, ...],
        date(2025, 1, 2): [bar3, bar4, ...],
        date(2025, 1, 3): [bar5, bar6, ...]
    },
    5: {  # 5-minute bars
        date(2025, 1, 1): [bar1, ...],
        date(2025, 1, 2): [bar2, ...],
    }
}
```

### Data Flow

```
Session Start
     │
     ├─► Load Historical Bars
     │   ├─► Query database for trailing N days
     │   ├─► Group by date and interval
     │   └─► Store in historical_bars
     │
     ├─► Stream Current Session
     │   └─► Store in bars_1m (current session)
     │
     └─► Session End
         └─► Session Roll
             ├─► Move current session → historical
             ├─► Remove oldest day
             └─► Clear current session data
```

---

## Features to Implement

### 1. Historical Bars Storage ✅

**Already exists in session_data.py**:
```python
historical_bars: Dict[int, Dict[date, List[BarData]]] = field(
    default_factory=lambda: defaultdict(dict)
)
```

**No changes needed** - structure already supports it!

### 2. Configuration

Add to `settings.py`:
```python
# Historical Bars Configuration
HISTORICAL_BARS_ENABLED: bool = True
HISTORICAL_BARS_TRAILING_DAYS: int = 5  # Load 5 trailing days
HISTORICAL_BARS_INTERVALS: List[int] = [1, 5]  # Load 1m and 5m bars
```

### 3. Loading Historical Bars

**File**: `session_data.py` (add methods)

```python
async def load_historical_bars(
    self,
    symbol: str,
    trailing_days: int,
    intervals: List[int],
    data_repository
) -> int:
    """Load historical bars for trailing days.
    
    Args:
        symbol: Stock symbol
        trailing_days: Number of days to load
        intervals: List of intervals (1, 5, 15, etc.)
        data_repository: Database access
        
    Returns:
        Total number of bars loaded
    """
    symbol = symbol.upper()
    
    if symbol not in self._active_symbols:
        await self.register_symbol(symbol)
    
    # Calculate date range
    end_date = self.current_session_date
    start_date = end_date - timedelta(days=trailing_days)
    
    total_loaded = 0
    
    async with self._lock:
        symbol_data = self._symbols[symbol]
        
        for interval in intervals:
            # Query database
            bars_db = await _query_historical_bars(
                data_repository,
                symbol,
                start_date,
                end_date,
                interval
            )
            
            # Group by date
            bars_by_date = defaultdict(list)
            for bar in bars_db:
                bar_date = bar.timestamp.date()
                bars_by_date[bar_date].append(bar)
            
            # Store in historical_bars
            symbol_data.historical_bars[interval] = dict(bars_by_date)
            total_loaded += len(bars_db)
    
    logger.info(
        f"Loaded {total_loaded} historical bars for {symbol} "
        f"({trailing_days} days, intervals: {intervals})"
    )
    
    return total_loaded
```

### 4. Session Roll Logic

```python
async def roll_session(
    self,
    new_session_date: date
) -> None:
    """Roll to a new session, moving current data to historical.
    
    Args:
        new_session_date: Date of the new session
    """
    if self.current_session_date is None:
        # First session, just start new
        await self.start_new_session(new_session_date)
        return
    
    async with self._lock:
        old_date = self.current_session_date
        
        # For each symbol, move current session to historical
        for symbol_data in self._symbols.values():
            # Move current 1m bars to historical
            if len(symbol_data.bars_1m) > 0:
                historical_bars = list(symbol_data.bars_1m)
                symbol_data.historical_bars[1][old_date] = historical_bars
            
            # Move derived bars to historical
            for interval, bars in symbol_data.bars_derived.items():
                if len(bars) > 0:
                    symbol_data.historical_bars[interval][old_date] = bars.copy()
            
            # Remove oldest day if exceeding trailing days
            max_days = self.historical_bars_trailing_days
            if max_days > 0:
                for interval in symbol_data.historical_bars:
                    dates = sorted(symbol_data.historical_bars[interval].keys())
                    if len(dates) > max_days:
                        oldest = dates[0]
                        del symbol_data.historical_bars[interval][oldest]
                        logger.debug(
                            f"Removed oldest historical day: {oldest}"
                        )
            
            # Clear current session data
            symbol_data.bars_1m.clear()
            symbol_data.bars_derived.clear()
            symbol_data.reset_session_metrics()
        
        # Update session date
        self.current_session_date = new_session_date
        self.session_ended = False
    
    logger.info(
        f"Rolled session from {old_date} to {new_session_date}"
    )
```

### 5. Access Methods

```python
async def get_historical_bars(
    self,
    symbol: str,
    days_back: int,
    interval: int = 1
) -> Dict[date, List[BarData]]:
    """Get historical bars for past N days.
    
    Args:
        symbol: Stock symbol
        days_back: Number of days to retrieve
        interval: Bar interval
        
    Returns:
        Dictionary mapping date to bars for that date
    """
    symbol = symbol.upper()
    
    async with self._lock:
        symbol_data = self._symbols.get(symbol)
        if symbol_data is None:
            return {}
        
        historical = symbol_data.historical_bars.get(interval, {})
        
        if days_back <= 0:
            return dict(historical)
        
        # Get last N days
        dates = sorted(historical.keys(), reverse=True)[:days_back]
        return {d: historical[d] for d in dates}


async def get_all_bars_including_historical(
    self,
    symbol: str,
    interval: int = 1
) -> List[BarData]:
    """Get all bars including historical and current session.
    
    Args:
        symbol: Stock symbol
        interval: Bar interval
        
    Returns:
        All bars chronologically ordered
    """
    symbol = symbol.upper()
    
    async with self._lock:
        symbol_data = self._symbols.get(symbol)
        if symbol_data is None:
            return []
        
        all_bars = []
        
        # Add historical bars (sorted by date)
        historical = symbol_data.historical_bars.get(interval, {})
        for bar_date in sorted(historical.keys()):
            all_bars.extend(historical[bar_date])
        
        # Add current session bars
        if interval == 1:
            all_bars.extend(list(symbol_data.bars_1m))
        else:
            derived = symbol_data.bars_derived.get(interval, [])
            all_bars.extend(derived)
        
        return all_bars
```

---

## Integration Points

### 1. DataManager Integration

**Modify**: `app/managers/data_manager/api.py`

```python
async def initialize_session(
    self,
    session_date: date,
    symbols: List[str],
    load_historical: bool = True
) -> None:
    """Initialize a new trading session.
    
    Args:
        session_date: Date of the session
        symbols: List of symbols to initialize
        load_historical: Whether to load historical bars
    """
    session_data = self.session_data
    
    # Start new session
    await session_data.start_new_session(session_date)
    
    # Load historical bars if enabled
    if load_historical and settings.HISTORICAL_BARS_ENABLED:
        for symbol in symbols:
            await session_data.load_historical_bars(
                symbol=symbol,
                trailing_days=settings.HISTORICAL_BARS_TRAILING_DAYS,
                intervals=settings.HISTORICAL_BARS_INTERVALS,
                data_repository=self.get_database_session()
            )
```

### 2. Session Roll Trigger

**Options**:
1. **Manual**: Call `roll_session()` explicitly
2. **Automatic**: Detect session end, auto-roll
3. **Scheduled**: Roll at specific time

**Recommended**: Manual for now, automatic in Phase 5

---

## Testing Strategy

### Unit Tests

**File**: `test_historical_bars.py`

```python
@pytest.mark.asyncio
async def test_load_historical_bars():
    """Test loading historical bars from database."""
    # Mock database with historical data
    # Call load_historical_bars
    # Verify bars stored in historical_bars structure


@pytest.mark.asyncio
async def test_session_roll():
    """Test rolling session moves current to historical."""
    # Add current session bars
    # Call roll_session
    # Verify current moved to historical
    # Verify current cleared


@pytest.mark.asyncio
async def test_get_historical_bars():
    """Test retrieving historical bars."""
    # Load historical data
    # Call get_historical_bars
    # Verify correct days returned


@pytest.mark.asyncio
async def test_get_all_bars_including_historical():
    """Test getting all bars (historical + current)."""
    # Load historical
    # Add current session bars
    # Call get_all_bars_including_historical
    # Verify chronological order


@pytest.mark.asyncio
async def test_historical_bars_max_days():
    """Test that oldest days are removed when exceeding max."""
    # Load 10 days
    # Set max to 5
    # Roll session
    # Verify only 5 days remain


@pytest.mark.asyncio
async def test_multiple_intervals_historical():
    """Test historical bars for multiple intervals."""
    # Load 1m and 5m historical
    # Verify both stored correctly
    # Verify retrieval works for both
```

---

## Configuration

### New Settings

```python
# In settings.py

# Historical Bars Configuration (Phase 3)
HISTORICAL_BARS_ENABLED: bool = True
HISTORICAL_BARS_TRAILING_DAYS: int = 5  # Number of days to keep
HISTORICAL_BARS_INTERVALS: List[int] = [1, 5]  # Which intervals to load
HISTORICAL_BARS_AUTO_LOAD: bool = True  # Load on session start
```

---

## Use Cases

### 1. Multi-Day SMA

```python
# Get last 200 1-minute bars across multiple days
all_bars = await session_data.get_all_bars_including_historical("AAPL", interval=1)
last_200 = all_bars[-200:]

sma_200 = sum(b.close for b in last_200) / 200
```

### 2. Volume Comparison

```python
# Compare today's volume to 5-day average
historical = await session_data.get_historical_bars("AAPL", days_back=5)

# Calculate average volume per day
avg_volume = sum(
    sum(b.volume for b in bars)
    for bars in historical.values()
) / len(historical)

# Compare to today
current_volume = await session_data.get_session_metrics("AAPL")
print(f"Today: {current_volume['session_volume']:,}")
print(f"5-day avg: {avg_volume:,}")
```

### 3. Pattern Analysis

```python
# Look for patterns across multiple days
for day_date, day_bars in historical.items():
    # Analyze each day's pattern
    high_of_day = max(b.high for b in day_bars)
    low_of_day = min(b.low for b in day_bars)
    # ...pattern detection logic...
```

---

## Performance Considerations

### Memory Usage

**Estimate**:
- 1-minute bars: ~390 bars/day
- 5 days: 1,950 bars
- 100 symbols: 195,000 bars
- ~200 bytes/bar: ~39 MB

**Optimization**:
- Only load configured intervals
- Limit trailing_days
- Clear old data regularly

### Load Time

**Estimate**:
- Database query: 50-100ms per symbol per interval
- 100 symbols, 2 intervals: ~10-20 seconds
- **Solution**: Load asynchronously, don't block

### Query Optimization

```python
# Efficient: Single query per interval
bars = await repo.get_bars_by_symbol(
    symbol,
    start_date,
    end_date,
    interval
)

# vs Inefficient: Query per day
for day in days:
    bars = await repo.get_bars_by_symbol(...)  # N queries!
```

---

## Migration Notes

### Backward Compatibility

Phase 3 is **additive** - no breaking changes:
- `historical_bars` structure already exists (Phase 1)
- All Phase 1 & 2 functionality preserved
- Historical bars optional (configurable)

### Graceful Degradation

```python
# If HISTORICAL_BARS_ENABLED = False
# - No historical data loaded
# - Only current session available
# - Same behavior as Phase 1 & 2
```

---

## Success Criteria

### Phase 3 Goals

- [ ] Historical bars storage working
- [ ] load_historical_bars() implemented
- [ ] Session roll logic working
- [ ] Access methods implemented
- [ ] Configuration added
- [ ] Unit tests comprehensive (>6 tests)
- [ ] DataManager integration
- [ ] Memory usage acceptable
- [ ] Documentation complete

---

## Timeline Breakdown

### Week 1: Core Implementation
**Days 1-2**:
- Add configuration settings
- Implement load_historical_bars()
- Database query integration

**Days 3-4**:
- Implement session roll logic
- Implement access methods
- Testing

**Day 5**:
- DataManager integration
- Code review

### Week 2: Testing & Polish
**Days 1-2**:
- Write comprehensive unit tests
- Fix bugs

**Days 3-4**:
- Performance testing
- Memory optimization
- Documentation

**Day 5**:
- Final testing
- Documentation review
- Prepare for Phase 4

---

## Next: Phase 4

After Phase 3, Phase 4 will add:
- Prefetch mechanism for next session
- Queue refilling on session boundary
- Seamless session transitions

---

**Status**: 📋 Ready to implement  
**Prerequisites**: Phases 1 & 2 complete ✅  
**Timeline**: 2 weeks  
**Complexity**: Medium
