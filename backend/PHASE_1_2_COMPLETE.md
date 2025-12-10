# Phase 1.2 Complete: Session Config Models Updated

## ✅ Implemented

Added scanner framework configuration support to session config models.

---

## New Dataclasses

### 1. ScannerSchedule

```python
@dataclass
class ScannerSchedule:
    """Scanner schedule configuration for regular session scans.
    
    Attributes:
        start: Start time (HH:MM format, e.g., "09:35")
        end: End time (HH:MM format, e.g., "15:55")
        interval: Scan interval (e.g., "5m", "15m")
    """
    start: str
    end: str
    interval: str
```

**Validation**:
- ✅ Time format (HH:MM)
- ✅ Interval format (via requirement_analyzer)

---

### 2. ScannerConfig

```python
@dataclass
class ScannerConfig:
    """Scanner configuration.
    
    Attributes:
        module: Python module path (e.g., "scanners.gap_scanner")
        enabled: Whether scanner is enabled
        pre_session: Whether to run before session starts
        regular_session: List of schedules for regular session scans
        config: Scanner-specific configuration (e.g., {"universe": "..."})
    """
    module: str
    enabled: bool = True
    pre_session: bool = False
    regular_session: Optional[List[ScannerSchedule]] = None
    config: Dict[str, Any] = field(default_factory=dict)
```

**Validation**:
- ✅ Module path required and valid Python identifier
- ✅ At least one schedule type (pre_session or regular_session)
- ✅ All regular session schedules validated

---

### 3. Updated SessionDataConfig

```python
@dataclass
class SessionDataConfig:
    """Session data configuration.
    
    Attributes:
        ...existing...
        scanners: Scanner configurations - NEW!
    """
    symbols: List[str]
    streams: List[str]
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    historical: HistoricalConfig = field(default_factory=HistoricalConfig)
    gap_filler: GapFillerConfig = field(default_factory=GapFillerConfig)
    indicators: IndicatorsConfig = field(default_factory=IndicatorsConfig)
    scanners: List[ScannerConfig] = field(default_factory=list)  # NEW!
```

**Validation Added**:
- ✅ Each scanner validated
- ✅ No duplicate scanner modules

---

## Example Configuration

Created `/session_configs/scanner_example.json`:

```json
{
  "session_data_config": {
    "symbols": ["AAPL", "MSFT"],
    "streams": ["1m"],
    "scanners": [
      {
        "module": "scanners.gap_scanner",
        "enabled": true,
        "pre_session": true,
        "regular_session": null,
        "config": {
          "universe": "data/universes/sp500_sample.txt"
        }
      },
      {
        "module": "scanners.momentum_scanner",
        "enabled": true,
        "pre_session": false,
        "regular_session": [
          {
            "start": "09:35",
            "end": "15:55",
            "interval": "5m"
          }
        ],
        "config": {
          "universe": "data/universes/nasdaq100_sample.txt"
        }
      }
    ]
  }
}
```

---

## Scanner Configuration Patterns

### Pre-Session Only

```json
{
  "module": "scanners.gap_scanner",
  "enabled": true,
  "pre_session": true,
  "regular_session": null,
  "config": {
    "universe": "data/universes/sp500_sample.txt"
  }
}
```

**Lifecycle**:
1. setup() - Before session starts
2. scan() - Once before session starts
3. teardown() - After scan completes

---

### Regular Session Only

```json
{
  "module": "scanners.momentum_scanner",
  "enabled": true,
  "pre_session": false,
  "regular_session": [
    {
      "start": "09:35",
      "end": "15:55",
      "interval": "5m"
    }
  ],
  "config": {
    "universe": "data/universes/nasdaq100_sample.txt"
  }
}
```

**Lifecycle**:
1. setup() - Before session starts
2. Session starts at 09:30
3. scan() - Every 5 minutes from 09:35 to 15:55
4. teardown() - After last scan (15:55)

---

### Hybrid (Both)

```json
{
  "module": "scanners.hybrid_scanner",
  "enabled": true,
  "pre_session": true,
  "regular_session": [
    {
      "start": "10:00",
      "end": "15:00",
      "interval": "15m"
    }
  ],
  "config": {
    "universe": "data/universes/test_universe.txt"
  }
}
```

**Lifecycle**:
1. setup() - Before session starts
2. scan() - Once pre-session
3. Session starts at 09:30
4. scan() - Every 15 minutes from 10:00 to 15:00
5. teardown() - After last scan (15:00)

---

## Validation Examples

### ✅ Valid Configurations

```json
// Pre-session only
{
  "module": "scanners.gap_scanner",
  "pre_session": true
}

// Regular session only
{
  "module": "scanners.momentum_scanner",
  "regular_session": [
    {"start": "09:35", "end": "15:55", "interval": "5m"}
  ]
}

// Both
{
  "module": "scanners.hybrid_scanner",
  "pre_session": true,
  "regular_session": [
    {"start": "10:00", "end": "15:00", "interval": "15m"}
  ]
}
```

---

### ❌ Invalid Configurations

```json
// No schedule type
{
  "module": "scanners.bad_scanner",
  "pre_session": false,
  "regular_session": null
}
// Error: Scanner must have at least one schedule type

// Invalid module path
{
  "module": "scanners/gap_scanner",  // Wrong separator
  "pre_session": true
}
// Error: Invalid module path

// Invalid time format
{
  "module": "scanners.test",
  "regular_session": [
    {"start": "9:35", "end": "15:55", "interval": "5m"}  // Missing leading zero
  ]
}
// Error: Invalid start time format

// Duplicate modules
{
  "scanners": [
    {"module": "scanners.gap_scanner", "enabled": true, "pre_session": true},
    {"module": "scanners.gap_scanner", "enabled": true, "pre_session": true}
  ]
}
// Error: Duplicate scanner modules
```

---

## Files Modified

1. ✅ `/home/yohannes/mismartera/backend/app/models/session_config.py`
   - Added `ScannerSchedule` dataclass (30 lines)
   - Added `ScannerConfig` dataclass (40 lines)
   - Updated `SessionDataConfig` to include scanners field
   - Added scanner validation logic

2. ✅ `/home/yohannes/mismartera/backend/session_configs/scanner_example.json`
   - Complete example with two scanners
   - Shows pre-session and regular session patterns

---

## Key Features

### 1. Flexible Scheduling

```python
# Pre-session only
pre_session: true
regular_session: null

# Regular session only  
pre_session: false
regular_session: [...]

# Both
pre_session: true
regular_session: [...]
```

---

### 2. Multiple Regular Session Schedules

```json
{
  "regular_session": [
    {"start": "09:35", "end": "10:30", "interval": "5m"},
    {"start": "14:00", "end": "15:55", "interval": "10m"}
  ]
}
```

Scanner runs:
- Every 5 minutes from 09:35 to 10:30
- Every 10 minutes from 14:00 to 15:55

---

### 3. Scanner-Specific Config

```json
{
  "config": {
    "universe": "data/universes/sp500_sample.txt",
    "min_volume": 1000000,
    "custom_setting": "value"
  }
}
```

Scanner accesses via `self.config.get("universe")`.

---

## Integration with Phase 1.1

**SessionData adhoc APIs** are ready to be used by scanners:

```python
# In scanner setup()
context.session_data.add_indicator(symbol, "sma", {
    "period": 20,
    "interval": "1d"
})

# In scanner scan()
context.session_data.add_symbol("TSLA")

# In scanner teardown()
context.session_data.remove_symbol_adhoc(symbol)
```

---

## Next Steps: Phase 2.1

**Create Scanner Base Classes**

Files to create:
- `scanners/__init__.py`
- `scanners/base.py` - BaseScanner, ScanContext, ScanResult

**Estimated Time**: 2-3 hours

---

## Summary

✅ **Phase 1.2 Complete**: Session config models support scanners  
✅ **Validation**: Time format, interval format, module paths  
✅ **Flexible**: Pre-session, regular session, or both  
✅ **Example**: Complete working configuration  
✅ **Integration Ready**: Works with Phase 1.1 adhoc APIs  

**Total Phase 1 Progress**: 2/2 complete (100%) 🎯

Ready for Phase 2.1! 🚀
