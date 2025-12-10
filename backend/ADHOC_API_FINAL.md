# Adhoc API - Final Design (Refined)

## Core Principle

**Separation**: Historical data ≠ Session (live) data

Many scanners only need historical data (pre-market screening based on prior session).
They don't need live streaming during the session.

---

## Adhoc APIs (Final)

### 1. add_historical_bars() - Historical Data Only

```python
def add_historical_bars(
    self,
    symbol: str,
    interval: str,
    days: int
) -> bool:
    """Add historical bars for a symbol (no live streaming).
    
    Use Case:
        Scanner needs prior session data for screening.
        Pre-market gap scanner analyzing yesterday's data.
    
    What it does:
        ✓ Registers symbol (if needed)
        ✓ Queues historical load (N days back)
        ✗ Does NOT start live streaming
        ✗ Does NOT add to session_config
    
    Args:
        symbol: Symbol to add bars for
        interval: Bar interval (e.g., "1d", "1m")
        days: Number of days of history
    
    Returns:
        True if successful
    
    Example:
        # Pre-market scanner wants yesterday's data only
        session_data.add_historical_bars("SPY", "1d", days=5)
        
        # After loading, can query
        bars = session_data.get_historical_bars("SPY", "1d")
        # No live streaming! Just historical data.
    """
```

---

### 2. add_session_bars() - Live Streaming Only

```python
def add_session_bars(
    self,
    symbol: str,
    interval: str
) -> bool:
    """Add live session bars for a symbol (no historical).
    
    Use Case:
        Intraday scanner needs live bars during session.
        No historical warmup needed.
    
    What it does:
        ✓ Registers symbol (if needed)
        ✓ Adds interval structure
        ✓ Starts streaming queue
        ✗ Does NOT load historical
        ✗ Does NOT add to session_config
    
    Args:
        symbol: Symbol to add bars for
        interval: Bar interval (e.g., "1m", "5m")
    
    Returns:
        True if successful
    
    Example:
        # Intraday scanner wants live 1m bars
        session_data.add_session_bars("SPY", "1m")
        
        # Now receives live bars
        bar = session_data.get_latest_bar("SPY", "1m")
        # No historical! Just live data.
    """
```

---

### 3. add_indicator() - Indicator Registration

```python
def add_indicator(
    self,
    symbol: str,
    indicator_type: str,
    config: dict
) -> bool:
    """Add indicator for a symbol.
    
    Args:
        symbol: Symbol to add indicator for
        indicator_type: Indicator name (e.g., "sma", "rsi")
        config: Configuration dict
            {
                "period": 20,
                "interval": "1d",
                "params": {}
            }
    
    Returns:
        True if successful
    
    Example:
        session_data.add_indicator("SPY", "sma", {
            "period": 20,
            "interval": "1d"
        })
    """
```

---

### 4. Symbol Management APIs (Unchanged)

```python
add_symbol(symbol)              # Full strategy symbol (idempotent)
remove_symbol(symbol)           # Remove (lock-protected)
lock_symbol(symbol, reason)     # Prevent removal
unlock_symbol(symbol)           # Allow removal
is_symbol_locked(symbol)        # Check status
```

---

## Scanner Configuration (Refined)

### session_config.json

```json
{
  "scanners": [
    {
      "module": "scanners.gap_scanner",
      "enabled": true,
      
      "pre_session": true,
      "regular_session": null,
      
      "config": {
        "universe": "data/universes/sp500.txt"
      }
    },
    
    {
      "module": "scanners.momentum_scanner",
      "enabled": true,
      
      "pre_session": false,
      "regular_session": [
        {
          "start": "09:35",
          "end": "12:00",
          "interval": "5m"
        },
        {
          "start": "13:00",
          "end": "15:55",
          "interval": "15m"
        }
      ],
      
      "config": {
        "universe": "data/universes/sp500.txt"
      }
    },
    
    {
      "module": "scanners.hybrid_scanner",
      "enabled": true,
      
      "pre_session": true,
      "regular_session": [
        {
          "start": "09:30",
          "end": "16:00",
          "interval": "30m"
        }
      ],
      
      "config": {
        "universe": "data/universes/nasdaq100.txt"
      }
    }
  ]
}
```

**Note**: 
- Scanner name is derived from module path: `module_path.split('.')[-1]`
  - `scanners.gap_scanner` → `gap_scanner`
  - `scanners.examples.gap_scanner_complete` → `gap_scanner_complete`
- Module path must be unique (enforced by file system)

**Note**: 
- `config.universe` is a **file path** to a text file with symbols (one per line)
- Scanner criteria (e.g., `min_gap_percent`, `min_rsi`) are **hardcoded in scanner source**
- Indicators needed are **hardcoded in scanner source** (not in config)

---

## Universe File Format

Scanner universes are defined in text files with one symbol per line.

### File Structure

```
# Lines starting with # are comments
# Blank lines are ignored

AAPL
MSFT
GOOGL
TSLA
# ... more symbols
```

### File Locations

```
data/
└─ universes/
   ├─ sp500.txt           # Full SP500 list
   ├─ sp500_sample.txt    # Sample for testing
   ├─ nasdaq100.txt       # Full NASDAQ100 list
   ├─ nasdaq100_sample.txt # Sample for testing
   ├─ dow30.txt           # Dow Jones 30
   └─ custom_universe.txt # Custom lists
```

### Usage in Config

```json
{
  "config": {
    "universe": "data/universes/sp500.txt"  // ← Relative or absolute path
  }
}
```

### Loading in Scanner

```python
def _load_universe_from_file(self, file_path: str) -> List[str]:
    """Load universe symbols from text file (one per line)."""
    if not file_path:
        raise ValueError("Universe file path required in config")
    
    symbols = []
    with open(file_path, 'r') as f:
        for line in f:
            symbol = line.strip().upper()
            if symbol and not symbol.startswith('#'):
                symbols.append(symbol)
    
    return symbols
```

---

## Scanner Types & Examples

### Type 1: Pre-Session Only Scanner

**Use Case**: Screen based on prior day's data, add symbols for the session

```python
class GapScanner(BaseScanner):
    """Pre-market gap scanner (historical data only).
    
    Hardcoded criteria:
    - Gap >= 2.0% from previous close
    - Volume >= 1,000,000 shares
    - Price <= $500
    
    Indicators:
    - SMA(20) on 1d bars
    """
    
    # HARDCODED CRITERIA (not in config)
    MIN_GAP_PERCENT = 2.0
    MIN_VOLUME = 1_000_000
    MAX_PRICE = 500.0
    
    def setup(self, context):
        """Provision historical data only (no streaming)."""
        
        # Load universe from file
        self._universe = self._load_universe_from_file(
            self.config.get("universe")
        )
        
        for symbol in self._universe:
            # Historical only (no live streaming)
            context.session_data.add_historical_bars(
                symbol,
                interval="1d",
                days=5
            )
            
            # HARDCODED indicator (not from config)
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20,
                "interval": "1d"
            })
        
        return True
    
    def scan(self, context):
        """Scan once pre-market, add symbols for session."""
        
        results = []
        
        for symbol in self._universe:
            # Query historical data (no live data needed)
            bars = context.session_data.get_historical_bars(symbol, "1d")
            if not bars or len(bars) < 2:
                continue
            
            yesterday = bars[-1]
            prev_close = bars[-2].close
            
            # Apply HARDCODED criteria
            gap_pct = ((yesterday.close - prev_close) / prev_close) * 100
            
            if gap_pct >= self.MIN_GAP_PERCENT:
                if yesterday.volume >= self.MIN_VOLUME:
                    if yesterday.close <= self.MAX_PRICE:
                        results.append(symbol)
                        
                        # Add as full symbol for trading
                        context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)
    
    def teardown(self, context):
        """Cleanup after scanner completes (no more schedules).
        
        Called after the last scheduled scan.
        Use this to remove symbols that didn't qualify and are no longer needed.
        """
        # Get list of symbols we added (promoted to full strategy symbols)
        config_symbols = set(context.session_data.get_config_symbols())
        
        # Remove universe symbols that weren't promoted
        for symbol in self._universe:
            # If symbol is NOT a config symbol (wasn't promoted)
            # AND scanner provisioned it (adhoc)
            # THEN remove it to free resources
            if symbol not in config_symbols:
                # Check if symbol has adhoc data only (no positions, no locks)
                if not context.session_data.is_symbol_locked(symbol):
                    context.session_data.remove_symbol(symbol)
                    logger.debug(f"[GAP_SCANNER] Removed {symbol} (did not qualify)")
        
        logger.info(
            f"[GAP_SCANNER] Teardown complete: "
            f"Removed {len(self._universe) - len(config_symbols)} unused symbols"
        )
    
    def _load_universe_from_file(self, file_path: str) -> List[str]:
        """Load universe symbols from text file (one per line)."""
        if not file_path:
            raise ValueError("Universe file path required in config")
        
        symbols = []
        with open(file_path, 'r') as f:
            for line in f:
                symbol = line.strip().upper()
                if symbol and not symbol.startswith('#'):
                    symbols.append(symbol)
        
        return symbols
```

**Config**:
```json
{
  "module": "scanners.gap_scanner",
  "pre_session": true,        // ← Runs once before session
  "regular_session": null     // ← Never runs during session
}
```

**Lifecycle**:
```
Pre-session (clock STOPPED in backtest):
  1. setup() provisions historical bars (500 symbols × 5 days)
  2. scan() runs ONCE, finds 3-5 qualifying symbols
     → add_symbol() for each (triggers full loading)
  3. teardown() called (no more schedules left)
     → Remove 495 symbols that didn't qualify
     → Keep only 3-5 qualifying symbols
  
Session processing:
  → Process session_config requirements
  → Start streaming
  → Advance clock
  
Session runs:
  → Scanner does NOT run (no regular_session schedule)
  → Qualifying symbols trade normally
```

---

### Type 2: Regular Session Only Scanner

**Use Case**: Intraday momentum/volume scanning during session

```python
class MomentumScanner(BaseScanner):
    """Intraday momentum scanner (live data).
    
    Hardcoded criteria:
    - RSI(14) >= 70 (overbought)
    - Volume >= 1,000,000 shares
    - Price momentum sustained
    
    Indicators:
    - RSI(14) on 1m bars
    """
    
    # HARDCODED CRITERIA (not in config)
    MIN_RSI = 70
    MIN_VOLUME = 1_000_000
    
    def setup(self, context):
        """Provision live streaming (no historical)."""
        
        # Load universe from file
        self._universe = self._load_universe_from_file(
            self.config.get("universe")
        )
        
        for symbol in self._universe:
            # Live streaming only (no historical)
            context.session_data.add_session_bars(symbol, "1m")
            
            # HARDCODED indicator (not from config)
            context.session_data.add_indicator(symbol, "rsi", {
                "period": 14,
                "interval": "1m"
            })
        
        return True
    
    def scan(self, context):
        """Scan during session for momentum."""
        
        results = []
        
        for symbol in self._universe:
            # Query live data
            bar = context.session_data.get_latest_bar(symbol, "1m")
            rsi = context.session_data.get_indicator(symbol, "rsi_14_1m")
            
            if bar and rsi and rsi.valid:
                # Apply HARDCODED criteria
                if rsi.current_value >= self.MIN_RSI:
                    if bar.volume >= self.MIN_VOLUME:
                        results.append(symbol)
                        context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)
    
    def _load_universe_from_file(self, file_path: str) -> List[str]:
        """Load universe symbols from text file (one per line)."""
        if not file_path:
            raise ValueError("Universe file path required in config")
        
        symbols = []
        with open(file_path, 'r') as f:
            for line in f:
                symbol = line.strip().upper()
                if symbol and not symbol.startswith('#'):
                    symbols.append(symbol)
        
        return symbols
```

**Config**:
```json
{
  "module": "scanners.momentum_scanner",
  "pre_session": false,        // ← Does NOT run pre-session
  "regular_session": [
    {
      "start": "09:35",
      "end": "15:55",
      "interval": "5m"          // ← Runs every 5m during session
    }
  ]
}
```

**Lifecycle**:
```
Pre-session:
  1. setup() provisions live streaming (500 symbols)
  2. scan() does NOT run
  
Session starts (clock RUNNING):
  → 09:35: scan() runs, finds momentum symbols
  → 09:40: scan() runs again
  → 09:45: scan() runs again
  → ... every 5m until 15:55
  → 15:55: scan() runs (LAST scheduled scan)
  → 15:55: teardown() called (no more schedules left)
     - Remove symbols that don't have positions
     - Cleanup scanner resources
  
Session continues:
  → Scanner does NOT run again
  → Qualifying symbols continue trading
```

---

### Type 3: Hybrid Scanner

**Use Case**: Pre-market screening + intraday monitoring

```python
class HybridScanner(BaseScanner):
    """Hybrid scanner (historical + live)."""
    
    def setup(self, context):
        """Provision both historical and live data."""
        
        self._universe = self._load_universe()
        
        for symbol in self._universe:
            # Historical for pre-market analysis
            context.session_data.add_historical_bars(symbol, "1d", days=10)
            
            # Live for intraday monitoring
            context.session_data.add_session_bars(symbol, "5m")
            
            # Indicators for both
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20,
                "interval": "1d"
            })
            context.session_data.add_indicator(symbol, "rsi", {
                "period": 14,
                "interval": "5m"
            })
        
        return True
    
    def scan(self, context):
        """Scan both pre-market and intraday."""
        
        results = []
        
        for symbol in self._universe:
            # Pre-market: Check historical gap
            hist_bars = context.session_data.get_historical_bars(symbol, "1d")
            if hist_bars and len(hist_bars) >= 2:
                gap = ((hist_bars[-1].close - hist_bars[-2].close) / hist_bars[-2].close) * 100
                
                if gap >= 1.5:  # Pre-market qualifier
                    # Intraday: Check momentum
                    live_bar = context.session_data.get_latest_bar(symbol, "5m")
                    rsi = context.session_data.get_indicator(symbol, "rsi_14_5m")
                    
                    if live_bar and rsi and rsi.valid:
                        if rsi.current_value >= 60:
                            results.append(symbol)
                            context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)
```

**Config**:
```json
{
  "name": "hybrid_scanner",
  "pre_session": true,         // ← Runs once pre-market
  "regular_session": [
    {
      "start": "09:30",
      "end": "16:00",
      "interval": "30m"        // ← Also runs every 30m during session
    }
  ]
}
```

---

## SessionCoordinator Scheduling Logic

```python
class ScannerManager:
    def schedule_scanners(self):
        """Schedule scanners based on config."""
        
        for name, config in self.scanner_configs.items():
            # Pre-session scheduling
            if config.get("pre_session", False):
                self.pre_session_scanners.append(name)
            
            # Regular session scheduling
            regular = config.get("regular_session")
            if regular:
                for schedule in regular:
                    self.regular_session_schedules.append({
                        "scanner": name,
                        "start": schedule["start"],
                        "end": schedule["end"],
                        "interval": schedule["interval"]
                    })
    
    def execute_pre_session_scans(self):
        """Execute all pre-session scanners ONCE."""
        
        for name in self.pre_session_scanners:
            logger.info(f"[PRE-SESSION] Executing {name}")
            scanner = self.scanners[name]
            result = scanner.scan(context)
            self._process_result(result)
    
    def should_run_scanner(self, name, current_time):
        """Check if scanner should run now."""
        
        for schedule in self.regular_session_schedules:
            if schedule["scanner"] != name:
                continue
            
            # Check time window
            start = time.fromisoformat(schedule["start"])
            end = time.fromisoformat(schedule["end"])
            
            if not (start <= current_time.time() <= end):
                continue
            
            # Check interval
            interval_str = schedule["interval"]
            if self._matches_interval(current_time, interval_str):
                return True
        
        return False
```

---

## Comparison Table

| Scanner Type | Historical | Live | Pre-Session | Regular Session | Use Case |
|--------------|-----------|------|-------------|-----------------|----------|
| **Pre-session only** | ✅ | ❌ | ✅ | ❌ | Gap scanner, overnight screening |
| **Regular session only** | ❌ | ✅ | ❌ | ✅ | Momentum, volume breakouts |
| **Hybrid** | ✅ | ✅ | ✅ | ✅ | Combined screening + monitoring |

---

## API Usage Patterns

### Pattern 1: Pre-Session Scanner (Historical Only)

```python
# Setup
add_historical_bars("SPY", "1d", days=5)  # ← Historical only
add_indicator("SPY", "sma", {...})

# Scan (pre-market)
bars = get_historical_bars("SPY", "1d")
gap = calculate_gap(bars)
if gap >= 2.0:
    add_symbol("SPY")  # ← Full symbol for trading

# Session
# Scanner does NOT run
# SPY trades normally with full data
```

### Pattern 2: Regular Session Scanner (Live Only)

```python
# Setup
add_session_bars("SPY", "1m")  # ← Live only
add_indicator("SPY", "rsi", {...})

# Pre-session
# Scanner does NOT run

# Session (every 5m)
bar = get_latest_bar("SPY", "1m")
rsi = get_indicator("SPY", "rsi_14_1m")
if rsi.value >= 70:
    add_symbol("SPY")
```

### Pattern 3: Hybrid Scanner (Both)

```python
# Setup
add_historical_bars("SPY", "1d", days=10)  # ← Historical
add_session_bars("SPY", "5m")               # ← Live
add_indicator("SPY", "sma", {...})
add_indicator("SPY", "rsi", {...})

# Pre-session
hist_bars = get_historical_bars("SPY", "1d")
gap = calculate_gap(hist_bars)
if gap >= 1.5:
    # Pre-qualify
    pass

# Session (every 30m)
bar = get_latest_bar("SPY", "5m")
rsi = get_indicator("SPY", "rsi_14_5m")
if rsi.value >= 60 and gap >= 1.5:
    add_symbol("SPY")
```

---

## Summary of Changes

### Old Design (Combined)
```python
add_bars(symbol, intervals=["1d"], historical_days=5)
# ❌ Unclear: Does it stream? Does it load history? Both?
```

### New Design (Separated)
```python
# Clear intent: Historical only (no streaming)
add_historical_bars(symbol, "1d", days=5)

# Clear intent: Live only (no history)
add_session_bars(symbol, "1m")

# Flexible: Can use one, the other, or both
```

---

## Benefits

✅ **Clear Separation**: Historical ≠ Live  
✅ **Resource Efficient**: Only provision what you need  
✅ **Scanner Types**: Pre-session, regular session, hybrid  
✅ **Flexible Scheduling**: Multiple time windows per scanner  
✅ **Simple Intent**: API names match purpose  

This is the final, refined design! 🎯
