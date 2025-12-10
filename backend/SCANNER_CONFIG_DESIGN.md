# Scanner Configuration Design - Final

## Core Principles

1. **Universe from File**: Symbol lists loaded from text files
2. **Hardcoded Logic**: Criteria and indicators in scanner source code
3. **Simple Config**: Only scheduling and universe file path
4. **Separated APIs**: Historical vs Session bars

---

## Configuration Schema

```json
{
  "scanners": [
    {
      "module": "scanners.module_path",
      "enabled": true,
      
      "pre_session": true|false,
      "regular_session": null | [
        {
          "start": "HH:MM",
          "end": "HH:MM",
          "interval": "Nm"
        }
      ],
      
      "config": {
        "universe": "path/to/universe.txt"
      }
    }
  ]
}
```

### Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `module` | string | Python module path (name derived from this) |
| `enabled` | boolean | Enable/disable scanner |
| `pre_session` | boolean | Run once before session |
| `regular_session` | array\|null | Session schedules |
| `config.universe` | string | Path to universe file |

**Note**: Scanner name is automatically derived from module path.
- `scanners.gap_scanner` → name: `gap_scanner`
- `scanners.custom.my_scanner` → name: `my_scanner`

**Implementation**:
```python
def derive_scanner_name(module_path: str) -> str:
    """Derive scanner name from module path."""
    return module_path.split('.')[-1]

# Examples:
# "scanners.gap_scanner" → "gap_scanner"
# "scanners.examples.gap_scanner_complete" → "gap_scanner_complete"
```

### What's NOT in Config

❌ **Criteria** - Hardcoded in scanner source (e.g., `MIN_GAP_PERCENT = 2.0`)  
❌ **Indicators** - Hardcoded in scanner source (e.g., `SMA(20)`)  
❌ **Thresholds** - Hardcoded in scanner source (e.g., `MIN_VOLUME = 1_000_000`)  

---

## Universe File Format

```
# Lines starting with # are comments
# Blank lines ignored

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
   ├─ sp500.txt
   ├─ sp500_sample.txt       # For testing
   ├─ nasdaq100.txt
   ├─ nasdaq100_sample.txt   # For testing
   ├─ dow30.txt
   └─ custom.txt
```

---

## Scanner Source Code Pattern

```python
class MyScanner(BaseScanner):
    """Scanner description.
    
    HARDCODED Criteria (not in config):
    - Criterion 1
    - Criterion 2
    
    HARDCODED Indicators (not in config):
    - Indicator 1
    - Indicator 2
    """
    
    # HARDCODED CRITERIA (not in config)
    MIN_THRESHOLD = 2.0
    MAX_THRESHOLD = 500.0
    
    def setup(self, context):
        # Load universe from file
        universe_file = self.config.get("universe")
        self._universe = self._load_universe_from_file(universe_file)
        
        for symbol in self._universe:
            # Provision data
            context.session_data.add_historical_bars(symbol, "1d", days=5)
            
            # HARDCODED indicators (not from config)
            context.session_data.add_indicator(symbol, "sma", {
                "period": 20,
                "interval": "1d"
            })
        
        return True
    
    def scan(self, context):
        results = []
        
        for symbol in self._universe:
            # Query data
            bar = context.session_data.get_latest_bar(symbol, "1d")
            
            # Apply HARDCODED criteria
            if bar.close >= self.MIN_THRESHOLD:
                results.append(symbol)
                context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)
    
    def _load_universe_from_file(self, file_path: str) -> List[str]:
        """Load symbols from file."""
        symbols = []
        with open(file_path, 'r') as f:
            for line in f:
                symbol = line.strip().upper()
                if symbol and not symbol.startswith('#'):
                    symbols.append(symbol)
        return symbols
```

---

## Adhoc APIs (Used by Scanner)

### Historical Bars (No Streaming)

```python
session_data.add_historical_bars(
    symbol: str,
    interval: str,
    days: int
) → bool
```

**Use Case**: Pre-market screening with prior day's data  
**Example**: `add_historical_bars("AAPL", "1d", days=5)`

---

### Session Bars (Streaming, No Historical)

```python
session_data.add_session_bars(
    symbol: str,
    interval: str
) → bool
```

**Use Case**: Intraday scanning with live data  
**Example**: `add_session_bars("AAPL", "1m")`

---

### Indicator Registration

```python
session_data.add_indicator(
    symbol: str,
    indicator_type: str,
    config: dict
) → bool
```

**Use Case**: Add specific indicator for criteria  
**Example**:
```python
add_indicator("AAPL", "sma", {
    "period": 20,
    "interval": "1d"
})
```

---

### Full Symbol Addition (Idempotent)

```python
session_data.add_symbol(
    symbol: str
) → bool
```

**Use Case**: Upgrade qualifying symbol to full strategy symbol  
**Triggers**: Load ALL streams, indicators, historical from session_config  
**Idempotent**: Safe to call multiple times

---

## Complete Example

### session_config.json

```json
{
  "symbols": ["AAPL", "MSFT"],
  
  "scanners": [
    {
      "module": "scanners.gap_scanner",
      "enabled": true,
      
      "pre_session": true,
      "regular_session": null,
      
      "config": {
        "universe": "data/universes/sp500.txt"
      }
    }
  ]
}
```

### scanners/gap_scanner.py

```python
class Scanner(BaseScanner):
    """Gap scanner.
    
    HARDCODED Criteria:
    - Gap >= 2% from previous close
    - Volume >= 1,000,000
    """
    
    MIN_GAP = 2.0
    MIN_VOLUME = 1_000_000
    
    def setup(self, context):
        universe_file = self.config.get("universe")
        self._universe = self._load_universe_from_file(universe_file)
        
        for symbol in self._universe:
            context.session_data.add_historical_bars(symbol, "1d", days=5)
        
        return True
    
    def scan(self, context):
        results = []
        
        for symbol in self._universe:
            bars = context.session_data.get_historical_bars(symbol, "1d")
            if len(bars) >= 2:
                gap = ((bars[-1].close - bars[-2].close) / bars[-2].close) * 100
                
                if gap >= self.MIN_GAP and bars[-1].volume >= self.MIN_VOLUME:
                    results.append(symbol)
                    context.session_data.add_symbol(symbol)
        
        return ScanResult(symbols=results)
```

### data/universes/sp500.txt

```
# SP500 Universe
AAPL
MSFT
GOOGL
TSLA
# ... 496 more
```

---

## Lifecycle

### Pre-Session Scanner

```
1. SessionCoordinator initialization
   ↓
2. ScannerManager.load_scanners()
   ↓
3. scanner.setup(context)
   → Load universe from file (500 symbols)
   → add_historical_bars() for each
   ↓
4. scanner.scan(context)  [ONCE]
   → Query historical data
   → Apply hardcoded criteria
   → Find 3-5 qualifying symbols
   → add_symbol() for each
   ↓
5. Session starts
   → Scanner does NOT run again
   → Qualifying symbols trade normally
```

### Regular Session Scanner

```
1. SessionCoordinator initialization
   ↓
2. ScannerManager.load_scanners()
   ↓
3. scanner.setup(context)
   → Load universe from file (500 symbols)
   → add_session_bars() for each (live streaming)
   ↓
4. Session starts
   ↓
5. scanner.scan(context)  [Every 5m]
   → Query live data
   → Apply hardcoded criteria
   → Find qualifying symbols
   → add_symbol() for each (idempotent)
   ↓
6. Repeat step 5 per schedule
```

---

## Benefits

✅ **Simple Config**: Only universe file path  
✅ **Hardcoded Logic**: Criteria and indicators in source (version controlled)  
✅ **Easy to Read**: Config shows what's running, source shows how  
✅ **File-Based Universe**: Reusable symbol lists  
✅ **Clear Separation**: Historical vs Session data  
✅ **Idempotent**: Safe to call add_symbol() repeatedly  

---

## Summary

### Config Contains:
- Scanner module path
- Schedule (pre-session / regular session)
- Universe file path

### Scanner Source Contains:
- Criteria (hardcoded constants)
- Indicators (hardcoded in setup)
- Logic (scan implementation)

### Universe File Contains:
- Symbol list (one per line)
- Comments (lines starting with #)

**This design is clean, simple, and production-ready!** 🎯
