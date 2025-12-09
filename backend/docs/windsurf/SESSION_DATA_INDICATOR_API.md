# SessionData Indicator API

**Goal**: Fast, simple access to indicators for AnalysisEngine  
**Storage**: All indicators stored in SessionData  
**Access**: Direct attribute access, no computation needed

---

## Indicator Storage Structure

### **In SessionData**

```python
@dataclass
class SymbolSessionData:
    """Session data for a single symbol."""
    symbol: str
    base_interval: str
    
    # Bar data (existing)
    bars: Dict[str, BarIntervalData]  # interval -> bars
    
    # NEW: Indicator data
    indicators: Dict[str, IndicatorData]  # indicator_key -> values
    
@dataclass
class IndicatorData:
    """Indicator values for a symbol."""
    name: str
    type: str  # "session" or "historical"
    interval: str  # Which bar interval it's computed on
    current_value: float | Dict[str, float]  # Latest value
    historical_values: List[IndicatorResult]  # Full history (optional)
    last_updated: datetime
    valid: bool  # Is warmup complete?
```

### **Indicator Keys** (Naming Convention)

```python
# Format: "{name}_{period}_{interval}" or "{name}_{interval}"

# Examples:
"sma_20_5m"      # SMA(20) on 5m bars
"rsi_14_15m"     # RSI(14) on 15m bars
"vwap_1m"        # VWAP on 1m bars (no period)
"atr_14_1d"      # ATR(14) on daily bars
"high_low_20_1d" # 20-day high/low
"high_low_4_1w"  # 4-week high/low
```

---

## High/Low Support (Nd and Nw)

### **Unified Implementation** ✅

We support **ONE** indicator: `high_low` that works on **ANY interval**:

```json
{
  "indicators": {
    "historical": [
      {
        "name": "high_low",
        "period": 20,
        "interval": "1d",
        "comment": "20-day high/low (Nd format)"
      },
      {
        "name": "high_low",
        "period": 4,
        "interval": "1w",
        "comment": "4-week high/low (Nw format)"
      },
      {
        "name": "high_low",
        "period": 3,
        "interval": "1d",
        "comment": "3-day high/low"
      }
    ]
  }
}
```

**Storage Keys**:
- `high_low_20_1d` → 20-day high/low
- `high_low_4_1w` → 4-week high/low
- `high_low_3_1d` → 3-day high/low

**Values** (Dictionary):
```python
{
  "high": 185.50,  # Highest high in N periods
  "low": 178.25    # Lowest low in N periods
}
```

### **Why This Works**

The `high_low` indicator is **parameterized by interval**:
- Applied to `"1d"` bars → Daily high/low (Nd)
- Applied to `"1w"` bars → Weekly high/low (Nw)
- Applied to `"1m"` bars → Minute high/low
- Applied to `"5m"` bars → 5-minute high/low

**No separate indicators needed!** Same code, different interval.

---

## AnalysisEngine Access API

### **Quick Access Methods**

```python
class SessionData:
    """Enhanced with indicator access."""
    
    def get_indicator(
        self,
        symbol: str,
        indicator_key: str
    ) -> Optional[IndicatorData]:
        """Get indicator by key.
        
        Args:
            symbol: Stock symbol
            indicator_key: Indicator key (e.g., "sma_20_5m")
        
        Returns:
            IndicatorData or None if not found
        
        Example:
            >>> sma = session_data.get_indicator("AAPL", "sma_20_5m")
            >>> if sma and sma.valid:
            >>>     print(f"SMA(20): {sma.current_value}")
        """
        symbol_data = self.get_symbol_data(symbol)
        if not symbol_data:
            return None
        
        return symbol_data.indicators.get(indicator_key)
    
    def get_indicator_value(
        self,
        symbol: str,
        indicator_key: str,
        field: Optional[str] = None
    ) -> Optional[float]:
        """Get indicator value directly.
        
        Args:
            symbol: Stock symbol
            indicator_key: Indicator key
            field: Field name for multi-value indicators (e.g., "upper" for BB)
        
        Returns:
            Indicator value or None
        
        Examples:
            >>> # Single-value indicator
            >>> sma_value = session_data.get_indicator_value("AAPL", "sma_20_5m")
            >>> # Result: 182.50
            
            >>> # Multi-value indicator
            >>> bb_upper = session_data.get_indicator_value("AAPL", "bbands_20_5m", "upper")
            >>> # Result: 185.30
        """
        indicator = self.get_indicator(symbol, indicator_key)
        if not indicator or not indicator.valid:
            return None
        
        value = indicator.current_value
        
        # Handle multi-value indicators (dictionaries)
        if isinstance(value, dict):
            if field is None:
                raise ValueError(
                    f"Indicator {indicator_key} returns multiple values. "
                    f"Specify field: {list(value.keys())}"
                )
            return value.get(field)
        
        # Single value
        if field is not None:
            raise ValueError(
                f"Indicator {indicator_key} returns single value, "
                f"but field '{field}' was specified"
            )
        return value
    
    def get_all_indicators(
        self,
        symbol: str,
        indicator_type: Optional[str] = None
    ) -> Dict[str, IndicatorData]:
        """Get all indicators for a symbol.
        
        Args:
            symbol: Stock symbol
            indicator_type: Filter by "session" or "historical" (None = all)
        
        Returns:
            Dict of {indicator_key: IndicatorData}
        
        Example:
            >>> indicators = session_data.get_all_indicators("AAPL", "session")
            >>> for key, ind in indicators.items():
            >>>     if ind.valid:
            >>>         print(f"{key}: {ind.current_value}")
        """
        symbol_data = self.get_symbol_data(symbol)
        if not symbol_data:
            return {}
        
        if indicator_type is None:
            return symbol_data.indicators
        
        # Filter by type
        return {
            key: ind for key, ind in symbol_data.indicators.items()
            if ind.type == indicator_type
        }
    
    def is_indicator_ready(
        self,
        symbol: str,
        indicator_key: str
    ) -> bool:
        """Check if indicator has completed warmup.
        
        Args:
            symbol: Stock symbol
            indicator_key: Indicator key
        
        Returns:
            True if indicator is valid (warmup complete)
        
        Example:
            >>> if session_data.is_indicator_ready("AAPL", "sma_20_5m"):
            >>>     value = session_data.get_indicator_value("AAPL", "sma_20_5m")
        """
        indicator = self.get_indicator(symbol, indicator_key)
        return indicator.valid if indicator else False
```

---

## Usage Examples

### **Example 1: Simple Moving Average**

```python
# In AnalysisEngine
def analyze_trend(self, symbol: str):
    """Check if price above SMA(20) on 5m."""
    
    # Get current price
    bars = self.session_data.get_bars(symbol, "5m", limit=1)
    if not bars:
        return
    
    current_price = bars[0].close
    
    # Get SMA(20) on 5m
    sma_20 = self.session_data.get_indicator_value(symbol, "sma_20_5m")
    
    if sma_20 is None:
        logger.warning(f"{symbol}: SMA(20) not ready yet (warmup)")
        return
    
    # Compare
    if current_price > sma_20:
        logger.info(f"{symbol}: Price {current_price} above SMA {sma_20} - BULLISH")
    else:
        logger.info(f"{symbol}: Price {current_price} below SMA {sma_20} - BEARISH")
```

### **Example 2: Multi-Value Indicator (Bollinger Bands)**

```python
def check_bollinger_bands(self, symbol: str):
    """Check if price touching Bollinger Bands."""
    
    # Get current price
    bars = self.session_data.get_bars(symbol, "5m", limit=1)
    if not bars:
        return
    
    current_price = bars[0].close
    
    # Get Bollinger Bands (returns dict with upper/middle/lower)
    bb_upper = self.session_data.get_indicator_value(symbol, "bbands_20_5m", "upper")
    bb_lower = self.session_data.get_indicator_value(symbol, "bbands_20_5m", "lower")
    bb_middle = self.session_data.get_indicator_value(symbol, "bbands_20_5m", "middle")
    
    if bb_upper is None:
        logger.warning(f"{symbol}: Bollinger Bands not ready")
        return
    
    # Check position
    if current_price >= bb_upper:
        logger.info(f"{symbol}: Price at upper band - OVERBOUGHT")
    elif current_price <= bb_lower:
        logger.info(f"{symbol}: Price at lower band - OVERSOLD")
    else:
        logger.info(f"{symbol}: Price in normal range")
```

### **Example 3: Historical Context (20-day high/low)**

```python
def check_breakout(self, symbol: str):
    """Check if price breaking 20-day high."""
    
    # Get current price
    bars = self.session_data.get_bars(symbol, "1m", limit=1)
    if not bars:
        return
    
    current_price = bars[0].close
    
    # Get 20-day high/low
    day_20_high = self.session_data.get_indicator_value(symbol, "high_low_20_1d", "high")
    day_20_low = self.session_data.get_indicator_value(symbol, "high_low_20_1d", "low")
    
    if day_20_high is None:
        logger.warning(f"{symbol}: 20-day high/low not ready")
        return
    
    # Check breakout
    if current_price > day_20_high:
        logger.info(f"{symbol}: BREAKOUT! Price {current_price} > 20-day high {day_20_high}")
    elif current_price < day_20_low:
        logger.info(f"{symbol}: BREAKDOWN! Price {current_price} < 20-day low {day_20_low}")
```

### **Example 4: Multiple Indicators (Strategy)**

```python
def momentum_strategy(self, symbol: str):
    """Check multiple indicators for entry signal."""
    
    # Check if all indicators ready
    required = ["sma_20_5m", "rsi_14_5m", "vwap_1m", "high_low_20_1d"]
    
    for ind_key in required:
        if not self.session_data.is_indicator_ready(symbol, ind_key):
            logger.warning(f"{symbol}: Waiting for {ind_key} warmup")
            return
    
    # Get current price
    bars = self.session_data.get_bars(symbol, "5m", limit=1)
    current_price = bars[0].close
    
    # Get indicators
    sma_20 = self.session_data.get_indicator_value(symbol, "sma_20_5m")
    rsi_14 = self.session_data.get_indicator_value(symbol, "rsi_14_5m")
    vwap = self.session_data.get_indicator_value(symbol, "vwap_1m")
    day_20_high = self.session_data.get_indicator_value(symbol, "high_low_20_1d", "high")
    
    # Strategy logic
    bullish_signals = []
    
    if current_price > sma_20:
        bullish_signals.append("Above SMA(20)")
    
    if rsi_14 < 30:
        bullish_signals.append("RSI oversold")
    
    if current_price > vwap:
        bullish_signals.append("Above VWAP")
    
    if current_price > day_20_high:
        bullish_signals.append("Breaking 20-day high")
    
    # Entry signal
    if len(bullish_signals) >= 3:
        logger.info(f"{symbol}: STRONG BUY - Signals: {bullish_signals}")
```

### **Example 5: Get All Indicators**

```python
def print_all_indicators(self, symbol: str):
    """Print all indicators for debugging."""
    
    # Get all session indicators
    session_indicators = self.session_data.get_all_indicators(symbol, "session")
    
    print(f"\n{symbol} - Session Indicators:")
    print("=" * 60)
    for key, ind in session_indicators.items():
        if ind.valid:
            value_str = (
                f"{ind.current_value:.2f}" 
                if isinstance(ind.current_value, float) 
                else str(ind.current_value)
            )
            print(f"  {key:20} = {value_str}")
        else:
            print(f"  {key:20} = [WARMUP]")
    
    # Get all historical indicators
    historical_indicators = self.session_data.get_all_indicators(symbol, "historical")
    
    print(f"\n{symbol} - Historical Indicators:")
    print("=" * 60)
    for key, ind in historical_indicators.items():
        if ind.valid:
            value_str = (
                f"{ind.current_value:.2f}" 
                if isinstance(ind.current_value, float) 
                else str(ind.current_value)
            )
            print(f"  {key:20} = {value_str}")
```

---

## Config Examples with Nd and Nw

### **Multi-Timeframe High/Low**

```json
{
  "data_requirements": {
    "symbols": ["AAPL"],
    "bars": ["1m", "5m", "1d", "1w"],
    "indicators": {
      "historical": [
        {
          "name": "high_low",
          "period": 3,
          "interval": "1d",
          "comment": "3-day high/low for short-term S/R"
        },
        {
          "name": "high_low",
          "period": 20,
          "interval": "1d",
          "comment": "20-day high/low for medium-term S/R"
        },
        {
          "name": "high_low",
          "period": 4,
          "interval": "1w",
          "comment": "4-week high/low for swing trading"
        },
        {
          "name": "high_low",
          "period": 13,
          "interval": "1w",
          "comment": "13-week (quarter) high/low"
        }
      ]
    }
  }
}
```

**SessionData will have**:
- `high_low_3_1d` → 3-day high/low
- `high_low_20_1d` → 20-day high/low
- `high_low_4_1w` → 4-week high/low
- `high_low_13_1w` → 13-week high/low

**Access**:
```python
# 3-day high
day_3_high = session_data.get_indicator_value("AAPL", "high_low_3_1d", "high")

# 20-day low
day_20_low = session_data.get_indicator_value("AAPL", "high_low_20_1d", "low")

# 4-week high
week_4_high = session_data.get_indicator_value("AAPL", "high_low_4_1w", "high")

# 13-week low
week_13_low = session_data.get_indicator_value("AAPL", "high_low_13_1w", "low")
```

---

## Implementation in SessionData

### **Enhanced SymbolSessionData**

```python
@dataclass
class SymbolSessionData:
    """Session data for a single symbol - Enhanced with indicators."""
    symbol: str
    base_interval: str
    
    # Existing: Bar data
    bars: Dict[str, BarIntervalData] = field(default_factory=dict)
    
    # NEW: Indicator data
    indicators: Dict[str, IndicatorData] = field(default_factory=dict)
    
    # Existing: Other fields
    quotes: Optional[QuoteData] = None
    volume: int = 0
    high: float = 0.0
    low: float = float('inf')
    last_price: float = 0.0
    last_update: Optional[datetime] = None
```

### **Indicator Update Flow**

```python
class IndicatorManager:
    """Manages indicator calculation and storage."""
    
    def update_indicators(
        self,
        symbol: str,
        interval: str,
        new_bar: BarData
    ):
        """Update indicators when new bar arrives.
        
        Called by:
        - DataProcessor (on new base interval bar)
        - Session Coordinator (on derived bar generation)
        """
        symbol_data = self.session_data.get_symbol_data(symbol)
        
        # Get indicators for this symbol/interval
        indicators_to_update = [
            ind for ind in symbol_data.indicator_configs
            if ind.interval == interval
        ]
        
        for config in indicators_to_update:
            # Get historical bars (enough for warmup)
            bars = self.session_data.get_bars(
                symbol, 
                interval, 
                limit=config.warmup_bars()
            )
            
            # Calculate indicator
            result = calculate_indicator(
                bars=bars,
                config=config,
                symbol=symbol,
                previous_result=self._get_previous_result(symbol, config)
            )
            
            # Store in SessionData
            indicator_key = self._make_key(config)
            
            symbol_data.indicators[indicator_key] = IndicatorData(
                name=config.name,
                type=config.type,
                interval=config.interval,
                current_value=result.value,
                historical_values=None,  # Optional: store full history
                last_updated=result.timestamp,
                valid=result.valid
            )
    
    def _make_key(self, config: IndicatorConfig) -> str:
        """Generate indicator key.
        
        Examples:
            sma, period=20, interval=5m → "sma_20_5m"
            vwap, interval=1m → "vwap_1m"
            high_low, period=20, interval=1d → "high_low_20_1d"
        """
        if config.period > 0:
            return f"{config.name}_{config.period}_{config.interval}"
        else:
            return f"{config.name}_{config.interval}"
```

---

## Summary

### **High/Low Support** ✅

| Format | Config | Storage Key | Description |
|--------|--------|-------------|-------------|
| **Nd** (N days) | `{"name": "high_low", "period": 20, "interval": "1d"}` | `high_low_20_1d` | 20-day high/low |
| **Nw** (N weeks) | `{"name": "high_low", "period": 4, "interval": "1w"}` | `high_low_4_1w` | 4-week high/low |
| **Nm** (N minutes) | `{"name": "high_low", "period": 30, "interval": "1m"}` | `high_low_30_1m` | 30-minute high/low |

**Same indicator, different intervals** - Unified implementation!

### **SessionData API** ✅

```python
# Get indicator value (simple)
value = session_data.get_indicator_value("AAPL", "sma_20_5m")

# Get multi-value field
bb_upper = session_data.get_indicator_value("AAPL", "bbands_20_5m", "upper")

# Check if ready
if session_data.is_indicator_ready("AAPL", "rsi_14_5m"):
    rsi = session_data.get_indicator_value("AAPL", "rsi_14_5m")

# Get all indicators
all_indicators = session_data.get_all_indicators("AAPL")
session_only = session_data.get_all_indicators("AAPL", "session")
historical_only = session_data.get_all_indicators("AAPL", "historical")
```

### **Documentation Status** ✅

- ✅ SessionData indicator API documented
- ✅ Nd and Nw high/low support clarified
- ✅ Usage examples for AnalysisEngine
- ✅ Indicator key naming convention
- ✅ Multi-value indicator access
- ✅ Config examples

---

## **Next**: Update Implementation Plan

This API will be implemented in **Phase 3: Indicator Manager** (see INDICATOR_IMPLEMENTATION_PLAN.md)
