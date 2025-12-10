# SymbolSessionData Metadata Integration

## Core Principle

**`meets_session_config_requirements` is a property of `SymbolSessionData` itself.**

No separate metadata structure needed. When the symbol is deleted, the flag goes with it automatically.

---

## SymbolSessionData Structure (Updated)

```python
@dataclass
class SymbolSessionData:
    """Session data for a single symbol (with integrated metadata)."""
    symbol: str
    
    # Bar data
    bars: Dict[str, IntervalBars]  # {interval: IntervalBars}
    
    # Indicator data
    indicators: Dict[str, IndicatorData]
    
    # Quality data
    quality: Dict[str, float]  # {interval: quality_score}
    
    # METADATA (INTEGRATED) ✅
    meets_session_config_requirements: bool = False
    added_by: str = "config"  # "config", "strategy", "scanner", "adhoc"
    auto_provisioned: bool = False
    added_at: Optional[datetime] = None
    upgraded_from_adhoc: bool = False
    
    def __init__(
        self,
        symbol: str,
        meets_session_config_requirements: bool = False,
        added_by: str = "config",
        auto_provisioned: bool = False
    ):
        """Initialize SymbolSessionData with metadata flags."""
        self.symbol = symbol
        self.bars = {}
        self.indicators = {}
        self.quality = {}
        
        # Set metadata at creation time
        self.meets_session_config_requirements = meets_session_config_requirements
        self.added_by = added_by
        self.auto_provisioned = auto_provisioned
        self.added_at = None
        self.upgraded_from_adhoc = False
```

---

## Creation Scenarios

### Scenario 1: Pre-Session Config Symbol (Full Loading)

```python
# In _load_session_data() after Step 0 validation
for symbol in validated_symbols:
    symbol_data = SymbolSessionData(
        symbol=symbol,
        meets_session_config_requirements=True,  # Full loading
        added_by="config",
        auto_provisioned=False
    )
    session_data.register_symbol(symbol, symbol_data)
    
    # Then load historical, indicators, quality, etc.
```

### Scenario 2: Mid-Session Full Addition (add_symbol)

```python
# In add_symbol() → _load_symbols_mid_session()
def add_symbol(self, symbol: str, added_by: str = "strategy") -> bool:
    # Validate
    result = self._validate_symbol_for_loading(symbol)
    if not result.can_proceed:
        return False
    
    # Create with full config requirements
    symbol_data = SymbolSessionData(
        symbol=symbol,
        meets_session_config_requirements=True,  # Full loading
        added_by=added_by,  # "strategy" or "scanner"
        auto_provisioned=False
    )
    symbol_data.added_at = self._time_manager.get_current_time()
    
    session_data.register_symbol(symbol, symbol_data)
    
    # Then load historical, indicators, quality, etc.
```

### Scenario 3: Adhoc Bar Addition (Auto-Provision)

```python
# In SessionData.add_bar() when symbol doesn't exist
def add_bar(self, symbol: str, interval: str, bar: BarData):
    if symbol not in self._symbols:
        logger.info(f"{symbol}: Auto-provisioning for adhoc bar")
        
        # Create with minimal structure
        symbol_data = SymbolSessionData(
            symbol=symbol,
            meets_session_config_requirements=False,  # Adhoc
            added_by="adhoc",
            auto_provisioned=True
        )
        symbol_data.added_at = time_manager.get_current_time()
        
        self._symbols[symbol] = symbol_data
    
    # Add bar to structure
    # ...
```

### Scenario 4: Upgrade from Adhoc to Full

```python
# In add_symbol() when symbol exists as adhoc
def add_symbol(self, symbol: str, added_by: str = "strategy") -> bool:
    existing = self.session_data.get_symbol_data(symbol)
    
    if existing and not existing.meets_session_config_requirements:
        logger.info(f"{symbol}: Upgrading from adhoc to full")
        
        # Update flags on EXISTING object
        existing.meets_session_config_requirements = True
        existing.upgraded_from_adhoc = True
        existing.added_by = added_by  # Update to requester
        
        # Load missing pieces (historical, indicators, quality)
        self._manage_historical_data(symbols=[symbol])
        self._register_session_indicators(symbols=[symbol])
        # ... etc
```

---

## Deletion (Automatic Cleanup)

```python
def remove_symbol(self, symbol: str) -> bool:
    """Remove symbol (metadata goes with it automatically)."""
    with self._symbol_operation_lock:
        # Delete SymbolSessionData (includes metadata)
        if symbol in self.session_data._symbols:
            del self.session_data._symbols[symbol]
            # No separate metadata to clean up! ✅
        
        # Clear from queues
        for key in list(self._bar_queues.keys()):
            if key[0] == symbol:
                del self._bar_queues[key]
    
    return True
```

---

## JSON Serialization

```python
class SymbolSessionData:
    def to_json(self) -> dict:
        """Serialize to JSON (includes metadata)."""
        return {
            "symbol": self.symbol,
            "bars": {interval: bars.to_json() for interval, bars in self.bars.items()},
            "indicators": {name: ind.to_json() for name, ind in self.indicators.items()},
            "quality": self.quality,
            
            # METADATA (inline) ✅
            "metadata": {
                "meets_session_config_requirements": self.meets_session_config_requirements,
                "added_by": self.added_by,
                "auto_provisioned": self.auto_provisioned,
                "added_at": self.added_at.isoformat() if self.added_at else None,
                "upgraded_from_adhoc": self.upgraded_from_adhoc
            }
        }
```

### Example JSON Output

```json
{
  "symbols": {
    "AAPL": {
      "symbol": "AAPL",
      "bars": {...},
      "indicators": {...},
      "quality": {...},
      "metadata": {
        "meets_session_config_requirements": true,
        "added_by": "config",
        "auto_provisioned": false,
        "added_at": null,
        "upgraded_from_adhoc": false
      }
    },
    "TSLA": {
      "symbol": "TSLA",
      "bars": {...},
      "indicators": {...},
      "quality": {...},
      "metadata": {
        "meets_session_config_requirements": false,
        "added_by": "adhoc",
        "auto_provisioned": true,
        "added_at": "2024-12-10T10:30:00",
        "upgraded_from_adhoc": false
      }
    }
  }
}
```

---

## CSV Export

```python
# In session_data_display.py
def export_to_csv(self):
    """Export session data including metadata."""
    for symbol, symbol_data in session_data._symbols.items():
        row[f"{symbol}_meets_config_req"] = symbol_data.meets_session_config_requirements
        row[f"{symbol}_added_by"] = symbol_data.added_by
        row[f"{symbol}_auto_provisioned"] = symbol_data.auto_provisioned
```

### Example CSV

```
timestamp,AAPL_1m_bars,AAPL_meets_config_req,AAPL_added_by,TSLA_1m_bars,TSLA_meets_config_req,TSLA_added_by
09:30:00,1,True,config,0,False,adhoc
09:31:00,2,True,config,1,False,adhoc
```

---

## SessionData API (No Changes Needed)

```python
class SessionData:
    def __init__(self):
        self._symbols: Dict[str, SymbolSessionData] = {}
        # NO separate metadata dict! ✅
    
    def register_symbol(self, symbol: str, symbol_data: SymbolSessionData):
        """Register symbol (metadata included in object)."""
        self._symbols[symbol] = symbol_data
    
    def get_symbol_data(self, symbol: str) -> Optional[SymbolSessionData]:
        """Get symbol data (includes metadata)."""
        return self._symbols.get(symbol)
    
    def clear(self):
        """Clear all symbols (metadata cleared automatically)."""
        self._symbols.clear()
```

---

## Benefits

### 1. Simplicity ✅
- One object, not two
- No synchronization needed
- No separate cleanup

### 2. Automatic Cleanup ✅
- Delete symbol → metadata gone automatically
- Clear session → all metadata cleared
- No orphaned metadata

### 3. Type Safety ✅
- Metadata is part of the dataclass
- IDE autocomplete works
- No optional lookups

### 4. Consistency ✅
- Metadata always present
- No "missing metadata" edge cases
- Default values defined in dataclass

---

## Implementation Changes

### What to Remove ❌
- ~~`SymbolMetadata` dataclass~~ (not needed)
- ~~`SessionData._symbol_metadata` dict~~ (not needed)
- ~~`get_symbol_metadata()` method~~ (not needed)
- ~~`set_symbol_metadata()` method~~ (not needed)

### What to Add ✅
- Add fields to `SymbolSessionData` dataclass
- Update `SymbolSessionData.__init__()` to accept metadata params
- Update creation sites to pass metadata
- Update `to_json()` to include metadata

### Migration Path
1. Add new fields to `SymbolSessionData` with defaults
2. Update creation sites gradually
3. Update serialization
4. No breaking changes (defaults handle missing values)

---

## Summary

**Simpler architecture**:
- Metadata lives ON the symbol object itself
- No separate tracking structure
- Automatic cleanup when symbol deleted
- Same structure for config and adhoc symbols
- Flag determines behavior, not structure

**This is the right design!** Much cleaner than a separate metadata structure.
