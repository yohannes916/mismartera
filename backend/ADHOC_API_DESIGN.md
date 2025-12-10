# Adhoc Data Management API - Final Design

## Overview

Clean separation between **lightweight screening data** and **full strategy symbols**.

---

## API Categories

### 1. Adhoc Data APIs (Lightweight, No Config Changes)

For scanning/screening purposes - minimal data provisioning.

```python
# Adhoc session bars (real-time/intraday)
session_data.add_session_bars(symbol: str, interval: str) → bool

# Adhoc historical bars (pre-session warmup)
session_data.add_historical_bars(symbol: str, interval: str, period: int) → bool

# Adhoc indicator
session_data.add_indicator(symbol: str, type: str, config: dict) → bool
```

### 2. Symbol Management APIs (Full Symbol, Config Changes)

For strategy symbols - full data provisioning from session_config.

```python
# Add full symbol (triggers complete loading)
session_data.add_symbol(symbol: str) → bool

# Remove symbol (clears everything)
session_data.remove_symbol(symbol: str) → bool

# Lock symbol (prevent removal)
session_data.lock_symbol(symbol: str, reason: str) → bool

# Unlock symbol (allow removal)
session_data.unlock_symbol(symbol: str) → bool

# Check if locked
session_data.is_symbol_locked(symbol: str) → bool
```

---

## Detailed API Specifications

### Adhoc APIs

#### 1. add_session_bars()

```python
def add_session_bars(self, symbol: str, interval: str) -> bool:
    """Add session bars for a symbol adhoc (lightweight).
    
    Use Case:
        Scanner wants to screen with minimal real-time data.
    
    What it does:
        - Registers symbol if not exists
        - Adds interval to bars structure
        - Starts streaming queue for this interval
        - Does NOT load historical data
        - Does NOT trigger session_config requirements
    
    Args:
        symbol: Symbol to add bars for
        interval: Bar interval (e.g., "1m", "5m")
    
    Returns:
        True if successful, False if already exists
    
    Example:
        # Scanner wants 1m bars for SPY (no historical)
        session_data.add_session_bars("SPY", "1m")
        
        # Now can query live bars
        bar = session_data.get_latest_bar("SPY", "1m")
    """
    with self._lock:
        # Register symbol if not exists
        if symbol not in self._symbols:
            self.register_symbol(symbol)
        
        symbol_data = self._symbols[symbol]
        
        # Check if already exists
        if interval in symbol_data.bars:
            logger.debug(f"{symbol}: {interval} bars already exist")
            return False
        
        # Add interval structure
        symbol_data.bars[interval] = IntervalData(
            interval=interval,
            data=deque(maxlen=5000),
            derived=False,
            updated=False
        )
        
        # Mark as adhoc (not from config)
        if not hasattr(symbol_data, '_adhoc_intervals'):
            symbol_data._adhoc_intervals = set()
        symbol_data._adhoc_intervals.add(interval)
        
        logger.info(f"{symbol}: Added adhoc session bars for {interval}")
        return True
```

---

#### 2. add_historical_bars()

```python
def add_historical_bars(
    self,
    symbol: str,
    interval: str,
    period: int
) -> bool:
    """Add historical bars for a symbol adhoc (lightweight warmup).
    
    Use Case:
        Scanner needs historical data for indicator calculation.
    
    What it does:
        - Registers symbol if not exists
        - Adds interval to historical bars structure
        - Queues historical data load (period days back)
        - Does NOT add to session_config
        - Does NOT trigger other requirements
    
    Args:
        symbol: Symbol to add bars for
        interval: Bar interval (e.g., "1d")
        period: Number of days of history (e.g., 5)
    
    Returns:
        True if successful
    
    Example:
        # Scanner wants 5 days of 1d bars for warmup
        session_data.add_historical_bars("SPY", "1d", period=5)
        
        # After loading completes, can query
        bars = session_data.get_historical_bars("SPY", "1d")
    """
    with self._lock:
        # Register symbol if not exists
        if symbol not in self._symbols:
            self.register_symbol(symbol)
        
        symbol_data = self._symbols[symbol]
        
        # Add to historical structure
        if interval not in symbol_data.historical.bars:
            symbol_data.historical.bars[interval] = HistoricalIntervalData(
                interval=interval,
                data_by_date={},
                quality=0.0,
                gaps=[]
            )
        
        # Queue historical load request
        self._pending_historical_loads.append({
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "adhoc": True  # Mark as adhoc
        })
        
        logger.info(f"{symbol}: Queued adhoc historical load for {interval} ({period} days)")
        return True
```

---

#### 3. add_indicator()

```python
def add_indicator(
    self,
    symbol: str,
    indicator_type: str,
    config: dict
) -> bool:
    """Add indicator for a symbol adhoc (automatic bar provisioning).
    
    Use Case:
        Scanner needs specific indicator for criteria.
    
    What it does:
        - Registers symbol if not exists
        - Creates IndicatorConfig from params
        - **Calls requirement_analyzer to determine needed bars**
        - **Automatically provisions required bars (historical + session)**
        - Registers with IndicatorManager
        - Adds metadata to session_data
        - Does NOT trigger session_config requirements
    
    This uses the SAME unified routine as session_config indicators:
    - requirement_analyzer determines base intervals needed
    - Provisions historical bars for warmup
    - Provisions session bars for real-time updates
    
    Args:
        symbol: Symbol to add indicator for
        indicator_type: Indicator name (e.g., "sma", "rsi")
        config: Indicator configuration dict
            {
                "period": 20,
                "interval": "1d",
                "params": {}
            }
    
    Returns:
        True if successful, False if already exists
    
    Example:
        # Scanner wants SMA(20) on daily bars
        session_data.add_indicator(
            "SPY",
            "sma",
            {
                "period": 20,
                "interval": "1d",
                "params": {}
            }
        )
        
        # This AUTOMATICALLY:
        # 1. Calls requirement_analyzer
        # 2. Determines that 1d bars are needed
        # 3. Provisions historical 1d bars (20+ days for warmup)
        # 4. Provisions session 1d bars (for updates)
        # 5. Registers indicator with IndicatorManager
        
        # After calculation, can query
        ind = session_data.get_indicator("SPY", "sma_20_1d")
    """
    from app.indicators import IndicatorConfig, IndicatorType
    
    from app.threads.quality.requirement_analyzer import requirement_analyzer
    
    with self._lock:
        # Register symbol if not exists
        if symbol not in self._symbols:
            self.register_symbol(symbol)
        
        symbol_data = self._symbols[symbol]
        
        # Create IndicatorConfig
        indicator_config = IndicatorConfig(
            name=indicator_type,
            type=IndicatorType(config.get("type", "trend")),
            period=config.get("period", 0),
            interval=config["interval"],
            params=config.get("params", {})
        )
        
        key = indicator_config.make_key()
        
        # Check if already exists
        if key in symbol_data.indicators:
            logger.debug(f"{symbol}: Indicator {key} already exists")
            return False
        
        # UNIFIED ROUTINE: Use requirement_analyzer to determine needed bars
        # Same as session_config indicator processing
        requirements = requirement_analyzer.analyze_indicator_requirements(
            indicator_config=indicator_config,
            warmup_multiplier=2.0  # 2x period for warmup
        )
        
        # Provision required bars automatically
        for interval in requirements.required_intervals:
            # Add historical bars for warmup
            if requirements.historical_days > 0:
                self.add_historical_bars(
                    symbol=symbol,
                    interval=interval,
                    days=requirements.historical_days
                )
            
            # Add session bars for real-time updates
            self.add_session_bars(
                symbol=symbol,
                interval=interval
            )
        
        # Add metadata (invalid until calculated)
        from app.indicators import IndicatorData
        symbol_data.indicators[key] = IndicatorData(
            name=indicator_type,
            type=config.get("type", "trend"),
            interval=config["interval"],
            current_value=None,
            last_updated=None,
            valid=False
        )
        
        # Register with IndicatorManager
        if self._indicator_manager:
            self._indicator_manager.register_symbol_indicators(
                symbol=symbol,
                indicators=[indicator_config],
                historical_bars=None  # Will calculate when bars available
            )
        
        logger.info(
            f"{symbol}: Added adhoc indicator {key} "
            f"(provisioned {len(requirements.required_intervals)} intervals)"
        )
        return True
```

---

### Symbol Management APIs

#### 1. add_symbol()

```python
def add_symbol(self, symbol: str) -> bool:
    """Add symbol as full strategy symbol (idempotent).
    
    Use Case:
        Scanner found qualifying symbol, add for trading.
    
    What it does:
        - Adds symbol to session_config.symbols (persistent)
        - Triggers FULL data loading from session_config:
          ✓ All streams from config
          ✓ All indicators from config
          ✓ Historical data per config
        - Notifies SessionCoordinator
        - IDEMPOTENT: Multiple calls ignored (no error)
    
    Args:
        symbol: Symbol to add
    
    Returns:
        True if newly added, False if already exists
    
    Example:
        # Scanner found TSLA
        session_data.add_symbol("TSLA")
        
        # Triggers:
        # - Load streams: ["1m", "5m", "15m"]
        # - Load indicators: [sma_20_5m, ema_9_5m, rsi_14_5m, ...]
        # - Load historical: 30 days
        
        # Multiple calls OK (idempotent)
        session_data.add_symbol("TSLA")  # Ignored
        session_data.add_symbol("TSLA")  # Ignored
    """
    symbol = symbol.upper()
    
    with self._lock:
        # Check if already a config symbol
        if symbol in self._config_symbols:
            logger.debug(f"{symbol}: Already a strategy symbol")
            return False
        
        # Add to config symbols set
        self._config_symbols.add(symbol)
        
        # Add to session_config (persistent)
        if symbol not in self.session_config.session_data_config.symbols:
            self.session_config.session_data_config.symbols.append(symbol)
        
        logger.info(f"{symbol}: Added as strategy symbol")
        
        # Notify SessionCoordinator to provision full requirements
        if self._session_coordinator:
            asyncio.create_task(
                self._session_coordinator.add_symbol_mid_session(symbol)
            )
        
        return True
```

---

#### 2. remove_symbol()

```python
def remove_symbol(self, symbol: str) -> bool:
    """Remove symbol from session (config and data).
    
    Use Case:
        Symbol no longer needed, clean up resources.
    
    What it does:
        - Checks if symbol is locked (prevents removal if locked)
        - Removes from session_config.symbols
        - Removes from session_data (all data)
        - Notifies SessionCoordinator
    
    Args:
        symbol: Symbol to remove
    
    Returns:
        True if removed, False if locked or not found
    
    Example:
        # Remove SPY from session
        if session_data.remove_symbol("SPY"):
            print("Removed")
        else:
            print("Locked or not found")
    """
    symbol = symbol.upper()
    
    with self._lock:
        # Check if locked
        if self.is_symbol_locked(symbol):
            logger.warning(
                f"{symbol}: Cannot remove - locked "
                f"({self._symbol_locks.get(symbol, 'unknown reason')})"
            )
            return False
        
        # Check if exists
        if symbol not in self._symbols:
            logger.debug(f"{symbol}: Not found, nothing to remove")
            return False
        
        # Remove from config
        if symbol in self._config_symbols:
            self._config_symbols.remove(symbol)
        
        if symbol in self.session_config.session_data_config.symbols:
            self.session_config.session_data_config.symbols.remove(symbol)
        
        # Remove from session_data (calls existing method)
        # This removes: bars, quotes, ticks, indicators, historical
        del self._symbols[symbol]
        
        # Clean up active streams
        streams_to_remove = [
            key for key in self._active_streams.keys()
            if key[0] == symbol
        ]
        for key in streams_to_remove:
            del self._active_streams[key]
        
        logger.info(f"{symbol}: Removed from session")
        return True
```

---

#### 3. lock_symbol() / unlock_symbol()

```python
def lock_symbol(self, symbol: str, reason: str) -> bool:
    """Lock symbol to prevent removal.
    
    Use Case:
        AnalysisEngine has open position, prevent removal.
    
    Args:
        symbol: Symbol to lock
        reason: Reason for lock (e.g., "open_position")
    
    Returns:
        True if locked
    
    Example:
        # Lock AAPL (has open position)
        session_data.lock_symbol("AAPL", "open_position")
        
        # Try to remove (will fail)
        session_data.remove_symbol("AAPL")  # → False
    """
    symbol = symbol.upper()
    
    with self._lock:
        if not hasattr(self, '_symbol_locks'):
            self._symbol_locks = {}
        
        self._symbol_locks[symbol] = reason
        logger.info(f"{symbol}: Locked ({reason})")
        return True


def unlock_symbol(self, symbol: str) -> bool:
    """Unlock symbol to allow removal.
    
    Use Case:
        Position closed, allow removal.
    
    Args:
        symbol: Symbol to unlock
    
    Returns:
        True if unlocked
    """
    symbol = symbol.upper()
    
    with self._lock:
        if hasattr(self, '_symbol_locks') and symbol in self._symbol_locks:
            reason = self._symbol_locks.pop(symbol)
            logger.info(f"{symbol}: Unlocked (was: {reason})")
            return True
        
        logger.debug(f"{symbol}: Not locked")
        return False


def is_symbol_locked(self, symbol: str) -> bool:
    """Check if symbol is locked.
    
    Args:
        symbol: Symbol to check
    
    Returns:
        True if locked
    """
    symbol = symbol.upper()
    
    if not hasattr(self, '_symbol_locks'):
        return False
    
    return symbol in self._symbol_locks
```

---

## Complete Scanner Example

```python
from scanners.base import BaseScanner, ScanContext, ScanResult


class GapScanner(BaseScanner):
    """Gap scanner using adhoc APIs.
    
    Note: add_indicator() automatically provisions required bars
    via requirement_analyzer (unified routine).
    """
    
    def setup(self, context: ScanContext) -> bool:
        """Setup lightweight screening data for universe."""
        
        # Load universe (500 symbols)
        self._universe = self._load_universe()
        
        logger.info(f"Setting up scanner for {len(self._universe)} symbols")
        
        # Provision minimal data for screening
        for symbol in self._universe:
            # Add indicator - AUTOMATICALLY provisions bars!
            # No need to manually add bars
            context.session_data.add_indicator(
                symbol,
                indicator_type="sma",
                config={
                    "period": 20,
                    "interval": "1d",
                    "type": "trend",
                    "params": {}
                }
            )
            # This AUTOMATICALLY (via requirement_analyzer):
            # 1. Determines 1d bars are needed
            # 2. Provisions historical 1d bars (40 days for SMA(20) warmup)
            # 3. Provisions session 1d bars (for real-time updates)
        
        logger.info(f"Scanner setup complete: {len(self._universe)} symbols provisioned")
        return True
    
    def scan(self, context: ScanContext) -> ScanResult:
        """Scan universe and add qualifying symbols."""
        
        results = []
        metadata = {}
        
        # Scan lightweight universe
        for symbol in self._universe:
            # Query adhoc data
            bar = context.session_data.get_latest_bar(symbol, "1d")
            if not bar:
                continue
            
            sma_indicator = context.session_data.get_indicator(symbol, "sma_20_1d")
            if not sma_indicator or not sma_indicator.valid:
                continue
            
            # Apply criteria
            price = bar.close
            sma = sma_indicator.current_value
            gap_pct = ((price - sma) / sma) * 100
            
            # Check criteria
            if gap_pct >= 2.0:  # 2% above SMA
                results.append(symbol)
                metadata[symbol] = {
                    "gap_percent": gap_pct,
                    "price": price,
                    "sma": sma
                }
                
                # Add as FULL strategy symbol
                # This triggers complete loading from session_config
                logger.info(f"Scanner found: {symbol} (gap: {gap_pct:.2f}%)")
                
                # IDEMPOTENT: Can call multiple times, will be ignored
                context.session_data.add_symbol(symbol)
                
                # No need to track state!
                # session_data handles duplicate adds internally
        
        logger.info(f"Scan complete: {len(results)} symbols found")
        
        return ScanResult(
            symbols=results,
            metadata=metadata
        )
    
    def _load_universe(self) -> List[str]:
        """Load SP500 universe."""
        universe_name = self.config.get("universe", "sp500")
        
        # Load from file
        # For now, example universe
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
            "TSLA", "META", "TSM", "V", "WMT",
            # ... 490 more symbols
        ]
```

---

## Usage Examples

### Example 1: Scanner Screening

```python
# Scanner setup (once)
for symbol in sp500:
    # Lightweight: Just daily bars + 1 indicator
    session_data.add_historical_bars(symbol, "1d", period=5)
    session_data.add_indicator(symbol, "sma", {"period": 20, "interval": "1d"})

# Scanner scan (periodic)
for symbol in sp500:
    bar = session_data.get_latest_bar(symbol, "1d")
    sma = session_data.get_indicator(symbol, "sma_20_1d")
    
    if meets_criteria(bar, sma):
        # UPGRADE to full symbol
        session_data.add_symbol(symbol)  # ← Triggers full loading
```

**Result:**
- 500 symbols with minimal data (screening)
- 3-5 symbols with full data (trading)

---

### Example 2: Analysis Engine Position Management

```python
class AnalysisEngine:
    def on_signal_enter(self, symbol, signal):
        """Lock symbol when opening position."""
        
        # Open position
        self.portfolio.open_position(symbol, ...)
        
        # Lock symbol (prevent removal)
        self.session_data.lock_symbol(symbol, "open_position")
    
    def on_signal_exit(self, symbol, signal):
        """Unlock symbol when closing position."""
        
        # Close position
        self.portfolio.close_position(symbol, ...)
        
        # Unlock symbol (allow removal)
        self.session_data.unlock_symbol(symbol)
```

---

### Example 3: Idempotent Add Symbol

```python
# Scanner runs every 5 minutes
# Same symbol might qualify multiple times

# 09:35 - First scan
session_data.add_symbol("TSLA")  # → True (newly added, triggers loading)

# 09:40 - Second scan
session_data.add_symbol("TSLA")  # → False (already exists, ignored)

# 09:45 - Third scan
session_data.add_symbol("TSLA")  # → False (already exists, ignored)

# No duplicate processing!
# No state tracking needed in scanner!
```

---

### Example 4: Remove Symbol with Lock Protection

```python
# Add symbol
session_data.add_symbol("AAPL")

# Open position
session_data.lock_symbol("AAPL", "open_position")

# Try to remove (FAILS - locked)
session_data.remove_symbol("AAPL")  # → False

# Close position
session_data.unlock_symbol("AAPL")

# Now can remove
session_data.remove_symbol("AAPL")  # → True
```

---

## Data Flow Comparison

### Adhoc APIs (Screening)

```
session_data.add_historical_bars("SPY", "1d", 5)
    ↓
Register symbol (if needed)
    ↓
Add historical interval structure
    ↓
Queue historical load (5 days)
    ↓
Historical loader loads 5 days of 1d bars
    ↓
Bars available for querying
    ↓
get_latest_bar("SPY", "1d") ✅

Cost: Minimal (5 days × 1 interval = 5 bars)
```

### Symbol Management API (Trading)

```
session_data.add_symbol("SPY")
    ↓
Add to session_config.symbols
    ↓
SessionCoordinator.add_symbol_mid_session("SPY")
    ↓
Analyze requirements from session_config:
  - streams: ["1m", "5m", "15m"]
  - indicators: [sma, ema, rsi, macd, ...]
  - historical: 30 days
    ↓
Load historical (30 days × 3 intervals = 90 days-worth)
    ↓
Register all indicators (20+)
    ↓
Calculate initial values
    ↓
Start streaming all intervals
    ↓
Symbol ready for AnalysisEngine ✅

Cost: Full (30 days × 3 intervals × 20 indicators = extensive)
```

---

## Summary

### Adhoc APIs (Lightweight)
```python
add_session_bars(symbol, interval)       # Live bars only
add_historical_bars(symbol, interval, period)  # Historical warmup
add_indicator(symbol, type, config)      # Specific indicator
```

**Use Case**: Scanner screening (500 symbols)

---

### Symbol Management APIs (Full-Featured)
```python
add_symbol(symbol)           # Full strategy symbol (idempotent)
remove_symbol(symbol)        # Clean removal (lock-protected)
lock_symbol(symbol, reason)  # Prevent removal
unlock_symbol(symbol)        # Allow removal
is_symbol_locked(symbol)     # Check status
```

**Use Case**: Trading symbols (3-5 symbols)

---

### Key Principles

✅ **Separation**: Screening ≠ Trading  
✅ **Idempotent**: `add_symbol()` safe to call multiple times  
✅ **Stateless Scanner**: No need to track what's added  
✅ **Lock Protection**: AnalysisEngine prevents removal of active positions  
✅ **Resource Efficient**: Minimal data for screening, full data for trading  
✅ **Config Integration**: `add_symbol()` uses session_config requirements  

This is the clean, final design! 🎯
