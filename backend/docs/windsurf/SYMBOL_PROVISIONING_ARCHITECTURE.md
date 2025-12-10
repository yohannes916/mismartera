# Symbol Provisioning Architecture - REFINED

## Core Principle

**There are TWO completely different symbol addition mechanisms:**

1. **Full Session-Config Addition** (`coordinator.add_symbol()`)
   - Explicit, comprehensive loading
   - Historical data + indicators + quality + queues
   - `meets_session_config_requirements = True`

2. **Adhoc Bar/Indicator Addition** (Scanner direct manipulation)
   - Implicit, lightweight provisioning
   - Auto-creates symbol structure if needed
   - `meets_session_config_requirements = False`

---

## Flow 1: Full Session-Config Addition

### Entry Point: `coordinator.add_symbol(symbol)`

**Purpose**: Load symbol with FULL session-config requirements

**Triggers**:
- Strategy explicitly requests symbol
- User manually adds via CLI
- Pre-session config loading

**Process**:
```python
def add_symbol(self, symbol: str) -> bool:
    """Add symbol with FULL session-config requirements."""
    
    # Check if already fully loaded
    existing = self.session_data.get_symbol_data(symbol)
    metadata = self.session_data.get_symbol_metadata(symbol)
    
    if existing and metadata and metadata.meets_session_config_requirements:
        logger.info(f"{symbol}: Already fully loaded, skipping")
        return True  # Already done
    
    if existing and metadata and not metadata.meets_session_config_requirements:
        logger.info(f"{symbol}: Exists as adhoc, UPGRADING to full session-config")
        # Will load missing pieces (historical, indicators, quality)
    
    # Add to pending for full loading
    with self._symbol_operation_lock:
        self._pending_symbols.add(symbol)
    
    return True
```

**What Gets Loaded**:
```python
def _load_symbols_mid_session(self, symbols: List[str]):
    """Full session-config loading."""
    
    for symbol in symbols:
        metadata = self.session_data.get_symbol_metadata(symbol)
        
        if not metadata:
            # New symbol: Full load
            self._register_single_symbol(symbol)
            self._manage_historical_data(symbols=[symbol])
            self._register_session_indicators(symbols=[symbol])
            self._calculate_historical_indicators(symbols=[symbol])
            self._load_queues(symbols=[symbol])
            self._calculate_historical_quality(symbols=[symbol])
            
            # Mark as fully loaded
            self.session_data.set_symbol_metadata(symbol, SymbolMetadata(
                symbol=symbol,
                meets_session_config_requirements=True,
                added_by="coordinator",
                # ... other fields
            ))
            
        elif not metadata.meets_session_config_requirements:
            # Upgrade: Load missing pieces
            logger.info(f"{symbol}: Upgrading from adhoc to full session-config")
            
            # Load what's missing
            self._manage_historical_data(symbols=[symbol])
            self._register_session_indicators(symbols=[symbol])
            self._calculate_historical_indicators(symbols=[symbol])
            self._load_queues(symbols=[symbol])
            self._calculate_historical_quality(symbols=[symbol])
            
            # Update metadata
            metadata.meets_session_config_requirements = True
            metadata.upgraded_at = self._time_manager.get_current_time()
            self.session_data.set_symbol_metadata(symbol, metadata)
```

**Result**:
- Symbol has full historical data
- Historical indicators calculated
- Session indicators registered
- Quality scores computed
- Queues loaded with current day data
- `meets_session_config_requirements = True`

---

## Flow 2: Adhoc Bar/Indicator Addition

### Entry Points (Direct SessionData Manipulation)

#### Scanner Adds Bar
```python
# Scanner finds interesting bar
session_data.add_bar("TSLA", "1m", bar_data)
```

#### Scanner Adds Indicator
```python
# Scanner needs custom indicator
indicator_manager.register_indicator("TSLA", indicator_config)
```

### Auto-Provisioning Logic (in SessionData)

```python
class SessionData:
    def add_bar(self, symbol: str, interval: str, bar: BarData):
        """Add bar to symbol (auto-provision if needed)."""
        
        # Check if symbol exists
        if symbol not in self._symbols:
            logger.info(f"{symbol}: Auto-provisioning for adhoc bar addition")
            self._auto_provision_symbol(symbol, reason="bar_addition")
        
        # Add bar to structure
        symbol_data = self._symbols[symbol]
        # ... add bar logic ...
    
    def _auto_provision_symbol(self, symbol: str, reason: str):
        """Auto-provision minimal symbol structure for adhoc additions."""
        
        # Create minimal SymbolSessionData
        symbol_data = SymbolSessionData(
            symbol=symbol,
            # Minimal bar structure (just what's needed for immediate use)
            # NO historical data
            # NO indicators (unless explicitly requested)
        )
        self._symbols[symbol] = symbol_data
        
        # Create metadata marking as adhoc
        metadata = SymbolMetadata(
            symbol=symbol,
            meets_session_config_requirements=False,  # KEY!
            added_by="scanner",
            added_mid_session=True,
            auto_provisioned=True,
            provisioned_reason=reason,
            added_at=time_manager.get_current_time()
        )
        self._symbol_metadata[symbol] = metadata
        
        logger.info(
            f"{symbol}: Auto-provisioned (adhoc, reason={reason}, "
            f"meets_session_config_requirements=False)"
        )
```

**What Gets Created**:
- Minimal `SymbolSessionData` structure
- NO historical data loaded
- NO historical indicators
- NO session indicators (unless explicitly requested)
- NO quality calculation
- NO queue data
- `meets_session_config_requirements = False`

---

## Metadata: `meets_session_config_requirements`

### Definition

**`meets_session_config_requirements: bool`**

- `True`: Symbol has ALL session-config requirements loaded
  - Historical data ✅
  - Historical indicators ✅
  - Session indicators ✅
  - Quality scores ✅
  - Queue data ✅
  
- `False`: Symbol auto-provisioned with minimal structure
  - Only what was explicitly added ⚠️
  - Missing full session-config data ⚠️
  - Can be upgraded later ⚠️

### SymbolMetadata Structure

```python
@dataclass
class SymbolMetadata:
    """Metadata tracking symbol origin and loading status."""
    symbol: str
    
    # Core flag
    meets_session_config_requirements: bool = False
    
    # Origin tracking
    added_by: str  # "config", "coordinator", "scanner", "strategy"
    added_mid_session: bool = False
    added_at: Optional[datetime] = None
    
    # Auto-provision tracking
    auto_provisioned: bool = False
    provisioned_reason: Optional[str] = None  # "bar_addition", "indicator_request"
    
    # Upgrade tracking
    upgraded_at: Optional[datetime] = None
    upgraded_from_adhoc: bool = False
    
    # Persistence
    persist_to_next_session: bool = False
    export_to_json: bool = True
```

### JSON Serialization

```python
def to_json(self) -> dict:
    """Export SessionData to JSON (includes metadata)."""
    
    symbols_json = {}
    for symbol, symbol_data in self._symbols.items():
        metadata = self._symbol_metadata.get(symbol)
        
        symbols_json[symbol] = {
            # Symbol data
            "bars": symbol_data.to_json(),
            "indicators": # ... ,
            
            # METADATA (NEW!)
            "metadata": {
                "meets_session_config_requirements": metadata.meets_session_config_requirements,
                "added_by": metadata.added_by,
                "added_mid_session": metadata.added_mid_session,
                "auto_provisioned": metadata.auto_provisioned,
                "provisioned_reason": metadata.provisioned_reason,
                "upgraded_from_adhoc": metadata.upgraded_from_adhoc
            } if metadata else None
        }
    
    return {
        "symbols": symbols_json,
        # ... other fields
    }
```

**CSV Export** (for validation):
```
symbol,meets_session_config_requirements,added_by,auto_provisioned
AAPL,True,config,False
RIVN,True,config,False
TSLA,False,scanner,True
```

---

## Use Case Examples

### Use Case 1: Pre-Session Config Symbol
```python
# session_config.json: symbols=["AAPL", "RIVN"]
system.start()

→ Load AAPL:
  - Historical data ✅
  - Indicators ✅
  - Quality ✅
  - meets_session_config_requirements = True

→ Load RIVN:
  - Historical data ✅
  - Indicators ✅
  - Quality ✅
  - meets_session_config_requirements = True
```

### Use Case 2: Scanner Adds Adhoc Bar
```python
# 10:00 AM: Scanner discovers TSLA
scanner.on_scan():
    session_data.add_bar("TSLA", "1m", bar_data)

→ TSLA doesn't exist
→ Auto-provision:
  - Create minimal structure
  - Add bar
  - meets_session_config_requirements = False
  - NO historical
  - NO indicators
```

### Use Case 3: Strategy Upgrades Adhoc Symbol
```python
# 10:30 AM: Strategy wants TSLA
strategy.on_bar():
    coordinator.add_symbol("TSLA")

→ TSLA exists (auto-provisioned)
→ Check: meets_session_config_requirements? NO
→ UPGRADE:
  - Load historical data ✅
  - Calculate indicators ✅
  - Calculate quality ✅
  - Load queues ✅
  - Set meets_session_config_requirements = True
```

### Use Case 4: Add Bar to Fully-Loaded Symbol
```python
# AAPL already fully loaded (meets_session_config_requirements=True)
scanner.on_scan():
    session_data.add_bar("AAPL", "1m", bar_data)

→ AAPL exists
→ Check: meets_session_config_requirements? YES
→ Simple bar addition:
  - Add bar to structure
  - Nothing else happens
  - No loading, no indicators, no quality
```

### Use Case 5: Duplicate add_symbol()
```python
# AAPL fully loaded
strategy.on_bar():
    coordinator.add_symbol("AAPL")

→ AAPL exists
→ Check: meets_session_config_requirements? YES
→ Skip:
  - Already fully loaded
  - Return success
  - No work needed
```

---

## Persistence Rules

### End of Session: Which Symbols Persist?

```python
def _teardown_and_cleanup(self):
    """End of session cleanup."""
    
    # Collect symbols to persist
    persisted_symbols = []
    for symbol, metadata in self.session_data._symbol_metadata.items():
        if metadata.meets_session_config_requirements:
            persisted_symbols.append(symbol)
            logger.info(f"{symbol}: Persisting to next session (full session-config)")
        else:
            logger.info(f"{symbol}: NOT persisting (adhoc symbol)")
    
    # Update config for next session
    self.session_config.session_data_config.symbols = persisted_symbols
```

**Result**:
- `AAPL` (meets_session_config_requirements=True) → Persists ✅
- `RIVN` (meets_session_config_requirements=True) → Persists ✅  
- `TSLA` (meets_session_config_requirements=False) → Discarded ❌

### Next Session Behavior

```python
# Day 2 starts
→ Load persisted symbols only (AAPL, RIVN)
→ TSLA not loaded (was adhoc)

# If scanner finds TSLA again:
→ Auto-provision again (adhoc)
→ Or: Strategy calls add_symbol("TSLA") → Full load
```

---

## Implementation Checklist

### Phase 1: Metadata Infrastructure ✅ (Design Complete)
- [x] Design `SymbolMetadata` dataclass
- [x] Design auto-provision logic
- [x] Design upgrade logic

### Phase 2: SessionData Auto-Provisioning
- [ ] Add `_symbol_metadata` dict to SessionData
- [ ] Implement `_auto_provision_symbol()` in SessionData
- [ ] Update `add_bar()` to auto-provision if needed
- [ ] Update `register_indicator()` to auto-provision if needed

### Phase 3: Coordinator Upgrade Logic
- [ ] Update `add_symbol()` to detect adhoc symbols
- [ ] Update `_load_symbols_mid_session()` to handle upgrades
- [ ] Add upgrade detection and logging

### Phase 4: Serialization
- [ ] Add metadata to `to_json()` export
- [ ] Add metadata to CSV export
- [ ] Update validation to check metadata

### Phase 5: Persistence
- [ ] Filter symbols by `meets_session_config_requirements` in teardown
- [ ] Update config save logic
- [ ] Test multi-day with adhoc symbols

---

## Key Differences from Previous Design

| Aspect | Previous (Wrong) | Current (Correct) |
|--------|------------------|-------------------|
| **Ad-hoc entry point** | `coordinator.add_symbol()` with flag | Direct `session_data.add_bar()` |
| **Auto-provisioning** | Not discussed | Core feature |
| **Symbol upgrade** | Not discussed | Key use case |
| **add_symbol() purpose** | Mixed (config + adhoc) | ONLY full session-config |
| **Scanner behavior** | Calls coordinator | Direct SessionData manipulation |

---

## Summary

**Critical Insights**:
1. ✅ `add_symbol()` is ALWAYS full session-config loading (no "adhoc mode")
2. ✅ Scanners add bars/indicators DIRECTLY to SessionData
3. ✅ Auto-provisioning creates minimal structure when needed
4. ✅ `meets_session_config_requirements` tracks loading completeness
5. ✅ Symbols can be UPGRADED from adhoc to full
6. ✅ Only fully-loaded symbols persist to next session

**This is a much cleaner architecture!** The separation between explicit full loading (`add_symbol`) and implicit minimal provisioning (auto-provision) is very elegant.

**Ready to implement?**
