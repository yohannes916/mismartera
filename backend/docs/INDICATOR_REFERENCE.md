# Indicator Reference Guide

**All indicators calculated from OHLCV data only** (Open, High, Low, Close, Volume)

---

## Quick Reference Table

| Indicator | Type | Inputs | Warmup | Range | Description |
|-----------|------|--------|--------|-------|-------------|
| **SMA** | Trend | Close, N | N bars | Any | Simple moving average |
| **EMA** | Trend | Close, N | N bars | Any | Exponential moving average |
| **WMA** | Trend | Close, N | N bars | Any | Weighted moving average |
| **VWAP** | Trend | OHLCV | Session | Any | Volume-weighted avg price |
| **RSI** | Momentum | Close, N | N+1 | 0-100 | Relative strength index |
| **MACD** | Momentum | Close | 26 | Any | Moving avg convergence/divergence |
| **Stochastic** | Momentum | HLC, N | N | 0-100 | Stochastic oscillator |
| **ATR** | Volatility | HLC, N | N+1 | >0 | Average true range |
| **BB** | Volatility | Close, N | N | Any | Bollinger bands |
| **OBV** | Volume | CV | Session | Any | On-balance volume |

**Legend**: H=High, L=Low, C=Close, V=Volume, N=Period

---

## Trend Indicators

### SMA (Simple Moving Average)

**Purpose**: Smooth price data to identify trend direction  
**Formula**: `SUM(close[i] for i in last N) / N`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any positive value  

**Interpretation**:
- Price above SMA = Uptrend
- Price below SMA = Downtrend
- Crossovers signal trend changes

**Config Example**:
```json
{
  "name": "sma",
  "period": 20,
  "interval": "5m",
  "type": "trend"
}
```

**Common Periods**:
- 9, 20, 50 (short-term)
- 100, 200 (long-term)

---

### EMA (Exponential Moving Average)

**Purpose**: Weighted average giving more weight to recent prices  
**Formula**: `EMA = α * Price + (1 - α) * EMA_prev` where `α = 2/(N+1)`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any positive value  

**Interpretation**:
- Faster response to price changes than SMA
- Less lag, more sensitive
- Common for crossover strategies

**Config Example**:
```json
{
  "name": "ema",
  "period": 12,
  "interval": "5m",
  "type": "trend"
}
```

**Common Periods**:
- 8, 12, 21 (fast)
- 26, 50 (slow)

**Stateful**: Yes (requires previous EMA value)

---

### WMA (Weighted Moving Average)

**Purpose**: Linear weighting (most recent = highest weight)  
**Formula**: `SUM(close[i] * weight[i]) / SUM(weights)`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any positive value  

**Interpretation**:
- More responsive than SMA
- Less smooth than EMA
- Linear weight decay

**Config Example**:
```json
{
  "name": "wma",
  "period": 10,
  "interval": "5m",
  "type": "trend"
}
```

---

### VWAP (Volume-Weighted Average Price)

**Purpose**: Institutional benchmark, intraday support/resistance  
**Formula**: `SUM(Typical_Price * Volume) / SUM(Volume)`  
where `Typical_Price = (High + Low + Close) / 3`  
**Inputs**: OHLCV  
**Warmup**: Session start  
**Range**: Any positive value  

**Interpretation**:
- Price above VWAP = bullish
- Price below VWAP = bearish
- Often acts as support/resistance
- Resets each session

**Config Example**:
```json
{
  "name": "vwap",
  "interval": "1m",
  "type": "trend",
  "note": "No period needed - cumulative from session open"
}
```

**Best Interval**: 1m or 1s (most accurate with finer resolution)  
**Stateful**: Yes (cumulative from session start)

---

### DEMA (Double Exponential Moving Average)

**Purpose**: Reduced lag vs EMA  
**Formula**: `DEMA = 2*EMA - EMA(EMA)`  
**Inputs**: Closing prices, Period  
**Warmup**: 2N bars  
**Range**: Any positive value  

**Interpretation**:
- Faster than EMA
- Less smooth
- Good for quick reversals

**Config Example**:
```json
{
  "name": "dema",
  "period": 20,
  "interval": "15m",
  "type": "trend"
}
```

---

### TEMA (Triple Exponential Moving Average)

**Purpose**: Even less lag than DEMA  
**Formula**: `TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))`  
**Inputs**: Closing prices, Period  
**Warmup**: 3N bars  
**Range**: Any positive value  

**Interpretation**:
- Fastest response
- Most noise
- Best for volatile markets

**Config Example**:
```json
{
  "name": "tema",
  "period": 9,
  "interval": "5m",
  "type": "trend"
}
```

---

### HMA (Hull Moving Average)

**Purpose**: Low lag, smooth curve  
**Formula**: `HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any positive value  

**Interpretation**:
- Balance of speed and smoothness
- Good for trend identification
- Fewer whipsaws than EMA

**Config Example**:
```json
{
  "name": "hma",
  "period": 16,
  "interval": "15m",
  "type": "trend"
}
```

---

## Momentum Indicators

### RSI (Relative Strength Index)

**Purpose**: Measure overbought/oversold conditions  
**Formula**: `RSI = 100 - (100 / (1 + RS))` where `RS = Avg_Gain / Avg_Loss`  
**Inputs**: Closing prices, Period  
**Warmup**: N+1 bars  
**Range**: 0-100  

**Interpretation**:
- **>70**: Overbought (potential sell signal)
- **<30**: Oversold (potential buy signal)
- **50**: Neutral
- Divergence = trend reversal

**Config Example**:
```json
{
  "name": "rsi",
  "period": 14,
  "interval": "5m",
  "type": "momentum"
}
```

**Common Periods**: 9, 14, 21

---

### MACD (Moving Average Convergence Divergence)

**Purpose**: Trend following and momentum indicator  
**Formula**:
- `MACD_Line = EMA(12) - EMA(26)`
- `Signal_Line = EMA(MACD_Line, 9)`
- `Histogram = MACD_Line - Signal_Line`

**Inputs**: Closing prices  
**Warmup**: 26 bars  
**Range**: Any (can be negative)  

**Interpretation**:
- **MACD > Signal**: Bullish
- **MACD < Signal**: Bearish
- **Crossover**: Buy/sell signal
- **Histogram expanding**: Strengthening trend
- **Divergence**: Reversal warning

**Config Example**:
```json
{
  "name": "macd",
  "interval": "15m",
  "type": "momentum",
  "params": {
    "fast": 12,
    "slow": 26,
    "signal": 9
  }
}
```

**Output**: Dictionary with `macd`, `signal`, `histogram` keys

---

### Stochastic Oscillator

**Purpose**: Compare close to price range  
**Formula**:
- `%K = (Close - Low_N) / (High_N - Low_N) * 100`
- `%D = SMA(%K, smooth)`

**Inputs**: High, Low, Close, Period  
**Warmup**: N + smooth bars  
**Range**: 0-100  

**Interpretation**:
- **>80**: Overbought
- **<20**: Oversold
- **%K crosses %D**: Buy/sell signal

**Config Example**:
```json
{
  "name": "stochastic",
  "period": 14,
  "interval": "5m",
  "type": "momentum",
  "params": {
    "smooth": 3
  }
}
```

**Output**: Dictionary with `k` and `d` keys

---

### CCI (Commodity Channel Index)

**Purpose**: Measure deviation from average price  
**Formula**: `CCI = (Typical_Price - SMA(Typical_Price)) / (0.015 * Mean_Deviation)`  
**Inputs**: High, Low, Close, Period  
**Warmup**: N bars  
**Range**: Unbounded (typically -200 to +200)  

**Interpretation**:
- **>100**: Overbought
- **<-100**: Oversold
- **Crossing zero**: Trend change

**Config Example**:
```json
{
  "name": "cci",
  "period": 20,
  "interval": "15m",
  "type": "momentum"
}
```

---

### ROC (Rate of Change)

**Purpose**: Measure momentum as percentage change  
**Formula**: `ROC = (Close - Close[N]) / Close[N] * 100`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any (percentage)  

**Interpretation**:
- **>0**: Upward momentum
- **<0**: Downward momentum
- **Divergence**: Reversal signal

**Config Example**:
```json
{
  "name": "roc",
  "period": 12,
  "interval": "5m",
  "type": "momentum"
}
```

---

### MOM (Momentum)

**Purpose**: Raw price change  
**Formula**: `MOM = Close - Close[N]`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: Any  

**Interpretation**:
- **>0**: Bullish momentum
- **<0**: Bearish momentum
- Magnitude shows strength

**Config Example**:
```json
{
  "name": "mom",
  "period": 10,
  "interval": "5m",
  "type": "momentum"
}
```

---

### Williams %R

**Purpose**: Overbought/oversold indicator  
**Formula**: `%R = (High_N - Close) / (High_N - Low_N) * -100`  
**Inputs**: High, Low, Close, Period  
**Warmup**: N bars  
**Range**: -100 to 0  

**Interpretation**:
- **>-20**: Overbought
- **<-80**: Oversold
- **Inverted scale** (negative values)

**Config Example**:
```json
{
  "name": "williams_r",
  "period": 14,
  "interval": "5m",
  "type": "momentum"
}
```

---

## Volatility Indicators

### ATR (Average True Range)

**Purpose**: Measure market volatility  
**Formula**: `ATR = SMA(True_Range, N)`  
where `TR = max(H-L, abs(H-prev_C), abs(L-prev_C))`  
**Inputs**: High, Low, Close, Period  
**Warmup**: N+1 bars  
**Range**: >0  

**Interpretation**:
- **High ATR**: High volatility (wider stops)
- **Low ATR**: Low volatility (tighter stops)
- Position sizing tool
- Stop loss placement

**Config Example**:
```json
{
  "name": "atr",
  "period": 14,
  "interval": "5m",
  "type": "volatility"
}
```

**Common Uses**:
- Stop loss: Entry ± (2 * ATR)
- Position sizing: Risk / ATR
- Breakout confirmation

---

### Bollinger Bands

**Purpose**: Volatility envelope around mean  
**Formula**:
- `Middle = SMA(Close, N)`
- `Upper = Middle + (StdDev * num_std)`
- `Lower = Middle - (StdDev * num_std)`

**Inputs**: Closing prices, Period, # of std devs  
**Warmup**: N bars  
**Range**: Any  

**Interpretation**:
- **Price at upper band**: Overbought
- **Price at lower band**: Oversold
- **Squeeze**: Low volatility (expansion coming)
- **Expansion**: High volatility
- **Bandwidth**: (Upper - Lower) / Middle

**Config Example**:
```json
{
  "name": "bbands",
  "period": 20,
  "interval": "5m",
  "type": "volatility",
  "params": {
    "num_std": 2.0
  }
}
```

**Output**: Dictionary with `upper`, `middle`, `lower`, `bandwidth` keys

**Common Settings**: 20-period, 2 std devs

---

### Keltner Channels

**Purpose**: Volatility bands using ATR  
**Formula**:
- `Middle = EMA(Close, N)`
- `Upper = Middle + (ATR * multiplier)`
- `Lower = Middle - (ATR * multiplier)`

**Inputs**: OHLC, Period, Multiplier  
**Warmup**: N+1 bars  
**Range**: Any  

**Interpretation**:
- Similar to Bollinger Bands
- Uses ATR instead of std dev
- Less sensitive to price spikes

**Config Example**:
```json
{
  "name": "keltner",
  "period": 20,
  "interval": "15m",
  "type": "volatility",
  "params": {
    "atr_period": 10,
    "multiplier": 2.0
  }
}
```

**Output**: Dictionary with `upper`, `middle`, `lower` keys

---

### Donchian Channels

**Purpose**: Breakout indicator  
**Formula**:
- `Upper = Highest_High(N)`
- `Lower = Lowest_Low(N)`
- `Middle = (Upper + Lower) / 2`

**Inputs**: High, Low, Period  
**Warmup**: N bars  
**Range**: Any  

**Interpretation**:
- **Price breaks upper**: Buy signal
- **Price breaks lower**: Sell signal
- Channel width = volatility

**Config Example**:
```json
{
  "name": "donchian",
  "period": 20,
  "interval": "15m",
  "type": "volatility"
}
```

**Output**: Dictionary with `upper`, `middle`, `lower` keys

---

### Standard Deviation

**Purpose**: Measure price dispersion  
**Formula**: `StdDev = sqrt(SUM((Close[i] - Mean)^2) / N)`  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: >0  

**Interpretation**:
- **High**: High volatility
- **Low**: Low volatility
- Used in Bollinger Bands

**Config Example**:
```json
{
  "name": "stddev",
  "period": 20,
  "interval": "5m",
  "type": "volatility"
}
```

---

### Historical Volatility

**Purpose**: Annualized volatility  
**Formula**: `HV = StdDev(log_returns) * sqrt(252)` (for daily)  
**Inputs**: Closing prices, Period  
**Warmup**: N bars  
**Range**: >0 (percentage)  

**Interpretation**:
- Measures price variability
- Used for options pricing
- Risk assessment

**Config Example**:
```json
{
  "name": "histvol",
  "period": 20,
  "interval": "1d",
  "type": "volatility"
}
```

---

## Volume Indicators

### OBV (On-Balance Volume)

**Purpose**: Cumulative volume direction  
**Formula**:
- If `Close > prev_Close`: `OBV += Volume`
- If `Close < prev_Close`: `OBV -= Volume`
- If `Close == prev_Close`: `OBV unchanged`

**Inputs**: Close, Volume  
**Warmup**: Session start  
**Range**: Any  

**Interpretation**:
- **Rising OBV + Rising Price**: Strong uptrend
- **Falling OBV + Falling Price**: Strong downtrend
- **Divergence**: Reversal warning

**Config Example**:
```json
{
  "name": "obv",
  "interval": "1m",
  "type": "volume",
  "note": "Cumulative from session start"
}
```

**Stateful**: Yes (cumulative)

---

### PVT (Price-Volume Trend)

**Purpose**: Similar to OBV with price weighting  
**Formula**: `PVT += Volume * ((Close - prev_Close) / prev_Close)`  
**Inputs**: Close, Volume  
**Warmup**: Session start  
**Range**: Any  

**Interpretation**:
- Weighted version of OBV
- More sensitive to price changes

**Config Example**:
```json
{
  "name": "pvt",
  "interval": "1m",
  "type": "volume"
}
```

**Stateful**: Yes (cumulative)

---

### Volume SMA

**Purpose**: Average volume  
**Formula**: `SMA(Volume, N)`  
**Inputs**: Volume, Period  
**Warmup**: N bars  
**Range**: >0  

**Interpretation**:
- **Volume > SMA**: High activity
- **Volume < SMA**: Low activity
- Breakout confirmation

**Config Example**:
```json
{
  "name": "volume_sma",
  "period": 20,
  "interval": "5m",
  "type": "volume"
}
```

---

### Volume Ratio

**Purpose**: Current volume vs average  
**Formula**: `Volume / SMA(Volume, N)`  
**Inputs**: Volume, Period  
**Warmup**: N bars  
**Range**: >0 (ratio)  

**Interpretation**:
- **>1**: Above average volume
- **<1**: Below average volume
- **>2**: Very high volume (potential breakout)

**Config Example**:
```json
{
  "name": "volume_ratio",
  "period": 20,
  "interval": "1m",
  "type": "volume"
}
```

---

## Support/Resistance Indicators

### Pivot Points

**Purpose**: Intraday support/resistance levels  
**Formula**:
- `PP = (High + Low + Close) / 3` (from previous day)
- `R1 = 2*PP - Low`, `R2 = PP + (High - Low)`, `R3 = High + 2*(PP - Low)`
- `S1 = 2*PP - High`, `S2 = PP - (High - Low)`, `S3 = Low - 2*(High - PP)`

**Inputs**: Daily OHLC  
**Warmup**: 1 day  
**Range**: Any  

**Interpretation**:
- **Price at R1/R2/R3**: Resistance levels
- **Price at S1/S2/S3**: Support levels
- Breakout targets

**Config Example**:
```json
{
  "name": "pivot_points",
  "interval": "1d",
  "type": "support_resistance"
}
```

**Output**: Dictionary with `pp`, `r1`, `r2`, `r3`, `s1`, `s2`, `s3` keys

---

### High/Low N

**Purpose**: Highest high and lowest low (works on ANY interval)  
**Formula**:
- `High_N = max(High[i] for i in last N)`
- `Low_N = min(Low[i] for i in last N)`

**Inputs**: High, Low, Period, Interval  
**Warmup**: N bars  
**Range**: Any  

**Interpretation**:
- **Breakout above High_N**: Buy signal
- **Breakdown below Low_N**: Sell signal
- Channel boundaries
- Support/Resistance levels

**Unified Implementation**:
- Apply to `"1d"` → N-day high/low (e.g., 20-day)
- Apply to `"1w"` → N-week high/low (e.g., 4-week)
- Apply to `"15m"` → N-period high/low on 15m bars
- Apply to `"1m"` → N-period high/low on 1m bars

**Config Examples**:
```json
{
  "name": "high_low",
  "period": 20,
  "interval": "1d",
  "type": "support_resistance",
  "comment": "20-day high/low (Nd format)"
}
```

```json
{
  "name": "high_low",
  "period": 4,
  "interval": "1w",
  "type": "support_resistance",
  "comment": "4-week high/low (Nw format)"
}
```

```json
{
  "name": "high_low",
  "period": 30,
  "interval": "15m",
  "type": "support_resistance",
  "comment": "30-period high/low on 15m bars"
}
```

**Output**: Dictionary with `high` and `low` keys

**Common Uses**:
- **20-day high/low**: Intermediate-term breakout levels
- **4-week high/low**: Swing trading support/resistance
- **52-week high/low**: Long-term extremes
- **Intraday**: 30-minute high/low for scalping

---

### Swing High

**Purpose**: Local peak detection  
**Formula**: Bar is swing high if it's the highest in window of N bars before and after  
**Inputs**: High, Period  
**Warmup**: 2N + 1 bars  
**Range**: Boolean or price  

**Interpretation**:
- Marks local resistance
- Useful for trendline drawing
- Reversal points

**Config Example**:
```json
{
  "name": "swing_high",
  "period": 5,
  "interval": "15m",
  "type": "support_resistance"
}
```

---

### Swing Low

**Purpose**: Local trough detection  
**Formula**: Bar is swing low if it's the lowest in window of N bars before and after  
**Inputs**: Low, Period  
**Warmup**: 2N + 1 bars  
**Range**: Boolean or price  

**Interpretation**:
- Marks local support
- Useful for trendline drawing
- Reversal points

**Config Example**:
```json
{
  "name": "swing_low",
  "period": 5,
  "interval": "15m",
  "type": "support_resistance"
}
```

---

## Historical Context Indicators

### Average Volume (Daily)

**Purpose**: Average daily volume  
**Formula**: `SMA(Daily_Volume, N_days)`  
**Inputs**: Daily volume, Period  
**Warmup**: N days  
**Range**: >0  

**Interpretation**:
- Baseline for volume analysis
- Compare current volume to average
- Liquidity measure

**Config Example**:
```json
{
  "name": "avg_volume",
  "period": 5,
  "unit": "days",
  "type": "historical"
}
```

---

### Average Range (Daily)

**Purpose**: Average daily range  
**Formula**: `SMA(High - Low, N_days)`  
**Inputs**: Daily high, low, Period  
**Warmup**: N days  
**Range**: >0  

**Interpretation**:
- Expected daily movement
- Position sizing
- Target setting

**Config Example**:
```json
{
  "name": "avg_range",
  "period": 10,
  "unit": "days",
  "type": "historical"
}
```

---

### Average True Range (Daily)

**Purpose**: Average daily true range  
**Formula**: `ATR on daily bars`  
**Inputs**: Daily HLC, Period  
**Warmup**: N+1 days  
**Range**: >0  

**Interpretation**:
- Accounts for gaps
- Better than simple range
- Risk management

**Config Example**:
```json
{
  "name": "atr_daily",
  "period": 14,
  "unit": "days",
  "type": "historical"
}
```

---

### High/Low N Days

**Purpose**: Multi-day high/low (same as High/Low N on daily interval)  
**Formula**: Highest high and lowest low over N days  
**Inputs**: Daily HL, Period  
**Warmup**: N days  
**Range**: Any  

**Interpretation**:
- Key support/resistance
- Breakout levels
- Position management

**Note**: This is the SAME indicator as `high_low` applied to daily bars.

**Config Example** (Two equivalent ways):
```json
{
  "name": "high_low",
  "period": 20,
  "interval": "1d",
  "type": "historical",
  "comment": "Preferred: Use standard high_low on 1d interval"
}
```

**Storage Key**: `high_low_20_1d`

**Output**: Dictionary with `high` and `low` keys

**Common Periods**:
- 3-day: Short-term S/R
- 10-day: Swing trading
- 20-day: Intermediate breakout levels
- 52-day: Quarter highs/lows
- 200-day: Long-term extremes

---

### Gap Statistics

**Purpose**: Gap frequency and average size  
**Formula**:
- Gap = `Open - prev_Close`
- Count gaps, average size

**Inputs**: Daily OC, Period  
**Warmup**: N days  
**Range**: Various  

**Interpretation**:
- Market behavior
- Expected gap size
- Risk assessment

**Config Example**:
```json
{
  "name": "gap_stats",
  "period": 20,
  "unit": "days",
  "type": "historical"
}
```

**Output**: Dictionary with `avg_gap`, `gap_count`, `gap_up_count`, `gap_down_count` keys

---

### Range Ratio

**Purpose**: Current range vs average  
**Formula**: `(Current_High - Current_Low) / Avg_Range`  
**Inputs**: Daily HL, Period  
**Warmup**: N days  
**Range**: >0 (ratio)  

**Interpretation**:
- **>1**: Expansion day
- **<1**: Contraction day
- Volatility context

**Config Example**:
```json
{
  "name": "range_ratio",
  "period": 20,
  "unit": "days",
  "type": "historical"
}
```

---

## Common Strategy Combinations

### Trend Following
```json
{
  "indicators": {
    "session": [
      {"name": "ema", "period": 12, "interval": "5m"},
      {"name": "ema", "period": 26, "interval": "5m"},
      {"name": "atr", "period": 14, "interval": "5m"}
    ]
  }
}
```

### Mean Reversion
```json
{
  "indicators": {
    "session": [
      {"name": "bbands", "period": 20, "interval": "5m"},
      {"name": "rsi", "period": 14, "interval": "5m"},
      {"name": "vwap", "interval": "1m"}
    ]
  }
}
```

### Breakout Trading
```json
{
  "indicators": {
    "session": [
      {"name": "donchian", "period": 20, "interval": "15m"},
      {"name": "volume_ratio", "period": 20, "interval": "5m"},
      {"name": "atr", "period": 14, "interval": "5m"}
    ],
    "historical": [
      {"name": "high_low_daily", "period": 20, "unit": "days"},
      {"name": "avg_volume", "period": 10, "unit": "days"}
    ]
  }
}
```

### Scalping
```json
{
  "indicators": {
    "session": [
      {"name": "vwap", "interval": "1m"},
      {"name": "ema", "period": 9, "interval": "1m"},
      {"name": "rsi", "period": 9, "interval": "1m"}
    ]
  }
}
```

---

## Notes

- **All indicators** use OHLCV data only
- **Stateful indicators** (EMA, OBV, VWAP) require previous values
- **Warmup period** is the minimum bars needed for valid output
- **Session indicators** reset each trading day
- **Historical indicators** use daily bars for context
- **Multi-value indicators** (BB, MACD, etc.) return dictionaries
