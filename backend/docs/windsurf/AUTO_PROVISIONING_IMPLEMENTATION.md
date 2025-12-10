# Indicator Auto-Provisioning Implementation - Dec 9, 2025

## Summary

Implemented the `analyze_indicator_requirements()` function that automatically determines what bar intervals and historical data are needed for indicators. This enables scanners to automatically provision required bars without manual configuration.

## Feature Overview

When a scanner or user adds an indicator (e.g., "20-period SMA on 5m bars"), the system now automatically:
1. **Analyzes** what intervals are needed (e.g., 5m bars require 1m base bars)
2. **Calculates** how many historical bars are needed for warmup
3. **Estimates** calendar days to cover those bars (accounting for weekends/holidays)
4. **Provisions** the required intervals automatically

## Implementation

### New Function: `analyze_indicator_requirements()`

**Location:** `/app/threads/quality/requirement_analyzer.py` (lines 466-548)

**Signature:**
```python
def analyze_indicator_requirements(
    indicator_config: IndicatorConfig,
    warmup_multiplier: float = 2.0
) -> IndicatorRequirements
```

**Returns:** `IndicatorRequirements` dataclass with:
- `indicator_key`: Unique key (e.g., "sma_20_5m")
- `required_intervals`: List of intervals needed (e.g., ["1m", "5m"])
- `historical_bars`: Number of bars for warmup (e.g., 40)
- `historical_days`: Estimated calendar days (e.g., 2)
- `reason`: Human-readable explanation

### Algorithm

1. **Parse Interval**: Determine if indicator's interval is a base or derived interval
2. **Determine Base**: If derived (e.g., 5m), identify required base interval (1m)
3. **Calculate Bars**: Use `indicator_config.warmup_bars()` × `warmup_multiplier`
4. **Estimate Days**: Convert bars to calendar days using `_estimate_calendar_days()`
5. **Build Requirements**: Return complete requirements object

### Calendar Day Estimation

**Function:** `_estimate_calendar_days()` (lines 551-613)

Conservative estimates accounting for:
- **Weekends**: Market closed Sat/Sun
- **Holidays**: ~10 per year
- **Data gaps**: Buffer for missing data

**Examples:**
- 40 daily bars → 60 calendar days (1.5x factor)
- 390 1-minute bars → 1-2 calendar days (full trading day + buffer)
- 52 weekly bars → ~400 calendar days (1 year + buffer)

## Usage

### In Scanner Setup

```python
from app.threads.quality.requirement_analyzer import analyze_indicator_requirements

# Define indicator
indicator_config = IndicatorConfig(
    name="sma",
    type=IndicatorType.TREND,
    period=20,
    interval="5m"
)

# Analyze requirements
reqs = analyze_indicator_requirements(
    indicator_config=indicator_config,
    warmup_multiplier=2.0  # 2x buffer for safety
)

# Auto-provision bars
for interval in reqs.required_intervals:
    session_data.add_historical_bars(
        symbol=symbol,
        interval=interval,
        days=reqs.historical_days
    )
    session_data.add_session_bars(
        symbol=symbol,
        interval=interval
    )
```

### Via SessionData.add_indicator()

The `add_indicator()` method now uses auto-provisioning automatically:

```python
# Scanners just call this - provisioning happens automatically!
context.session_data.add_indicator(
    symbol="AAPL",
    indicator_type="sma",
    config={
        "period": 20,
        "interval": "5m",
        "type": "trend"
    }
)
```

**What happens internally:**
1. Creates `IndicatorConfig`
2. Calls `analyze_indicator_requirements()`
3. Provisions base interval (1m) + derived interval (5m)
4. Registers with IndicatorManager
5. Returns success

## Examples

### Example 1: Simple Daily Indicator

```python
config = IndicatorConfig(
    name="sma",
    period=20,
    interval="1d"
)

reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
```

**Result:**
- `required_intervals`: `["1d"]`
- `historical_bars`: `40` (20 × 2.0)
- `historical_days`: `60` (~40 trading days = 60 calendar days)
- `reason`: "SMA(20) on 1d needs 20 bars for warmup, requesting 40 bars (2.0x buffer) = ~60 calendar days"

### Example 2: Derived Interval Indicator

```python
config = IndicatorConfig(
    name="rsi",
    period=14,
    interval="5m"
)

reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
```

**Result:**
- `required_intervals`: `["1m", "5m"]` (needs base + derived)
- `historical_bars`: `30` (RSI needs period+1 = 15, × 2.0 = 30)
- `historical_days`: `1` (30 5-min bars = 2.5 hours)
- `reason`: "RSI(14) on 5m needs 15 bars for warmup, requesting 30 bars (2.0x buffer) = ~1 calendar days"

### Example 3: High-Frequency Indicator

```python
config = IndicatorConfig(
    name="sma",
    period=200,
    interval="5s"
)

reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
```

**Result:**
- `required_intervals`: `["1s", "5s"]` (needs 1s base)
- `historical_bars`: `400` (200 × 2.0)
- `historical_days`: `1` (400 5-sec bars = 33 minutes)

### Example 4: 52-Week High/Low

```python
config = IndicatorConfig(
    name="high_low",
    period=52,
    interval="1w"
)

reqs = analyze_indicator_requirements(config, warmup_multiplier=2.0)
```

**Result:**
- `required_intervals`: `["1w"]`
- `historical_bars`: `104` (52 × 2.0)
- `historical_days`: `~728` (104 weeks = ~2 years)

## Special Indicator Handling

The system knows about indicators that need extra warmup:

| Indicator | Standard | Warmup Formula |
|-----------|----------|----------------|
| SMA       | period   | `period` |
| RSI       | period   | `period + 1` |
| MACD      | 12/26/9  | `26` (slow EMA) |
| DEMA      | period   | `period * 2` |
| TEMA      | period   | `period * 3` |
| Stochastic| period   | `period + smooth` |
| Swing High/Low | period | `(period * 2) + 1` |

These formulas are defined in `IndicatorConfig.warmup_bars()` (lines 68-86 in `app/indicators/base.py`).

## Warmup Multiplier

The `warmup_multiplier` parameter adds a safety buffer:

- **1.0**: Minimal - exactly what indicator needs
- **2.0**: Conservative (default) - 2x the warmup bars
- **3.0**: Very conservative - 3x the warmup bars

**Why use 2.0?**
- Accounts for holidays and weekends
- Handles gaps in historical data
- Provides buffer for data quality issues
- Ensures indicator has valid values from session start

## Integration Points

### 1. SessionData.add_indicator()

**File:** `/app/managers/data_manager/session_data.py` (lines 2198-2234)

Now fully implemented with auto-provisioning:
1. Creates `IndicatorConfig`
2. Analyzes requirements via `analyze_indicator_requirements()`
3. Provisions historical bars for each required interval
4. Provisions session bars for real-time updates
5. Registers with IndicatorManager

### 2. Scanner Setup

Scanners call `context.session_data.add_indicator()` during setup:

```python
def setup(self, context: ScanContext) -> bool:
    for symbol in self._universe:
        context.session_data.add_indicator(
            symbol=symbol,
            indicator_type="sma",
            config={"period": 20, "interval": "1d"}
        )
    return True
```

Provisioning happens automatically - no manual bar requests needed!

### 3. Requirement Analyzer Module

**Module:** `app.threads.quality.requirement_analyzer`

**Exports:**
- `analyze_indicator_requirements()` - Main auto-provisioning function
- `IndicatorRequirements` - Return dataclass
- `analyze_session_requirements()` - Session-level analysis
- `parse_interval()` - Interval parsing
- `determine_required_base()` - Base interval logic

## Testing

### Unit Tests

**File:** `/tests/unit/test_indicator_auto_provisioning.py`

**Coverage:** 17 tests across 3 test classes:

1. **TestIndicatorAutoProvisioning** (11 tests)
   - Simple indicators on base intervals
   - Derived interval indicators
   - Special warmup cases (RSI, MACD)
   - Intraday vs daily vs weekly
   - Custom warmup multipliers
   - Zero-period indicators

2. **TestCalendarDayEstimation** (3 tests)
   - Daily bar estimation
   - Intraday bar estimation
   - Weekly bar estimation

3. **TestMultiIntervalProvisioning** (3 tests)
   - Minute-based derivation
   - Second-based derivation
   - Base interval behavior

**All 17 tests pass** ✅

### Integration Tests

**File:** `/tests/integration/test_scanner_integration.py`

**All 8 tests pass** including:
- `test_scanner_setup_provisions_data` - Verifies auto-provisioning works
- Full scanner lifecycle tests
- State progression tests

## Performance Considerations

### Time Complexity

- **Parsing**: O(1) - regex match
- **Base determination**: O(1) - simple lookup
- **Bar calculation**: O(1) - arithmetic
- **Total**: O(1) per indicator

### Memory

- Lightweight dataclass return value
- No caching (analysis is cheap)
- Minimal overhead

### Provisioning Impact

The actual bar provisioning (adding historical/session bars) is done by SessionData, not by the analyzer. The analyzer just determines WHAT is needed.

## Error Handling

### Invalid Intervals

```python
try:
    reqs = analyze_indicator_requirements(config)
except ValueError as e:
    # Invalid interval format (e.g., "1h" - hourly not supported)
    logger.error(f"Invalid indicator interval: {e}")
```

### Circular Imports

Uses `TYPE_CHECKING` to avoid circular dependency:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.indicators import IndicatorConfig
```

Runtime import happens inside function when needed.

## Logging

The system logs detailed information during provisioning:

```
[ADHOC] add_indicator(AAPL, sma, interval=5m)
Analyzing requirements for sma_20_5m...
[ADHOC] Indicator sma_20_5m requires: intervals=['1m', '5m'], historical_bars=40, historical_days=2
[ADHOC] Reasoning: SMA(20) on 5m needs 20 bars for warmup, requesting 40 bars (2.0x buffer) = ~2 calendar days
[ADHOC] Provisioning 2 days of 1m bars for AAPL
[ADHOC] Provisioning 1m session bars for AAPL
[ADHOC] Provisioning 2 days of 5m bars for AAPL
[ADHOC] Provisioning 5m session bars for AAPL
Registered indicator sma_20_5m with IndicatorManager
[ADHOC] Added indicator sma_20_5m for AAPL (provisioned 2 intervals, 2 days historical)
```

## Future Enhancements

### Potential Improvements

1. **Smart Caching**: Cache analysis results for identical configs
2. **Batch Analysis**: Analyze multiple indicators at once
3. **Dynamic Adjustment**: Adjust based on actual data quality
4. **Market-Specific**: Different estimates for different exchanges
5. **Validation**: Verify bars were actually provisioned

### Known Limitations

1. **Estimates are conservative**: May request more days than strictly needed
2. **No data quality check**: Assumes perfect data availability
3. **No overlap detection**: Doesn't optimize when multiple indicators need same data
4. **Fixed multiplier**: Can't vary multiplier by indicator complexity

## Files Modified/Created

### Modified
1. `/app/threads/quality/requirement_analyzer.py`
   - Added `IndicatorRequirements` dataclass
   - Implemented `analyze_indicator_requirements()`
   - Implemented `_estimate_calendar_days()`
   - Added TYPE_CHECKING imports

2. `/app/managers/data_manager/session_data.py`
   - Updated `add_indicator()` to use auto-provisioning
   - Restored auto-provisioning loop (lines 2215-2234)
   - Enhanced logging with detailed requirements

### Created
1. `/tests/unit/test_indicator_auto_provisioning.py`
   - Comprehensive unit tests (17 tests)
   - Tests all indicator types and scenarios

2. `/backend/docs/windsurf/AUTO_PROVISIONING_IMPLEMENTATION.md`
   - This documentation file

## Migration Notes

### Before Auto-Provisioning

Scanners had to manually provision bars:

```python
# OLD WAY - Manual provisioning
def setup(self, context: ScanContext) -> bool:
    for symbol in self._universe:
        # Had to manually figure out what's needed!
        context.session_data.add_historical_bars(
            symbol=symbol,
            interval="1m",  # Guessed base interval
            days=30  # Guessed days
        )
        context.session_data.add_historical_bars(
            symbol=symbol,
            interval="5m",  # Guessed derived interval
            days=30
        )
        context.session_data.add_session_bars(symbol=symbol, interval="1m")
        context.session_data.add_session_bars(symbol=symbol, interval="5m")
```

### After Auto-Provisioning

Scanners just declare what they need:

```python
# NEW WAY - Automatic provisioning
def setup(self, context: ScanContext) -> bool:
    for symbol in self._universe:
        # System figures out everything automatically!
        context.session_data.add_indicator(
            symbol=symbol,
            indicator_type="sma",
            config={"period": 20, "interval": "5m"}
        )
```

## Benefits

1. **Simpler Scanner Code**: No manual bar provisioning logic
2. **Correctness**: System knows exact warmup requirements
3. **Consistency**: All indicators use same logic
4. **Maintainability**: Requirements centralized in one place
5. **Debugging**: Clear logging shows what was provisioned
6. **Efficiency**: Only provisions what's actually needed

## Conclusion

The auto-provisioning feature is **fully implemented and tested**. Scanners can now add indicators with a single call, and the system automatically provisions all required bars with appropriate warmup periods.

**Status:** ✅ Complete and Production-Ready
