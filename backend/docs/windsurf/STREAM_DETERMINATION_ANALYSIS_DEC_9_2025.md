# Stream Determination Analysis - December 9, 2025

## Overview

Analysis of how we determine what gets streamed vs generated based on session config and Parquet data availability.

---

## Architecture

### Three-Phase Validation

```
Phase 1: Configuration Validation
  ↓
Phase 2: Requirement Analysis
  ↓
Phase 3: Database Validation
  ↓
Decision: START or ABORT
```

### Key Components

1. **`StreamRequirementsCoordinator`** - Orchestrates validation
2. **`RequirementAnalyzer`** - Determines what's needed
3. **`DatabaseValidator`** - Checks if data exists
4. **`SessionCoordinator`** - Consumes decision and starts session

---

## Truth Table: Config + Data → Decision

### Input Variables

**A: Config Requests** (from `session_config.streams`)
- Examples: `["1m", "5m"]`, `["1s", "5s", "5m"]`, `["1d"]`

**B: Parquet Availability** (what exists in database)
- Check via `data_checker(symbol, interval, start_date, end_date) -> count`
- For each symbol, for date range, for required base interval

### Decision Matrix

| Config Streams | Required Base | Data Available? | Decision | Action |
|----------------|---------------|-----------------|----------|--------|
| `["1m"]` | `1m` | ✅ 1m exists | ✅ **START** | Stream 1m |
| `["1m"]` | `1m` | ❌ No 1m | ❌ **ABORT** | Error: Missing 1m data |
| `["5m"]` | `1m` | ✅ 1m exists | ✅ **START** | Stream 1m, Generate 5m |
| `["5m"]` | `1m` | ❌ No 1m | ❌ **ABORT** | Error: Missing 1m data |
| `["1m", "5m"]` | `1m` | ✅ 1m exists | ✅ **START** | Stream 1m, Generate 5m |
| `["1m", "5m"]` | `1m` | ❌ No 1m | ❌ **ABORT** | Error: Missing 1m data |
| `["1s", "5s"]` | `1s` | ✅ 1s exists | ✅ **START** | Stream 1s, Generate 5s |
| `["1s", "5s"]` | `1s` | ❌ No 1s | ❌ **ABORT** | Error: Missing 1s data |
| `["5s", "5m"]` | `1s` | ✅ 1s exists | ✅ **START** | Stream 1s, Generate 5s, 5m |
| `["5s", "5m"]` | `1s` | ❌ No 1s | ❌ **ABORT** | Error: Missing 1s data |
| `["1d"]` | `1d` | ✅ 1d exists | ✅ **START** | Stream 1d |
| `["1d"]` | `1d` | ❌ No 1d | ❌ **ABORT** | Error: Missing 1d data |
| `["5d"]` | `1d` | ✅ 1d exists | ✅ **START** | Stream 1d, Generate 5d |
| `["1m", "1d"]` | `1m` | ✅ 1m exists | ✅ **START** | Stream 1m, Direct load 1d |
| `["1m", "1d"]` | `1m` | ❌ No 1m | ❌ **ABORT** | Error: Missing 1m data |

### Multi-Symbol Cases

| Symbols | Config | AAPL Data | GOOGL Data | Decision | Reason |
|---------|--------|-----------|------------|----------|--------|
| `["AAPL", "GOOGL"]` | `["1m"]` | ✅ 1m | ✅ 1m | ✅ **START** | Both have 1m |
| `["AAPL", "GOOGL"]` | `["1m"]` | ✅ 1m | ❌ No 1m | ❌ **ABORT** | GOOGL missing 1m |
| `["AAPL", "GOOGL"]` | `["1m"]` | ❌ No 1m | ❌ No 1m | ❌ **ABORT** | Both missing 1m |
| `["AAPL", "GOOGL"]` | `["5m"]` | ✅ 1m | ✅ 1m | ✅ **START** | Both have 1m (base for 5m) |
| `["AAPL", "GOOGL"]` | `["5m"]` | ✅ 1m | ❌ No 1m | ❌ **ABORT** | GOOGL missing 1m |

---

## Derivation Rules

### Base Interval Selection

**Rule**: Stream the **smallest base interval** that satisfies all requirements

```
Priority (smallest → largest):
  1s < 1m < 1d < 1w
```

### Derivation Logic

**From Config** → **Required Base**

```python
# Rule 1: Second intervals require 1s
"5s" → requires "1s"
"10s" → requires "1s"
"30s" → requires "1s"

# Rule 2: Minute intervals require 1m
"5m" → requires "1m"
"15m" → requires "1m"
"30m" → requires "1m"
"60m" → requires "1m"

# Rule 3: Day intervals require 1d
"5d" → requires "1d"
"10d" → requires "1d"

# Rule 4: Week intervals require 1w
"2w" → requires "1w"
"4w" → requires "1w"

# Base intervals require themselves
"1s" → requires "1s"
"1m" → requires "1m"
"1d" → requires "1d"
"1w" → requires "1w"
```

### Multi-Interval Selection

```python
# Example 1: Multiple within same unit
Config: ["1m", "5m", "15m"]
→ Required: "1m" (smallest)
→ Stream: 1m
→ Generate: 5m, 15m

# Example 2: Across units
Config: ["5s", "5m"]
→ Required: "1s" (smallest that satisfies both)
→ Stream: 1s
→ Generate: 5s, 5m

# Example 3: Base + derived
Config: ["1m", "5m"]
→ Required: "1m"
→ Stream: 1m
→ Generate: 5m (1m is direct stream, not generated)
```

---

## Validation Flow

### Phase 1: Configuration Validation

**Input**: `session_config.streams`

**Checks**:
1. ❌ Streams list not empty
2. ❌ No "ticks" (unsupported)
3. ❌ Valid interval format (Ns, Nm, Nd, Nw, "quotes")
4. ❌ No hourly format ("1h" → use "60m")

**Output**: Config valid or error message

### Phase 2: Requirement Analysis

**Input**: Validated streams list

**Process**:
```python
analyze_session_requirements(streams) → SessionRequirements
```

**Algorithm**:
1. Parse each interval
2. Determine required base for each
3. Select smallest base (priority: 1s < 1m < 1d < 1w)
4. Calculate derivable intervals (all - base)

**Output**: 
```python
SessionRequirements(
    explicit_intervals=["5m", "15m"],
    implicit_intervals=[],  # Auto-detected needs
    required_base_interval="1m",
    derivable_intervals=["5m", "15m"]
)
```

### Phase 3: Database Validation

**Input**: 
- `SessionRequirements.required_base_interval`
- `symbols` from config
- `date_range` from TimeManager
- `data_checker` callable

**Process**:
```python
for symbol in symbols:
    count = data_checker(
        symbol,
        required_base_interval,
        start_date,
        end_date
    )
    
    if count == 0:
        return False, f"Missing {required_base_interval} for {symbol}"
        
return True, None
```

**Output**:
```python
ValidationResult(
    valid=True/False,
    required_base_interval="1m",
    derivable_intervals=["5m", "15m"],
    symbols=["AAPL", "GOOGL"],
    error_message=None or "Missing 1m data for GOOGL (2025-07-01 to 2025-07-03)",
    requirements=<full requirements object>
)
```

---

## Fault Handling

### Level 1: Configuration Errors (Pre-Session)

**When**: Before any data loading

**Errors**:
- Empty streams list
- Invalid interval format
- Unsupported intervals (ticks, hourly)

**Action**: 
```python
raise ValueError("Configuration error: {details}")
```

**Example**:
```
ValueError: Invalid stream '1h'. Expected format: <number><unit> (e.g., '1s', '5m', '1d', '1w')
NOTE: Hourly intervals not supported - use minutes (60m, 120m, etc.)
```

**Recovery**: Fix config file, restart

---

### Level 2: Requirement Analysis Errors

**When**: During requirement analysis

**Errors**:
- No bar intervals requested (only quotes)
- Cannot determine base interval

**Action**:
```python
return ValidationResult(
    valid=False,
    error_message="Requirement analysis error: {details}"
)
```

**Example**:
```
Requirement analysis error: No bar intervals requested
```

**Recovery**: Add bar intervals to config

---

### Level 3: Database Validation Errors (Critical)

**When**: Checking if required data exists

**Errors**:
- Missing base interval data for symbol(s)
- No data in date range
- Partial data availability

**Action**:
```python
logger.error("=" * 70)
logger.error("STREAM REQUIREMENTS VALIDATION FAILED")
logger.error("=" * 70)
logger.error(result.error_message)
logger.error("=" * 70)
logger.error("Cannot start session: validation failed")
logger.error("Suggestions:")
logger.error("  1. Check data availability: Is required data downloaded?")
logger.error("  2. Check date range: Does backtest window have data?")
logger.error("  3. Check config: Are stream intervals correct?")
logger.error("=" * 70)
return False  # Abort session initialization
```

**Example Error**:
```
Cannot start session: 2 symbol(s) missing 1m data:
  - AAPL: Required interval 1m not available for AAPL (2025-07-02 to 2025-07-02)
  - GOOGL: Required interval 1m not available for GOOGL (2025-07-02 to 2025-07-02)

Checking available intervals for each symbol...
  AAPL: No base intervals available
  GOOGL: ['1d'] available
```

**Recovery Options**:
1. Download missing data
2. Adjust date range to where data exists
3. Change config to use available intervals (e.g., use 1d instead of 1m)
4. Remove symbols without data

---

## Example Scenarios

### Scenario 1: Perfect Match ✅

**Config**:
```json
{
  "symbols": ["AAPL"],
  "streams": ["1m", "5m"]
}
```

**Parquet**: AAPL has 1m data for date range

**Analysis**:
- Required base: `1m`
- Derivable: `["5m"]`

**Validation**: ✅ PASS

**Action**:
- Stream `1m` from Parquet/queue
- Generate `5m` from 1m bars

---

### Scenario 2: Missing Base Data ❌

**Config**:
```json
{
  "symbols": ["AAPL", "GOOGL"],
  "streams": ["5m"]
}
```

**Parquet**: 
- AAPL has 1m data ✅
- GOOGL has only 1d data ❌

**Analysis**:
- Required base: `1m` (to generate 5m)
- Derivable: `["5m"]`

**Validation**: ❌ FAIL
```
Missing 1m data for GOOGL (2025-07-01 to 2025-07-03)
```

**Action**: **ABORT** - Cannot start session

**Fix Options**:
1. Download 1m data for GOOGL
2. Remove GOOGL from symbols
3. Change config to `["1d"]` if acceptable

---

### Scenario 3: Multi-Timeframe ✅

**Config**:
```json
{
  "symbols": ["AAPL"],
  "streams": ["1s", "5s", "5m", "15m"]
}
```

**Parquet**: AAPL has 1s data for date range

**Analysis**:
- Required base: `1s` (smallest, satisfies all)
- Derivable: `["5s", "5m", "15m"]`

**Validation**: ✅ PASS

**Action**:
- Stream `1s` from Parquet
- Generate `5s` from 1s
- Generate `5m` from 1s (via 1m intermediate)
- Generate `15m` from 1s (via 1m intermediate)

---

### Scenario 4: Daily Only ✅

**Config**:
```json
{
  "symbols": ["AAPL"],
  "streams": ["1d"]
}
```

**Parquet**: AAPL has 1d data

**Analysis**:
- Required base: `1d`
- Derivable: `[]` (no generation needed)

**Validation**: ✅ PASS

**Action**:
- Stream `1d` from Parquet
- No derived intervals

---

## Conflict Resolution

### Config Conflict: No Data Available

**Problem**: Config requests intervals but no data exists

**Resolution**: **FAIL FAST**
- Validate before session starts
- Clear error message with diagnostics
- Suggest available intervals
- Do NOT attempt to start session

**Rationale**: Better to fail early with clear error than fail mid-session

---

### Config Conflict: Wrong Base Available

**Problem**: Config wants 5m, but only 1s available (not 1m)

**Current Behavior**: 
- Required base: 1m
- Check: 1m exists? → No
- Result: **ABORT**

**Could Use 1s**: YES, technically could generate 5m from 1s

**Why We Don't**: 
- Clarity: Config determines intent
- Performance: 1s → 5m is expensive (aggregate 300 bars)
- Explicitness: If user wants 1s-based generation, add "1s" to config

**Better Config**:
```json
{
  "streams": ["1s", "5m"]  // Explicit: use 1s to generate 5m
}
```

---

### Multi-Symbol Conflict: Partial Availability

**Problem**: AAPL has data, GOOGL doesn't

**Resolution**: **ALL OR NOTHING**
- If ANY symbol missing required data → ABORT
- Do NOT start with partial symbol list

**Rationale**:
- Strategy expects all symbols
- Partial data could cause strategy errors
- Clear is better than implicit filtering

**Recovery**: Remove symbols without data OR download missing data

---

## Data Checker Implementation

### Interface

```python
Callable[[str, str, date, date], int]
# (symbol, interval, start_date, end_date) → bar_count
```

### Current Implementation

**Via DataManager** (production):
```python
def data_checker(symbol, interval, start_date, end_date):
    bars = data_manager.get_bars(
        session=None,
        symbol=symbol,
        start=datetime.combine(start_date, time.min),
        end=datetime.combine(end_date, time.max),
        interval=interval,
        regular_hours_only=False
    )
    return len(bars) if bars else 0
```

**Abstraction**: DataManager handles Parquet internally

---

## Summary

### Current System Design

✅ **Explicit Configuration**
- User specifies what intervals they want
- System validates and determines streaming strategy
- Fail fast with clear errors

✅ **Deterministic**
- Same config + same data = same decision
- No hidden "smart" choices
- Transparent derivation logic

✅ **Safe**
- Validate before starting
- All-or-nothing for symbols
- Clear error messages with diagnostics

✅ **Efficient**
- Stream smallest base needed
- Generate derived intervals from base
- Minimize data transfer

### Key Principles

1. **Config is King**: User's config is the requirement specification
2. **Fail Fast**: Validate everything before starting session
3. **All or Nothing**: Don't start with partial data
4. **Smallest Base**: Stream minimum needed to satisfy requirements
5. **Clear Errors**: Tell user exactly what's missing and how to fix

### Truth Table Summary

```
IF config_valid AND base_data_exists_for_all_symbols:
    START session with base_interval
ELSE:
    ABORT with specific error message
```

**No gray areas. No fallbacks. No surprises.**

---

## Status

**Current Implementation**: ✅ WORKING

**Test Coverage**: ✅ COMPREHENSIVE
- Configuration validation
- Requirement analysis  
- Database validation
- Multi-symbol cases
- Error cases

**Documentation**: ✅ COMPLETE (this doc)
