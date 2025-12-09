# Unified Requirement Analysis & Indicator Support

**Date**: December 7, 2025  
**Goal**: Single unified logic to determine ALL data requirements  
**Approach**: User specifies goals, system determines implementation

---

## Philosophy

### **User Perspective** (What They Want)
```json
{
  "data_requirements": {
    "bars": ["5m", "15m", "1d", "1w"],
    "quotes": true,
    "indicators": {
      "session": ["sma_20", "vwap", "rsi_14"],
      "historical": ["avg_volume_5d", "atr_14d"]
    }
  }
}
```

### **System Response** (What It Determines)
```
Analysis Result:
✓ Base interval needed: 1m (smallest to support all requirements)
✓ Will stream: 1m bars, quotes
✓ Will generate: 5m, 15m, 1d (from 1m)
✓ Will generate: 1w (from 1d)
✓ Indicators requiring: 1m for SMA/VWAP/RSI, 1d for ATR
✓ Historical data needed: 20 days of 1m (for indicators)
```

**No distinction** between "base" and "derived" in config - system figures it out!

---

## Existing Implementation (Very Good!)

### **requirement_analyzer.py** - Already Does Most of This! ✅

**Current Capabilities**:
1. ✅ Parses ANY interval string (`"5s"`, `"5m"`, `"1d"`, `"1w"`)
2. ✅ Determines required base interval automatically
3. ✅ Identifies implicit requirements (derivation chains)
4. ✅ Handles indicator requirements (partial)
5. ✅ Validates configuration
6. ✅ Rejects hourly intervals
7. ✅ Priority-based selection (1s < 1m < 1d)

**Example**:
```python
result = analyze_session_requirements(
    streams=["5m", "15m", "1d"],
    indicator_requirements=["1m"]  # From indicator
)

# Result:
# - required_base_interval: "1m"
# - explicit_intervals: ["5m", "15m", "1d"]
# - derivable_intervals: ["5m", "15m", "1d"]
# - implicit_intervals: [IntervalRequirement("1m", IMPLICIT_DERIVATION, "Required to generate 5m")]
```

---

## What Needs Extension

### **1. Indicator Specification** ❌ (Needs Design)

Current: `indicator_requirements` is just a list of intervals  
Needed: Full indicator metadata with interval requirements

### **2. Storage Availability Check** ❌ (Needs Implementation)

Current: Assumes we'll stream base interval  
Needed: Check if data exists in parquet, adjust strategy

### **3. Historical Requirements** ❌ (Needs Implementation)

Current: No historical window calculation  
Needed: Calculate lookback periods for indicators

---

## Comprehensive Indicator Matrix

### **Session Indicators** (Real-time, computed on bars)

| Category | Indicator | Interval Req | Lookback | Description |
|----------|-----------|--------------|----------|-------------|
| **Trend** | `sma_N` | Any bar | N bars | Simple Moving Average |
| | `ema_N` | Any bar | N bars | Exponential Moving Average |
| | `wma_N` | Any bar | N bars | Weighted Moving Average |
| | `vwap` | Intraday (1s-1d) | Session | Volume-Weighted Avg Price |
| | `tema_N` | Any bar | N bars | Triple EMA |
| **Momentum** | `rsi_N` | Any bar | N bars | Relative Strength Index |
| | `macd` | Any bar | 26 bars | MACD (12,26,9) |
| | `stoch_N` | Any bar | N bars | Stochastic Oscillator |
| | `cci_N` | Any bar | N bars | Commodity Channel Index |
| | `roc_N` | Any bar | N bars | Rate of Change |
| **Volatility** | `bbands_N` | Any bar | N bars | Bollinger Bands |
| | `atr_N` | Any bar | N bars | Average True Range |
| | `kc_N` | Any bar | N bars | Keltner Channels |
| | `dc_N` | Any bar | N bars | Donchian Channels |
| **Volume** | `obv` | Any bar | Session | On-Balance Volume |
| | `adl` | Any bar | Session | Accumulation/Distribution |
| | `cmf_N` | Any bar | N bars | Chaikin Money Flow |
| | `mfi_N` | Any bar | N bars | Money Flow Index |
| **Support/Resistance** | `pivot_points` | Daily | 1 day | Pivot Points (daily) |
| | `hilo_N` | Any bar | N bars | High/Low N periods |
| | `swing_high_N` | Any bar | N bars | Swing High Detection |
| | `swing_low_N` | Any bar | N bars | Swing Low Detection |

### **Historical Indicators** (Pre-computed, context)

| Category | Indicator | Interval Req | Lookback | Description |
|----------|-----------|--------------|----------|-------------|
| **Volume Profile** | `avg_volume_Nd` | Daily | N days | Average Daily Volume |
| | `relative_volume` | Daily | 20 days | Current vs Avg Volume |
| | `volume_trend` | Daily | 10 days | Volume trend direction |
| **Price Context** | `high_low_Nd` | Daily | N days | N-day High/Low |
| | `atr_Nd` | Daily | N days | Daily ATR |
| | `range_avg_Nd` | Daily | N days | Avg Daily Range |
| | `gap_history` | Daily | 20 days | Gap statistics |
| **Trend Context** | `trend_strength_Nd` | Daily | N days | Trend strength measure |
| | `consolidation_Nd` | Daily | N days | Consolidation detection |
| | `breakout_level` | Daily | 20 days | Key breakout levels |
| **Correlation** | `sector_correlation` | Daily | 20 days | Sector correlation |
| | `spy_beta` | Daily | 60 days | Beta to SPY |

### **Special Indicators** (Multi-interval)

| Indicator | Requirements | Description |
|-----------|--------------|-------------|
| `anchored_vwap` | 1m bars + anchor time | VWAP from specific time |
| `session_high_low` | Session bars | Session extremes |
| `opening_range` | 1m bars (first 30m) | Opening range breakout |
| `time_and_sales` | Quotes | Time & sales analysis |

---

## Unified Config Structure

### **New Config Format**

```json
{
  "session_name": "Example Session",
  "mode": "backtest",
  "backtest_config": {
    "start_date": "2025-07-15",
    "end_date": "2025-07-16",
    "speed_multiplier": 60.0
  },
  "data_requirements": {
    "symbols": ["AAPL", "RIVN", "TSLA"],
    
    "bars": {
      "session": ["5m", "15m", "1d"],
      "historical": {
        "trailing_days": 20,
        "intervals": ["1d"]
      }
    },
    
    "quotes": {
      "enabled": true,
      "historical": false
    },
    
    "indicators": {
      "session": [
        {"name": "sma", "period": 20, "interval": "5m"},
        {"name": "vwap", "interval": "1m"},
        {"name": "rsi", "period": 14, "interval": "5m"},
        {"name": "bbands", "period": 20, "interval": "15m"}
      ],
      "historical": [
        {"name": "avg_volume", "period": 5, "unit": "days"},
        {"name": "atr", "period": 14, "unit": "days"},
        {"name": "high_low", "period": 20, "unit": "days"}
      ]
    }
  }
}
```

---

## Unified Analysis Logic

### **Step 1: Parse User Requirements**

```python
@dataclass
class SessionIndicator:
    """Real-time indicator computed on bars."""
    name: str
    period: int
    interval: str  # Which bar interval to compute on
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HistoricalIndicator:
    """Pre-computed indicator for context."""
    name: str
    period: int
    unit: str  # "days" or "bars"
    interval: str = "1d"  # Most historical indicators use daily
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DataRequirements:
    """Complete data requirements from config."""
    symbols: List[str]
    session_bars: List[str]
    historical_bars: Dict[str, int]  # interval -> trailing_days
    quotes_enabled: bool
    quotes_historical: bool
    session_indicators: List[SessionIndicator]
    historical_indicators: List[HistoricalIndicator]
```

### **Step 2: Determine Interval Requirements**

```python
def analyze_data_requirements(
    config: DataRequirements,
    storage_available: Optional[Dict[str, List[str]]] = None
) -> UnifiedRequirements:
    """Analyze complete data requirements.
    
    Args:
        config: User-specified data requirements
        storage_available: What's in parquet (symbol -> list of intervals)
    
    Returns:
        Complete analysis with base interval, derivation plan, etc.
    """
    
    # 1. Collect all bar intervals requested
    all_intervals = set(config.session_bars)
    all_intervals.update(config.historical_bars.keys())
    
    # 2. Add intervals required by session indicators
    for indicator in config.session_indicators:
        all_intervals.add(indicator.interval)
        
        # Some indicators need underlying data
        if indicator.name in ["vwap", "obv", "adl"]:
            # Need actual trades/volume, so need finest resolution
            base = determine_required_base(indicator.interval)
            all_intervals.add(base)
    
    # 3. Add intervals required by historical indicators
    for indicator in config.historical_indicators:
        all_intervals.add(indicator.interval)
    
    # 4. Run requirement analysis (existing logic!)
    requirements = analyze_session_requirements(
        streams=list(all_intervals),
        indicator_requirements=[]  # Already included above
    )
    
    # 5. Check storage availability (NEW)
    if storage_available:
        # Optimize: Use what's in storage if available
        requirements = optimize_with_storage(requirements, storage_available)
    
    # 6. Calculate historical lookback (NEW)
    historical_lookback = calculate_historical_lookback(
        config.session_indicators,
        config.historical_indicators,
        config.historical_bars
    )
    
    return UnifiedRequirements(
        base_interval=requirements.required_base_interval,
        stream_intervals=[requirements.required_base_interval],
        derived_intervals=requirements.derivable_intervals,
        historical_lookback=historical_lookback,
        indicators=config.session_indicators,
        historical_indicators=config.historical_indicators
    )
```

### **Step 3: Storage Optimization** (NEW)

```python
def optimize_with_storage(
    requirements: SessionRequirements,
    storage: Dict[str, List[str]]
) -> SessionRequirements:
    """Optimize requirements based on available storage.
    
    Example:
        Requested: 5m, 15m, 1d
        Base determined: 1m
        Storage has: 1m, 1d
        
        Optimization:
        - Stream: 1m (need for 5m, 15m generation)
        - Load from storage: 1d (already computed, don't recompute)
        - Generate: 5m, 15m (from 1m)
    
    Args:
        requirements: Initial requirements
        storage: Available intervals in storage
    
    Returns:
        Optimized requirements
    """
    # Check which derived intervals exist in storage
    available_derived = []
    still_need_derived = []
    
    for interval in requirements.derivable_intervals:
        if interval in storage.get("AAPL", []):  # Check any symbol
            available_derived.append(interval)
        else:
            still_need_derived.append(interval)
    
    # If daily bars exist, we might not need to generate them
    if "1d" in available_derived and "1d" in requirements.derivable_intervals:
        logger.info("1d bars available in storage - will load instead of generate")
    
    # Update requirements
    requirements.derivable_intervals = still_need_derived
    requirements.loadable_intervals = available_derived
    
    return requirements
```

### **Step 4: Historical Lookback Calculation** (NEW)

```python
def calculate_historical_lookback(
    session_indicators: List[SessionIndicator],
    historical_indicators: List[HistoricalIndicator],
    historical_bars: Dict[str, int]
) -> Dict[str, int]:
    """Calculate how much historical data needed.
    
    Returns:
        interval -> days needed
    
    Examples:
        SMA_20 on 5m → need 20 bars of 5m → need 1 trading day
        RSI_14 on 1d → need 14 bars of 1d → need 14 trading days
        avg_volume_5d → need 5 trading days of 1d
    """
    lookback = defaultdict(int)
    
    # From explicit historical config
    for interval, days in historical_bars.items():
        lookback[interval] = max(lookback[interval], days)
    
    # From session indicators (need warmup period)
    for indicator in session_indicators:
        interval = indicator.interval
        period = indicator.period
        
        # Convert bars to days (approximate)
        if interval.endswith('m'):
            minutes = int(interval[:-1])
            # 390 minutes per trading day
            days_needed = (period * minutes) / 390
            days_needed = max(1, int(days_needed) + 1)  # Round up
        elif interval.endswith('d'):
            days_needed = period
        else:
            days_needed = 1  # Conservative
        
        lookback[interval] = max(lookback[interval], days_needed)
    
    # From historical indicators
    for indicator in historical_indicators:
        if indicator.unit == "days":
            lookback[indicator.interval] = max(
                lookback[indicator.interval],
                indicator.period
            )
    
    return dict(lookback)
```

---

## Enhanced Data Structures

### **UnifiedRequirements** (Enhanced SessionRequirements)

```python
@dataclass
class UnifiedRequirements:
    """Complete analysis of all data requirements."""
    
    # Intervals
    base_interval: str                    # What to stream (1s, 1m, or 1d)
    stream_intervals: List[str]           # All intervals to stream
    derived_intervals: List[str]          # Intervals to generate
    loadable_intervals: List[str]         # Intervals available in storage
    
    # Historical
    historical_lookback: Dict[str, int]   # interval -> days needed
    
    # Indicators
    indicators: List[SessionIndicator]    # Real-time indicators
    historical_indicators: List[HistoricalIndicator]  # Context indicators
    
    # Storage optimization
    storage_strategy: Dict[str, str]      # interval -> "stream" | "load" | "generate"
    
    # Reasoning
    all_requirements: List[IntervalRequirement]  # Complete audit trail
```

---

## Indicator Implementation Framework

### **Base Indicator Class**

```python
class BaseIndicator(ABC):
    """Base class for all indicators."""
    
    def __init__(self, name: str, period: int, **params):
        self.name = name
        self.period = period
        self.params = params
    
    @abstractmethod
    def required_interval(self) -> str:
        """Which bar interval does this indicator need?"""
        pass
    
    @abstractmethod
    def warmup_bars(self) -> int:
        """How many bars needed before valid output?"""
        pass
    
    @abstractmethod
    def compute(self, bars: List[BarData]) -> Any:
        """Compute indicator value."""
        pass
    
    @property
    def is_historical(self) -> bool:
        """Is this a historical context indicator?"""
        return False
```

### **Session Indicator Examples**

```python
class SMA(BaseIndicator):
    """Simple Moving Average."""
    
    def required_interval(self) -> str:
        return self.params.get("interval", "1m")
    
    def warmup_bars(self) -> int:
        return self.period
    
    def compute(self, bars: List[BarData]) -> float:
        if len(bars) < self.period:
            return None
        recent = bars[-self.period:]
        return sum(b.close for b in recent) / self.period


class VWAP(BaseIndicator):
    """Volume-Weighted Average Price."""
    
    def required_interval(self) -> str:
        # VWAP needs finest resolution for accuracy
        return "1m"
    
    def warmup_bars(self) -> int:
        return 1  # Starts from session open
    
    def compute(self, bars: List[BarData]) -> float:
        if not bars:
            return None
        
        # Session VWAP: cumulative from session start
        total_pv = sum(b.close * b.volume for b in bars)
        total_v = sum(b.volume for b in bars)
        
        return total_pv / total_v if total_v > 0 else None
```

### **Historical Indicator Examples**

```python
class AvgVolume(BaseIndicator):
    """Average daily volume over N days."""
    
    def __init__(self, period: int):
        super().__init__("avg_volume", period, interval="1d")
        self.is_historical = True
    
    def required_interval(self) -> str:
        return "1d"
    
    def warmup_bars(self) -> int:
        return self.period
    
    def compute(self, daily_bars: List[BarData]) -> float:
        if len(daily_bars) < self.period:
            return None
        recent = daily_bars[-self.period:]
        return sum(b.volume for b in recent) / self.period


class ATR_Daily(BaseIndicator):
    """Daily Average True Range."""
    
    def __init__(self, period: int):
        super().__init__("atr", period, interval="1d")
        self.is_historical = True
    
    def required_interval(self) -> str:
        return "1d"
    
    def warmup_bars(self) -> int:
        return self.period + 1  # Need prev close
    
    def compute(self, daily_bars: List[BarData]) -> float:
        if len(daily_bars) < self.period + 1:
            return None
        
        # True range calculations...
        true_ranges = []
        for i in range(1, len(daily_bars)):
            high = daily_bars[i].high
            low = daily_bars[i].low
            prev_close = daily_bars[i-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        recent = true_ranges[-self.period:]
        return sum(recent) / self.period
```

---

## Usage Examples

### **Example 1: Simple Scalping Setup**

```json
{
  "data_requirements": {
    "symbols": ["AAPL", "TSLA"],
    "bars": {
      "session": ["1m", "5m"],
      "historical": {
        "trailing_days": 1,
        "intervals": ["1d"]
      }
    },
    "indicators": {
      "session": [
        {"name": "vwap", "interval": "1m"},
        {"name": "ema", "period": 9, "interval": "1m"}
      ],
      "historical": [
        {"name": "avg_volume", "period": 5, "unit": "days"}
      ]
    }
  }
}
```

**System Analysis**:
```
✓ Base interval: 1m (smallest to support all)
✓ Will stream: 1m bars
✓ Will generate: 5m (from 1m)
✓ Historical: 1d bars for 5 days (for avg_volume)
✓ Indicators: VWAP and EMA_9 on 1m (real-time)
✓ Context: 5-day average volume
```

### **Example 2: Multi-Timeframe Strategy**

```json
{
  "data_requirements": {
    "symbols": ["SPY"],
    "bars": {
      "session": ["1m", "5m", "15m", "1d"],
      "historical": {
        "trailing_days": 20,
        "intervals": ["1d"]
      }
    },
    "indicators": {
      "session": [
        {"name": "sma", "period": 20, "interval": "5m"},
        {"name": "rsi", "period": 14, "interval": "15m"},
        {"name": "bbands", "period": 20, "interval": "5m"}
      ],
      "historical": [
        {"name": "atr", "period": 14, "unit": "days"},
        {"name": "high_low", "period": 20, "unit": "days"}
      ]
    }
  }
}
```

**System Analysis**:
```
✓ Base interval: 1m
✓ Will stream: 1m bars
✓ Will generate: 5m, 15m, 1d (from 1m)
✓ Historical: 1d bars for 20 days
✓ Session indicators need: 20 bars warmup (5m), 14 bars warmup (15m)
✓ Historical warmup: 20 days of 1d bars
```

### **Example 3: Day/Swing Trading**

```json
{
  "data_requirements": {
    "symbols": ["AAPL", "MSFT", "NVDA"],
    "bars": {
      "session": ["1d"],
      "historical": {
        "trailing_days": 60,
        "intervals": ["1d"]
      }
    },
    "indicators": {
      "session": [
        {"name": "sma", "period": 50, "interval": "1d"},
        {"name": "sma", "period": 200, "interval": "1d"},
        {"name": "rsi", "period": 14, "interval": "1d"}
      ],
      "historical": [
        {"name": "atr", "period": 14, "unit": "days"},
        {"name": "avg_volume", "period": 20, "unit": "days"},
        {"name": "spy_beta", "period": 60, "unit": "days"}
      ]
    }
  }
}
```

**System Analysis**:
```
✓ Base interval: 1d
✓ Will stream: 1d bars (OR: load from storage if available)
✓ Historical: 200 days of 1d bars (for SMA_200 warmup)
✓ Session indicators: Need up to 200 bars warmup
✓ Historical indicators: Need 60 days
✓ OPTIMIZATION: Check if 1d bars in parquet, avoid recomputation
```

---

## Implementation Plan

### **Phase 1: Enhanced Requirement Analyzer** (2 days)
1. Extend `analyze_session_requirements()` to handle indicators
2. Add `SessionIndicator` and `HistoricalIndicator` dataclasses
3. Implement `calculate_historical_lookback()`
4. Add storage availability checking
5. Implement `optimize_with_storage()`

### **Phase 2: Indicator Framework** (3 days)
1. Create `BaseIndicator` abstract class
2. Implement core session indicators (SMA, EMA, VWAP, RSI, MACD)
3. Implement core historical indicators (avg_volume, ATR, high/low)
4. Create indicator registry and factory
5. Add indicator validation

### **Phase 3: Config Integration** (2 days)
1. Update `session_config.py` with new `data_requirements` structure
2. Remove old `streams`, `historical`, `data_upkeep` sections
3. Update validation logic
4. Migrate example configs

### **Phase 4: Session Coordinator Integration** (2 days)
1. Update coordinator to use unified requirements
2. Remove hardcoded interval lists
3. Implement storage-aware loading
4. Update symbol registration

### **Phase 5: Testing** (1 day)
1. Test all indicator requirements
2. Test storage optimization
3. Test historical lookback calculation
4. End-to-end validation

---

## Success Criteria

### **After Implementation** ✅

1. ✅ **Single config format** - No base/derived distinction
   ```json
   "bars": ["5m", "15m", "1d"]  // System figures out base = 1m
   ```

2. ✅ **Automatic base selection**
   ```
   User wants: 5m, 15m
   System determines: Need 1m base, generate 5m/15m
   ```

3. ✅ **Indicator-driven requirements**
   ```json
   "indicators": [{"name": "sma", "period": 20, "interval": "5m"}]
   // System adds: Need 5m bars, therefore need 1m base
   ```

4. ✅ **Storage optimization**
   ```
   Storage has: 1m, 1d
   User wants: 5m, 15m, 1d
   System: Stream 1m, generate 5m/15m, LOAD 1d from storage
   ```

5. ✅ **Historical lookback automatic**
   ```
   SMA_20 on 5m → Need 1 day of 5m bars
   ATR_14 on 1d → Need 14 days of 1d bars
   System: Load 14 days of 1d, generate 1 day of 5m from 1m
   ```

6. ✅ **Comprehensive indicators**
   - 20+ session indicators (trend, momentum, volatility, volume)
   - 10+ historical indicators (context, statistics)
   - Extensible framework for custom indicators

---

## **Status**: ⏳ **READY TO IMPLEMENT**

We have:
- ✅ Excellent foundation (`requirement_analyzer.py`)
- ✅ Clear extension path (indicators, storage, lookback)
- ✅ Comprehensive indicator matrix
- ✅ Unified config structure

Next: Implement enhanced requirement analyzer with full indicator support!
