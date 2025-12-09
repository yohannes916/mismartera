# Indicator Implementation Plan - OHLCV Only

**Date**: December 7, 2025  
**Constraint**: Price + Volume data ONLY (OHLCV)  
**Goal**: Unified, parameterized, reusable indicator framework  
**Approach**: Clean break, works per-symbol for mid-session insertion

---

## Available Data

### **Bar Data** (Any interval: 1s, 1m, 5m, 1d, 1w, etc.)
```python
@dataclass
class BarData:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
```

### **Derived Fields** (Computed from OHLCV)
- **Typical Price**: `(H + L + C) / 3`
- **True Range**: `max(H - L, abs(H - prev_C), abs(L - prev_C))`
- **Price Change**: `C - prev_C`
- **Range**: `H - L`

---

## Supported Indicators (OHLCV Only)

### **Trend Indicators** (9 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **SMA** | Close, Period | N bars | Simple Moving Average of closing prices |
| **EMA** | Close, Period | N bars | Exponential Moving Average (faster response) |
| **WMA** | Close, Period | N bars | Weighted Moving Average (linear weights) |
| **DEMA** | Close, Period | 2N bars | Double EMA (faster than EMA) |
| **TEMA** | Close, Period | 3N bars | Triple EMA (even faster) |
| **HMA** | Close, Period | N bars | Hull Moving Average (low lag) |
| **VWAP** | OHLCV, Session | Session | Volume-Weighted Average Price |
| **TWAP** | Close, Session | Session | Time-Weighted Average Price |
| **LWMA** | Close, Period | N bars | Linearly Weighted MA |

### **Momentum Indicators** (8 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **RSI** | Close, Period | N+1 bars | Relative Strength Index (overbought/oversold) |
| **MACD** | Close | 26 bars | Moving Average Convergence Divergence |
| **Stochastic** | HLC, Period | N bars | Stochastic Oscillator (%K, %D) |
| **CCI** | HLC, Period | N bars | Commodity Channel Index |
| **ROC** | Close, Period | N bars | Rate of Change (momentum) |
| **MOM** | Close, Period | N bars | Momentum (C - C[n]) |
| **Williams %R** | HLC, Period | N bars | Williams Percent Range |
| **Ultimate Osc** | HLC | 28 bars | Ultimate Oscillator (multi-period) |

### **Volatility Indicators** (6 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **ATR** | HLC, Period | N+1 bars | Average True Range (volatility measure) |
| **BB** | Close, Period | N bars | Bollinger Bands (mean ± std dev) |
| **KC** | HLCV, Period | N bars | Keltner Channels (EMA ± ATR) |
| **DC** | HL, Period | N bars | Donchian Channels (highest/lowest) |
| **STD** | Close, Period | N bars | Standard Deviation |
| **Hist Vol** | Close, Period | N bars | Historical Volatility (annualized) |

### **Volume Indicators** (4 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **OBV** | CV, Session | Session | On-Balance Volume (cumulative) |
| **PVT** | CV, Session | Session | Price-Volume Trend |
| **Volume SMA** | Volume, Period | N bars | Moving average of volume |
| **Volume Ratio** | Volume, Period | N bars | Current vol / Average vol |

### **Support/Resistance** (4 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **Pivot Points** | Daily OHLC | 1 day | Standard pivot points (PP, R1-3, S1-3) |
| **High/Low N** | HL, Period | N bars | Highest high / Lowest low in N periods |
| **Swing High** | H, Period | N bars | Local peak detection |
| **Swing Low** | L, Period | N bars | Local trough detection |

### **Historical Context** (6 indicators)

| Indicator | Inputs | Lookback | Description |
|-----------|--------|----------|-------------|
| **Avg Volume** | Volume, N days | N days | Average daily volume |
| **Avg Range** | HL, N days | N days | Average daily range (H-L) |
| **Avg True Range** | HLC, N days | N days | Average daily true range |
| **High/Low Nd** | HL, N days | N days | N-day high/low |
| **Gap Stats** | Daily OC | N days | Gap frequency and avg size |
| **Range Ratio** | HL, N days | N days | Current range vs avg range |

**Total**: 37 indicators, all calculatable from OHLCV

---

## Unified Indicator Framework

### **Design Principles**

1. **Parameterized**: Works for ANY symbol, ANY interval
2. **Reusable**: Same function for pre-session and mid-session
3. **Stateless**: Pure functions, no instance state
4. **Type-safe**: Explicit typing, validation
5. **Efficient**: Vectorized where possible

### **Base Structure**

```python
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

@dataclass
class BarData:
    """Single bar of OHLCV data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class IndicatorResult:
    """Result from indicator calculation."""
    timestamp: datetime
    value: float | Dict[str, float]  # Single value or multiple (e.g., BB has upper/lower/mid)
    valid: bool  # False during warmup period
    
class IndicatorType(Enum):
    """Indicator classification."""
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    SUPPORT_RESISTANCE = "support_resistance"
    HISTORICAL = "historical"

@dataclass
class IndicatorConfig:
    """Configuration for an indicator."""
    name: str
    type: IndicatorType
    period: int
    interval: str  # Which bar interval to compute on
    params: Dict[str, Any] = field(default_factory=dict)
    
    def warmup_bars(self) -> int:
        """How many bars needed before valid output."""
        # Most indicators need their period
        # Some need more (MACD needs 26, TEMA needs 3*period)
        warmup_map = {
            "macd": 26,
            "tema": self.period * 3,
            "dema": self.period * 2,
            "stochastic": self.period + self.params.get("smooth", 3),
            "ultimate_osc": 28,
        }
        return warmup_map.get(self.name, self.period)
```

### **Indicator Function Signature** (Unified)

```python
def calculate_indicator(
    bars: List[BarData],
    config: IndicatorConfig,
    symbol: str,  # For logging/debugging
    previous_result: Optional[IndicatorResult] = None  # For stateful indicators (EMA, OBV)
) -> IndicatorResult:
    """Calculate indicator value.
    
    Args:
        bars: Historical bars (already filtered to required lookback)
        config: Indicator configuration
        symbol: Symbol being processed
        previous_result: Previous indicator value (for EMA, OBV, etc.)
    
    Returns:
        IndicatorResult with value and validity
    
    This function is:
    - Parameterized: Works for any symbol
    - Reusable: Same code for pre-session and mid-session
    - Stateless: Pure function (except for previous_result)
    """
    # Validate we have enough bars
    if len(bars) < config.warmup_bars():
        return IndicatorResult(
            timestamp=bars[-1].timestamp if bars else None,
            value=None,
            valid=False
        )
    
    # Route to specific indicator implementation
    calculator = INDICATOR_REGISTRY.get(config.name)
    if not calculator:
        raise ValueError(f"Unknown indicator: {config.name}")
    
    return calculator(bars, config, previous_result)
```

---

## Implementation Structure

### **File Organization**

```
app/indicators/
├── __init__.py
├── base.py              # Base classes, types, IndicatorResult
├── registry.py          # Indicator registry and factory
├── trend.py             # Trend indicators (SMA, EMA, etc.)
├── momentum.py          # Momentum indicators (RSI, MACD, etc.)
├── volatility.py        # Volatility indicators (ATR, BB, etc.)
├── volume.py            # Volume indicators (OBV, PVT, etc.)
├── support.py           # S/R indicators (pivots, swing points)
├── historical.py        # Historical context indicators
└── utils.py             # Helper functions (typical_price, true_range, etc.)
```

### **Registry Pattern**

```python
# registry.py
from typing import Callable, Dict
from .base import IndicatorConfig, IndicatorResult, BarData

IndicatorCalculator = Callable[
    [List[BarData], IndicatorConfig, Optional[IndicatorResult]],
    IndicatorResult
]

class IndicatorRegistry:
    """Central registry of all indicators."""
    
    def __init__(self):
        self._calculators: Dict[str, IndicatorCalculator] = {}
    
    def register(self, name: str, calculator: IndicatorCalculator):
        """Register an indicator calculator."""
        self._calculators[name] = calculator
    
    def get(self, name: str) -> Optional[IndicatorCalculator]:
        """Get calculator for an indicator."""
        return self._calculators.get(name)
    
    def list_all(self) -> List[str]:
        """List all registered indicators."""
        return list(self._calculators.keys())

# Global registry instance
INDICATOR_REGISTRY = IndicatorRegistry()

# Decorator for easy registration
def indicator(name: str):
    """Decorator to register an indicator."""
    def decorator(func: IndicatorCalculator):
        INDICATOR_REGISTRY.register(name, func)
        return func
    return decorator
```

### **Example: SMA Implementation**

```python
# trend.py
from .registry import indicator
from .base import BarData, IndicatorConfig, IndicatorResult
from typing import List, Optional

@indicator("sma")
def calculate_sma(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Simple Moving Average.
    
    Formula: SUM(close[i] for i in last N) / N
    """
    period = config.period
    
    # Need at least period bars
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate SMA from last N bars
    recent_closes = [b.close for b in bars[-period:]]
    sma_value = sum(recent_closes) / period
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=sma_value,
        valid=True
    )
```

### **Example: EMA Implementation** (Stateful)

```python
@indicator("ema")
def calculate_ema(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Exponential Moving Average.
    
    Formula: EMA = α * Price + (1 - α) * EMA_prev
    where α = 2 / (period + 1)
    """
    period = config.period
    alpha = 2.0 / (period + 1)
    
    # If we have previous EMA, use it
    if previous_result and previous_result.valid:
        prev_ema = previous_result.value
        current_price = bars[-1].close
        ema_value = alpha * current_price + (1 - alpha) * prev_ema
        
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=ema_value,
            valid=True
        )
    
    # No previous EMA - need to bootstrap
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Bootstrap: Start with SMA, then compute EMA iteratively
    sma = sum(b.close for b in bars[:period]) / period
    ema = sma
    
    # Apply EMA formula to remaining bars
    for bar in bars[period:]:
        ema = alpha * bar.close + (1 - alpha) * ema
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=ema,
        valid=True
    )
```

### **Example: RSI Implementation**

```python
@indicator("rsi")
def calculate_rsi(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Relative Strength Index.
    
    Formula: RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    """
    period = config.period
    
    # Need period + 1 bars (need previous close for first change)
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate price changes
    changes = []
    for i in range(1, len(bars)):
        change = bars[i].close - bars[i-1].close
        changes.append(change)
    
    # Separate gains and losses
    gains = [max(0, c) for c in changes[-period:]]
    losses = [abs(min(0, c)) for c in changes[-period:]]
    
    # Average gain and loss
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Avoid division by zero
    if avg_loss == 0:
        rsi_value = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_value = 100.0 - (100.0 / (1.0 + rs))
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=rsi_value,
        valid=True
    )
```

### **Example: ATR Implementation**

```python
@indicator("atr")
def calculate_atr(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Average True Range.
    
    Formula: ATR = SMA(TR, period)
    where TR = max(H-L, abs(H-prev_C), abs(L-prev_C))
    """
    period = config.period
    
    # Need period + 1 bars (need previous close)
    if len(bars) < period + 1:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate true ranges
    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i-1].close
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)
    
    # ATR = average of last N true ranges
    recent_tr = true_ranges[-period:]
    atr_value = sum(recent_tr) / period
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value=atr_value,
        valid=True
    )
```

### **Example: Bollinger Bands** (Multi-value)

```python
@indicator("bbands")
def calculate_bbands(
    bars: List[BarData],
    config: IndicatorConfig,
    previous_result: Optional[IndicatorResult] = None
) -> IndicatorResult:
    """Bollinger Bands.
    
    Formula:
    - Middle = SMA(close, period)
    - Upper = Middle + (std_dev * num_std)
    - Lower = Middle - (std_dev * num_std)
    """
    period = config.period
    num_std = config.params.get("num_std", 2.0)
    
    if len(bars) < period:
        return IndicatorResult(
            timestamp=bars[-1].timestamp,
            value=None,
            valid=False
        )
    
    # Calculate SMA
    recent_closes = [b.close for b in bars[-period:]]
    sma = sum(recent_closes) / period
    
    # Calculate standard deviation
    variance = sum((c - sma) ** 2 for c in recent_closes) / period
    std_dev = variance ** 0.5
    
    # Bollinger Bands
    upper = sma + (std_dev * num_std)
    lower = sma - (std_dev * num_std)
    
    return IndicatorResult(
        timestamp=bars[-1].timestamp,
        value={
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "bandwidth": (upper - lower) / sma if sma != 0 else 0
        },
        valid=True
    )
```

---

## Integration with Session Data

### **Indicator Manager** (New Component)

```python
class IndicatorManager:
    """Manages indicator calculation for session data.
    
    This is parameterized and reusable:
    - Works per-symbol
    - Works for pre-session and mid-session insertion
    - Handles warmup periods
    - Maintains state for stateful indicators (EMA, OBV)
    """
    
    def __init__(self, session_data: SessionData, time_manager):
        self.session_data = session_data
        self.time_manager = time_manager
        
        # State storage for stateful indicators
        # Structure: {symbol: {interval: {indicator_name: last_result}}}
        self._indicator_state: Dict[str, Dict[str, Dict[str, IndicatorResult]]] = {}
    
    def register_indicators(
        self,
        symbol: str,
        indicators: List[IndicatorConfig]
    ):
        """Register indicators for a symbol.
        
        This works for:
        - Pre-session: Register all symbols at start
        - Mid-session: Register new symbol dynamically
        """
        if symbol not in self._indicator_state:
            self._indicator_state[symbol] = {}
        
        for config in indicators:
            interval = config.interval
            if interval not in self._indicator_state[symbol]:
                self._indicator_state[symbol][interval] = {}
            
            # Initialize state for this indicator
            self._indicator_state[symbol][interval][config.name] = None
    
    def calculate_indicators(
        self,
        symbol: str,
        interval: str,
        bars: List[BarData]
    ) -> Dict[str, IndicatorResult]:
        """Calculate all indicators for a symbol/interval.
        
        Args:
            symbol: Stock symbol
            interval: Bar interval (e.g., "5m")
            bars: Historical bars (including warmup)
        
        Returns:
            Dict of {indicator_name: result}
        
        This function is:
        - Parameterized: Works for any symbol
        - Reusable: Same for pre-session and mid-session
        """
        results = {}
        
        # Get registered indicators for this symbol/interval
        symbol_indicators = self.session_data.get_symbol_data(symbol).indicators
        interval_indicators = [
            ind for ind in symbol_indicators
            if ind.interval == interval
        ]
        
        for config in interval_indicators:
            # Get previous result (for stateful indicators)
            previous = self._indicator_state[symbol][interval].get(config.name)
            
            # Calculate indicator
            result = calculate_indicator(bars, config, symbol, previous)
            
            # Store result
            self._indicator_state[symbol][interval][config.name] = result
            results[config.name] = result
        
        return results
    
    def add_symbol_mid_session(
        self,
        symbol: str,
        indicators: List[IndicatorConfig],
        historical_bars: Dict[str, List[BarData]]
    ):
        """Add new symbol during session (mid-session insertion).
        
        This reuses the same logic as pre-session:
        1. Register indicators
        2. Load historical bars
        3. Calculate warmup
        4. Ready to compute real-time
        """
        # Register indicators (same function as pre-session)
        self.register_indicators(symbol, indicators)
        
        # Calculate initial values using historical data
        for interval, bars in historical_bars.items():
            self.calculate_indicators(symbol, interval, bars)
        
        logger.info(f"Added {symbol} mid-session with {len(indicators)} indicators")
```

---

## Config File Documentation

### **Complete Config File Template**

```json
{
  "session_name": "Comprehensive Trading Session",
  "exchange_group": "US_EQUITY",
  "asset_class": "EQUITY",
  "mode": "backtest",
  
  "backtest_config": {
    "start_date": "2025-07-15",
    "end_date": "2025-07-16",
    "speed_multiplier": 60.0
  },
  
  "data_requirements": {
    "symbols": ["AAPL", "TSLA", "NVDA"],
    
    "bars": {
      "comment": "List all bar intervals you want. System determines base interval automatically.",
      "session": ["1m", "5m", "15m", "1d"],
      "historical": {
        "trailing_days": 20,
        "intervals": ["1d"]
      }
    },
    
    "quotes": {
      "comment": "Enable quote data (bid/ask). Not used for indicators currently.",
      "enabled": false,
      "historical": false
    },
    
    "indicators": {
      "comment": "All indicators calculated from OHLCV data only",
      
      "session": [
        {
          "name": "sma",
          "description": "Simple Moving Average of closing prices",
          "period": 20,
          "interval": "5m",
          "type": "trend"
        },
        {
          "name": "ema",
          "description": "Exponential Moving Average (faster response than SMA)",
          "period": 12,
          "interval": "5m",
          "type": "trend"
        },
        {
          "name": "vwap",
          "description": "Volume-Weighted Average Price from session start",
          "interval": "1m",
          "type": "trend",
          "note": "No period needed - cumulative from session start"
        },
        {
          "name": "rsi",
          "description": "Relative Strength Index (0-100, overbought >70, oversold <30)",
          "period": 14,
          "interval": "5m",
          "type": "momentum"
        },
        {
          "name": "macd",
          "description": "Moving Average Convergence Divergence (trend + momentum)",
          "interval": "15m",
          "type": "momentum",
          "params": {
            "fast": 12,
            "slow": 26,
            "signal": 9
          }
        },
        {
          "name": "bbands",
          "description": "Bollinger Bands (volatility envelope around SMA)",
          "period": 20,
          "interval": "5m",
          "type": "volatility",
          "params": {
            "num_std": 2.0
          }
        },
        {
          "name": "atr",
          "description": "Average True Range (volatility measure)",
          "period": 14,
          "interval": "5m",
          "type": "volatility"
        },
        {
          "name": "obv",
          "description": "On-Balance Volume (cumulative volume direction)",
          "interval": "1m",
          "type": "volume",
          "note": "Cumulative from session start"
        }
      ],
      
      "historical": [
        {
          "name": "avg_volume",
          "description": "Average daily volume over N days",
          "period": 5,
          "unit": "days",
          "type": "volume"
        },
        {
          "name": "atr_daily",
          "description": "Average True Range on daily bars",
          "period": 14,
          "unit": "days",
          "type": "volatility"
        },
        {
          "name": "high_low",
          "description": "Highest high and lowest low over N days",
          "period": 20,
          "unit": "days",
          "type": "support_resistance"
        }
      ]
    }
  }
}
```

### **Indicator Reference Documentation**

Create: `/docs/INDICATOR_REFERENCE.md`

```markdown
# Indicator Reference

All indicators are calculated from OHLCV data (Open, High, Low, Close, Volume).

## Trend Indicators

### SMA (Simple Moving Average)
**Formula**: Average of closing prices over N periods  
**Inputs**: Close, Period  
**Warmup**: N bars  
**Use**: Identify trend direction, support/resistance  
**Example**: `{"name": "sma", "period": 20, "interval": "5m"}`

### EMA (Exponential Moving Average)
**Formula**: Weighted average giving more weight to recent prices  
**Inputs**: Close, Period  
**Warmup**: N bars  
**Use**: Faster trend detection than SMA  
**Example**: `{"name": "ema", "period": 12, "interval": "5m"}`

### VWAP (Volume-Weighted Average Price)
**Formula**: Cumulative (Price × Volume) / Cumulative Volume  
**Inputs**: OHLC, Volume  
**Warmup**: Session start  
**Use**: Institutional benchmark, intraday support/resistance  
**Example**: `{"name": "vwap", "interval": "1m"}`

[... continue for all 37 indicators ...]

## Momentum Indicators

### RSI (Relative Strength Index)
**Formula**: 100 - (100 / (1 + RS)), where RS = Avg Gain / Avg Loss  
**Inputs**: Close, Period  
**Warmup**: N+1 bars  
**Range**: 0-100  
**Interpretation**: >70 overbought, <30 oversold  
**Example**: `{"name": "rsi", "period": 14, "interval": "5m"}`

[... etc ...]
```

---

## Implementation Plan

### **Phase 1: Indicator Framework** (3 days)
**Goal**: Core framework with 10 essential indicators

**Tasks**:
1. Create `app/indicators/` directory structure
2. Implement base classes (`IndicatorResult`, `IndicatorConfig`)
3. Implement registry pattern
4. Implement 10 core indicators:
   - Trend: SMA, EMA, VWAP
   - Momentum: RSI, MACD
   - Volatility: ATR, BB
   - Volume: OBV, Volume SMA
   - S/R: High/Low N

**Deliverables**:
- ✅ `app/indicators/base.py`
- ✅ `app/indicators/registry.py`
- ✅ `app/indicators/trend.py`
- ✅ `app/indicators/momentum.py`
- ✅ `app/indicators/volatility.py`
- ✅ `app/indicators/volume.py`
- ✅ `app/indicators/support.py`
- ✅ Unit tests for all 10 indicators

---

### **Phase 2: Remaining Indicators** (2 days)
**Goal**: Complete all 37 indicators

**Tasks**:
1. Implement remaining trend indicators (WMA, DEMA, TEMA, HMA, etc.)
2. Implement remaining momentum indicators (Stochastic, CCI, etc.)
3. Implement remaining volatility indicators (KC, DC, etc.)
4. Implement historical context indicators
5. Add utility functions (`typical_price`, `true_range`, etc.)

**Deliverables**:
- ✅ All 37 indicators implemented
- ✅ `app/indicators/utils.py`
- ✅ `app/indicators/historical.py`
- ✅ Complete test coverage

---

### **Phase 3: Indicator Manager** (2 days)
**Goal**: Integration with SessionData

**Tasks**:
1. Create `IndicatorManager` class
2. Implement per-symbol indicator tracking
3. Implement state management (for EMA, OBV, etc.)
4. Implement mid-session symbol insertion support
5. Integrate with `SessionData`

**Deliverables**:
- ✅ `app/indicators/manager.py`
- ✅ Integration tests
- ✅ Works for pre-session and mid-session

---

### **Phase 4: Enhanced Requirement Analyzer** (2 days)
**Goal**: Update requirement analyzer to handle indicators

**Tasks**:
1. Extend `analyze_session_requirements()` to parse indicators
2. Implement `calculate_historical_lookback()`
3. Update config schema to support indicator definitions
4. Add indicator validation

**Deliverables**:
- ✅ Updated `requirement_analyzer.py`
- ✅ Indicator warmup calculation
- ✅ Historical lookback logic

---

### **Phase 5: Config Integration** (2 days)
**Goal**: New unified config structure

**Tasks**:
1. Update `session_config.py` with `data_requirements` structure
2. Remove old `streams`, `historical`, `data_upkeep` sections
3. Add indicator config validation
4. Create comprehensive config documentation
5. Migrate example configs

**Deliverables**:
- ✅ Updated `session_config.py`
- ✅ New config schema
- ✅ `/docs/INDICATOR_REFERENCE.md`
- ✅ `/docs/CONFIG_REFERENCE.md`
- ✅ Updated example configs

---

### **Phase 6: Session Coordinator Integration** (2 days)
**Goal**: Use unified requirements and indicators

**Tasks**:
1. Update coordinator to use `UnifiedRequirements`
2. Initialize `IndicatorManager`
3. Calculate indicators on new bars
4. Remove hardcoded interval lists
5. Support mid-session symbol insertion with indicators

**Deliverables**:
- ✅ Updated `session_coordinator.py`
- ✅ Indicator calculation pipeline
- ✅ Mid-session insertion support

---

### **Phase 7: Testing & Documentation** (2 days)
**Goal**: Comprehensive testing and docs

**Tasks**:
1. End-to-end tests with all indicators
2. Performance testing (1000+ bars)
3. Mid-session insertion tests
4. Create user guide
5. Create indicator cookbook (common strategies)

**Deliverables**:
- ✅ Full test suite
- ✅ `/docs/USER_GUIDE.md`
- ✅ `/docs/INDICATOR_COOKBOOK.md`
- ✅ Performance benchmarks

---

## Success Criteria

### **After Implementation** ✅

1. ✅ **37 indicators working** - All calculatable from OHLCV
2. ✅ **Unified framework** - Same code for all intervals
3. ✅ **Parameterized** - Works per-symbol
4. ✅ **Reusable** - Pre-session and mid-session
5. ✅ **Clean config** - User-friendly, well-documented
6. ✅ **Type-safe** - Explicit types, validation
7. ✅ **Efficient** - Fast calculation, minimal overhead

### **Config Example Works**

```json
{
  "data_requirements": {
    "symbols": ["AAPL"],
    "bars": ["5m", "15m"],
    "indicators": {
      "session": [
        {"name": "sma", "period": 20, "interval": "5m"},
        {"name": "rsi", "period": 14, "interval": "15m"}
      ]
    }
  }
}
```

**System determines**:
- Base: 1m (needed for 5m, 15m)
- Generates: 5m, 15m
- Calculates: SMA_20 on 5m, RSI_14 on 15m
- Warmup: 20 bars of 5m, 15 bars of 15m

### **Mid-Session Insertion Works**

```python
# During session, add new symbol
coordinator.add_symbol_mid_session(
    symbol="TSLA",
    indicators=[
        IndicatorConfig("sma", "trend", 20, "5m"),
        IndicatorConfig("rsi", "momentum", 14, "5m")
    ]
)

# System:
# 1. Loads historical 1m bars (for 5m generation)
# 2. Generates 5m bars from 1m
# 3. Calculates SMA and RSI on 5m
# 4. Ready for real-time updates
```

---

## Estimated Timeline

| Phase | Days | Cumulative |
|-------|------|------------|
| Phase 1: Framework + 10 indicators | 3 | 3 |
| Phase 2: Remaining 27 indicators | 2 | 5 |
| Phase 3: Indicator Manager | 2 | 7 |
| Phase 4: Requirement Analyzer | 2 | 9 |
| Phase 5: Config Integration | 2 | 11 |
| Phase 6: Session Coordinator | 2 | 13 |
| Phase 7: Testing & Docs | 2 | 15 |
| **Total** | **15 days** | |

---

## **Status**: ⏳ **READY TO IMPLEMENT**

Clean break approach:
- ❌ Delete old `data_upkeep` config
- ❌ Delete hardcoded interval lists
- ✅ New unified `data_requirements` structure
- ✅ Parameterized indicator framework
- ✅ Works for pre-session and mid-session
- ✅ All 37 indicators from OHLCV only

**Ready to start Phase 1?**
