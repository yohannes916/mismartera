# Comprehensive Test Plan: Session Lifecycle & Unified Provisioning

**Target**: Complete session lifecycle flow (Phase 0 → Phase 4 + multi-day loop)  
**Coverage Goal**: 100+ tests covering all phases, edge cases, and assumptions  
**Test Types**: Unit, Integration, E2E  
**Estimated Tests**: 150-200 tests

---

## Test Infrastructure

### Existing Fixtures (Reuse)
- ✅ `test_db` - Test database with holidays, trading hours
- ✅ `mock_time_manager` - Controllable time
- ✅ `synthetic_bars` - Generated bar data
- ✅ `test_parquet_data` - Parquet test data
- ✅ `test_symbols` - Predefined test symbols with characteristics

### New Fixtures Needed
- `session_coordinator_with_data` - Coordinator with Parquet data loaded
- `mock_system_manager` - SystemManager with all managers
- `sample_session_configs` - Various config scenarios
- `mock_indicator_config` - IndicatorConfig for testing
- `session_state_snapshot` - Capture/compare session state
- `multi_day_backtest_setup` - 3-5 day backtest setup

---

## Test Organization Structure

```
tests/
├── unit/
│   ├── test_provisioning_requirements.py      # ProvisioningRequirements dataclass
│   ├── test_requirement_analysis.py           # _analyze_requirements() tests
│   ├── test_provisioning_executor.py          # _execute_provisioning() tests
│   ├── test_unified_entry_points.py           # add_*_unified() tests
│   ├── test_metadata_tracking.py              # Metadata correctness
│   ├── test_validation_step0.py               # Step 0 validation
│   └── test_provisioning_steps.py             # Individual provisioning methods
│
├── integration/
│   ├── test_phase0_stream_validation.py       # Phase 0 system-wide validation
│   ├── test_phase1_teardown_cleanup.py        # Phase 1 state clearing
│   ├── test_phase2_initialization.py          # Phase 2 three-phase loading
│   ├── test_phase3a_adhoc_additions.py        # Lightweight additions
│   ├── test_phase3b_midsession_symbols.py     # Full mid-session loading
│   ├── test_phase3c_symbol_deletion.py        # Symbol removal
│   ├── test_phase4_session_end.py             # Session deactivation
│   ├── test_upgrade_path.py                   # Adhoc → Full upgrade
│   ├── test_graceful_degradation.py           # Failed symbol handling
│   └── test_thread_safety.py                  # Concurrent operations
│
├── e2e/
│   ├── test_single_day_session.py             # Full single-day session
│   ├── test_multi_day_backtest.py             # 3-5 day loop
│   ├── test_no_persistence.py                 # Verify no cross-session state
│   ├── test_complete_workflow_scanner.py      # Scanner adds indicator → strategy upgrades
│   ├── test_complete_workflow_strategy.py     # Strategy full loading
│   └── test_stress_scenarios.py               # Multiple concurrent additions
│
└── performance/
    ├── test_provisioning_speed.py             # Provisioning performance
    └── test_multi_symbol_loading.py           # 10+ symbols loading

```

---

## 1. Unit Tests (60-80 tests)

### 1.1 ProvisioningRequirements Dataclass (5 tests)
**File**: `tests/unit/test_provisioning_requirements.py`

```python
def test_provisioning_requirements_creation():
    """Test ProvisioningRequirements can be created with all fields."""

def test_provisioning_requirements_defaults():
    """Test default values are correct."""

def test_provisioning_requirements_validation_errors_list():
    """Test validation_errors can accumulate multiple errors."""

def test_provisioning_requirements_provisioning_steps_list():
    """Test provisioning_steps can contain multiple steps."""

def test_provisioning_requirements_immutable_after_creation():
    """Test that requirements object captures state at creation time."""
```

---

### 1.2 Requirement Analysis (_analyze_requirements) (20 tests)
**File**: `tests/unit/test_requirement_analysis.py`

#### Symbol Requirements (8 tests)
```python
def test_analyze_symbol_requirements_new_symbol():
    """Analyze requirements for new symbol from config."""
    # Expected: All intervals, full historical, all indicators
    
def test_analyze_symbol_requirements_existing_adhoc():
    """Analyze requirements for existing adhoc symbol (upgrade path)."""
    # Expected: Upgrade steps, load missing pieces

def test_analyze_symbol_requirements_existing_full():
    """Analyze requirements for symbol already fully loaded."""
    # Expected: can_proceed=False (duplicate)

def test_analyze_symbol_requirements_no_intervals():
    """Analyze symbol when config has no derived intervals."""
    # Expected: Only base interval

def test_analyze_symbol_requirements_multiple_derived():
    """Analyze symbol with multiple derived intervals (5m, 15m, 1h)."""
    # Expected: All derived intervals in requirements

def test_analyze_symbol_requirements_with_indicators():
    """Analyze symbol that needs indicators from config."""
    # Expected: Indicator requirements included

def test_analyze_symbol_requirements_historical_days():
    """Analyze symbol with various trailing_days values (0, 30, 90)."""
    # Expected: Correct historical days

def test_analyze_symbol_requirements_from_strategy():
    """Analyze symbol added by strategy (source='strategy')."""
    # Expected: Full requirements, correct metadata
```

#### Bar Requirements (6 tests)
```python
def test_analyze_bar_requirements_new_symbol_base_interval():
    """Analyze bar for new symbol, base interval (1m)."""
    # Expected: Auto-provision, add base interval only

def test_analyze_bar_requirements_new_symbol_derived():
    """Analyze bar for new symbol, derived interval (5m)."""
    # Expected: Auto-provision, add base + derived

def test_analyze_bar_requirements_existing_symbol():
    """Analyze bar for existing symbol, new interval."""
    # Expected: Add interval only, no symbol creation

def test_analyze_bar_requirements_existing_interval():
    """Analyze bar for interval that already exists."""
    # Expected: can_proceed=False (duplicate)

def test_analyze_bar_requirements_historical_days():
    """Analyze bar with various historical days (0, 5, 30)."""
    # Expected: Correct historical requirements

def test_analyze_bar_requirements_historical_only():
    """Analyze bar with historical_only=True."""
    # Expected: No session loading step
```

#### Indicator Requirements (6 tests)
```python
def test_analyze_indicator_requirements_new_symbol():
    """Analyze indicator for new symbol."""
    # Expected: Auto-provision, add required intervals, warmup bars

def test_analyze_indicator_requirements_existing_symbol():
    """Analyze indicator for existing symbol with interval."""
    # Expected: Register indicator only

def test_analyze_indicator_requirements_missing_interval():
    """Analyze indicator for existing symbol without required interval."""
    # Expected: Add interval + register indicator

def test_analyze_indicator_requirements_warmup_calculation():
    """Verify warmup days calculated correctly (period * 2)."""
    # Expected: SMA(20) → ~40 bars warmup

def test_analyze_indicator_requirements_duplicate():
    """Analyze indicator that already exists."""
    # Expected: can_proceed=False (duplicate)

def test_analyze_indicator_requirements_derived_interval():
    """Analyze indicator on derived interval (5m SMA)."""
    # Expected: Base (1m) + derived (5m) + register
```

---

### 1.3 Provisioning Executor (_execute_provisioning) (15 tests)
**File**: `tests/unit/test_provisioning_executor.py`

#### Orchestration (5 tests)
```python
def test_execute_provisioning_cannot_proceed():
    """Test provisioning blocked when can_proceed=False."""
    # Expected: Returns False immediately

def test_execute_provisioning_empty_steps():
    """Test provisioning with empty provisioning_steps."""
    # Expected: Returns True (nothing to do)

def test_execute_provisioning_executes_all_steps():
    """Test all steps executed in order."""
    # Expected: All steps called

def test_execute_provisioning_stops_on_error():
    """Test provisioning stops if a step fails."""
    # Expected: Returns False, remaining steps not executed

def test_execute_provisioning_logs_progress():
    """Test provisioning logs each step."""
    # Expected: Log entries for each step
```

#### Individual Provisioning Steps (10 tests)
```python
def test_provision_create_symbol():
    """Test _provision_create_symbol() creates symbol with metadata."""
    # Expected: SymbolSessionData created, metadata correct

def test_provision_upgrade_symbol():
    """Test _provision_upgrade_symbol() updates metadata."""
    # Expected: meets_session_config_requirements=True, upgraded_from_adhoc=True

def test_provision_add_interval_base():
    """Test _provision_add_interval() adds base interval."""
    # Expected: BarIntervalData with derived=False

def test_provision_add_interval_derived():
    """Test _provision_add_interval() adds derived interval."""
    # Expected: BarIntervalData with derived=True, base set

def test_provision_load_historical_calls_existing_method():
    """Test _provision_load_historical() calls _manage_historical_data()."""
    # Expected: Existing method called with correct params

def test_provision_load_session_calls_existing_method():
    """Test _provision_load_session() calls _load_queues()."""
    # Expected: Existing method called

def test_provision_register_indicator():
    """Test _provision_register_indicator() adds indicator."""
    # Expected: Indicator in symbol_data.indicators, registered with manager

def test_provision_calculate_quality_calls_existing_method():
    """Test _provision_calculate_quality() calls existing method."""
    # Expected: Quality calculation method called

def test_provision_step_error_handling():
    """Test individual step error handling."""
    # Expected: Exception caught, logged, returns False

def test_provision_step_unknown_step():
    """Test unknown provisioning step."""
    # Expected: Error logged, skipped
```

---

### 1.4 Unified Entry Points (12 tests)
**File**: `tests/unit/test_unified_entry_points.py`

#### add_indicator_unified (4 tests)
```python
def test_add_indicator_unified_success():
    """Test successful indicator addition."""
    # Expected: Returns True, indicator added

def test_add_indicator_unified_validation_fails():
    """Test indicator addition when validation fails."""
    # Expected: Returns False, error logged

def test_add_indicator_unified_no_coordinator():
    """Test when session_coordinator not set."""
    # Expected: Returns False, error logged

def test_add_indicator_unified_exception_handling():
    """Test exception during indicator addition."""
    # Expected: Exception caught, returns False
```

#### add_bar_unified (4 tests)
```python
def test_add_bar_unified_success():
    """Test successful bar addition."""
    # Expected: Returns True, bar interval added

def test_add_bar_unified_validation_fails():
    """Test bar addition when validation fails."""
    # Expected: Returns False, error logged

def test_add_bar_unified_no_coordinator():
    """Test when session_coordinator not set."""
    # Expected: Returns False, error logged

def test_add_bar_unified_exception_handling():
    """Test exception during bar addition."""
    # Expected: Exception caught, returns False
```

#### add_symbol (updated) (4 tests)
```python
def test_add_symbol_unified_success():
    """Test successful symbol addition via unified pattern."""
    # Expected: Returns True, symbol loaded, added to config

def test_add_symbol_unified_validation_fails():
    """Test symbol addition when validation fails."""
    # Expected: Returns False, not added to config

def test_add_symbol_unified_already_exists():
    """Test adding symbol that's already fully loaded."""
    # Expected: Returns False (duplicate detected in validation)

def test_add_symbol_unified_exception_handling():
    """Test exception during symbol addition."""
    # Expected: Exception caught, returns False
```

---

### 1.5 Metadata Tracking (8 tests)
**File**: `tests/unit/test_metadata_tracking.py`

```python
def test_metadata_config_symbol():
    """Test metadata for symbol loaded from config."""
    # Expected: meets_session_config_requirements=True, added_by="config"

def test_metadata_strategy_symbol():
    """Test metadata for symbol added by strategy."""
    # Expected: meets_session_config_requirements=True, added_by="strategy"

def test_metadata_scanner_symbol():
    """Test metadata for symbol auto-provisioned by scanner."""
    # Expected: meets_session_config_requirements=False, auto_provisioned=True

def test_metadata_upgraded_symbol():
    """Test metadata after upgrade from adhoc to full."""
    # Expected: meets_session_config_requirements=True, upgraded_from_adhoc=True

def test_metadata_added_at_timestamp():
    """Test added_at uses TimeManager."""
    # Expected: added_at = current backtest time

def test_metadata_json_export():
    """Test metadata exported to JSON."""
    # Expected: All metadata fields in JSON

def test_metadata_csv_export():
    """Test metadata exported to CSV."""
    # Expected: Metadata columns present

def test_metadata_deleted_with_symbol():
    """Test metadata deleted when symbol removed."""
    # Expected: No orphaned metadata
```

---

### 1.6 Validation (Step 0) (12 tests)
**File**: `tests/unit/test_validation_step0.py`

```python
def test_validate_symbol_data_source_available():
    """Test validation passes when data source available."""
    # Expected: can_proceed=True

def test_validate_symbol_no_data_source():
    """Test validation fails when no data source."""
    # Expected: can_proceed=False, reason set

def test_validate_symbol_parquet_data_available():
    """Test validation checks Parquet data availability."""
    # Expected: can_proceed=True if data exists

def test_validate_symbol_parquet_data_missing():
    """Test validation fails when Parquet data missing."""
    # Expected: can_proceed=False, reason set

def test_validate_symbol_intervals_supported():
    """Test validation checks interval support."""
    # Expected: can_proceed=True if intervals valid

def test_validate_symbol_unsupported_interval():
    """Test validation fails for unsupported interval (2m from 1m)."""
    # Expected: can_proceed=False, derivation not possible

def test_validate_symbol_historical_data_available():
    """Test validation checks historical data availability."""
    # Expected: can_proceed=True if enough historical bars

def test_validate_symbol_insufficient_historical():
    """Test validation fails when insufficient historical data."""
    # Expected: can_proceed=False or warning

def test_validate_symbol_duplicate_full():
    """Test validation fails for duplicate full symbol."""
    # Expected: can_proceed=False, already loaded

def test_validate_symbol_duplicate_adhoc_allows_upgrade():
    """Test validation allows adhoc symbol to be upgraded."""
    # Expected: can_proceed=True, upgrade path detected

def test_validate_symbol_multiple_checks():
    """Test validation accumulates multiple errors."""
    # Expected: validation_errors list has all errors

def test_validate_symbol_uses_timemanager():
    """Test validation uses TimeManager for date checks."""
    # Expected: No hardcoded dates
```

---

## 2. Integration Tests (40-50 tests)

### 2.1 Phase 0: System-Wide Validation (8 tests)
**File**: `tests/integration/test_phase0_stream_validation.py`

```python
def test_phase0_valid_config():
    """Test Phase 0 with valid session config."""
    # Expected: All validations pass

def test_phase0_determine_base_interval():
    """Test base interval determination (1m, 1s, 1d)."""
    # Expected: Correct base interval identified

def test_phase0_determine_derived_intervals():
    """Test derived intervals determination."""
    # Expected: All derived intervals (5m, 15m, 1h) identified

def test_phase0_validate_derivation_capability():
    """Test derivation validation (can derive 5m from 1m?)."""
    # Expected: Valid derivations pass, invalid fail

def test_phase0_invalid_config_format():
    """Test Phase 0 with malformed config."""
    # Expected: Validation fails, clear error

def test_phase0_results_stored_for_reuse():
    """Test Phase 0 results stored and reused."""
    # Expected: No re-validation for each symbol

def test_phase0_no_symbol_validation():
    """Test Phase 0 does not validate individual symbols."""
    # Expected: Only system-wide checks

def test_phase0_no_symbol_registration():
    """Test Phase 0 does not register symbols."""
    # Expected: No SymbolSessionData created
```

---

### 2.2 Phase 1: Teardown & Cleanup (10 tests)
**File**: `tests/integration/test_phase1_teardown_cleanup.py`

```python
def test_phase1_clear_all_symbols():
    """Test all symbols cleared (config + adhoc)."""
    # Expected: session_data.symbols empty

def test_phase1_clear_metadata():
    """Test metadata cleared with symbols."""
    # Expected: No orphaned metadata

def test_phase1_clear_bar_queues():
    """Test all bar queues cleared."""
    # Expected: bar_queues empty

def test_phase1_clear_quote_tick_queues():
    """Test quote and tick queues cleared."""
    # Expected: All queues empty

def test_phase1_teardown_all_threads():
    """Test all threads torn down."""
    # Expected: All thread teardown() called

def test_phase1_advance_clock_to_next_day():
    """Test clock advanced to next trading day."""
    # Expected: TimeManager set to next day market open

def test_phase1_skip_holidays():
    """Test clock skips holidays/weekends."""
    # Expected: Next trading day used

def test_phase1_no_persistence_from_previous_day():
    """Test no state persists from previous day."""
    # Expected: Fresh start

def test_phase1_locked_symbols_cleared():
    """Test symbol locks cleared."""
    # Expected: No locked symbols

def test_phase1_multiple_teardowns():
    """Test repeated teardowns (multi-day)."""
    # Expected: Each teardown complete
```

---

### 2.3 Phase 2: Initialization (12 tests)
**File**: `tests/integration/test_phase2_initialization.py`

```python
def test_phase2_load_single_symbol_full():
    """Test loading single symbol with full three-phase pattern."""
    # Expected: Symbol loaded, all intervals, historical, quality

def test_phase2_load_multiple_symbols():
    """Test loading multiple symbols from config."""
    # Expected: All symbols loaded

def test_phase2_requirement_analysis_all_symbols():
    """Test requirement analysis runs for each symbol."""
    # Expected: ProvisioningRequirements for each

def test_phase2_validation_all_symbols():
    """Test validation runs for each symbol."""
    # Expected: Validated symbols proceed

def test_phase2_provisioning_all_symbols():
    """Test provisioning executes for each validated symbol."""
    # Expected: All symbols loaded

def test_phase2_historical_loading():
    """Test historical data loaded for all symbols."""
    # Expected: Historical bars present

def test_phase2_session_queue_loading():
    """Test session queues loaded for all symbols."""
    # Expected: Queues populated for current day

def test_phase2_quality_calculation():
    """Test quality scores calculated."""
    # Expected: Quality > 0 for all symbols

def test_phase2_indicator_registration():
    """Test indicators registered from config."""
    # Expected: All indicators present

def test_phase2_metadata_correctness():
    """Test metadata set correctly for config symbols."""
    # Expected: meets_session_config_requirements=True, added_by="config"

def test_phase2_thread_initialization():
    """Test all threads initialized after loading."""
    # Expected: All thread setup() called

def test_phase2_pre_session_scan():
    """Test pre-session scan runs if configured."""
    # Expected: Scanner ran before session start
```

---

### 2.4 Phase 3a: Adhoc Additions (10 tests)
**File**: `tests/integration/test_phase3a_adhoc_additions.py`

```python
def test_adhoc_add_indicator_new_symbol():
    """Test scanner adds indicator for new symbol."""
    # Expected: Symbol auto-provisioned, indicator registered

def test_adhoc_add_indicator_existing_symbol():
    """Test scanner adds indicator to existing symbol."""
    # Expected: Indicator registered, no symbol recreation

def test_adhoc_add_bar_new_symbol():
    """Test scanner adds bar for new symbol."""
    # Expected: Symbol auto-provisioned, interval added

def test_adhoc_add_bar_existing_symbol():
    """Test scanner adds bar to existing symbol."""
    # Expected: Interval added, symbol not recreated

def test_adhoc_minimal_historical_loading():
    """Test adhoc loading loads only warmup bars."""
    # Expected: Warmup bars loaded, not full 30 days

def test_adhoc_no_quality_calculation():
    """Test adhoc loading skips quality calculation."""
    # Expected: quality = 0.0 or not calculated

def test_adhoc_metadata_correctness():
    """Test adhoc symbol has correct metadata."""
    # Expected: meets_session_config_requirements=False, auto_provisioned=True

def test_adhoc_derived_interval_base_added():
    """Test adhoc addition of derived interval adds base."""
    # Expected: Base (1m) + derived (5m) both added

def test_adhoc_duplicate_detection():
    """Test duplicate adhoc addition detected."""
    # Expected: Second addition returns False

def test_adhoc_multiple_concurrent():
    """Test multiple adhoc additions concurrently."""
    # Expected: All additions succeed, thread-safe
```

---

### 2.5 Phase 3b: Mid-Session Symbols (8 tests)
**File**: `tests/integration/test_phase3b_midsession_symbols.py`

```python
def test_midsession_add_new_symbol():
    """Test strategy adds new symbol mid-session."""
    # Expected: Full loading (same as config)

def test_midsession_upgrade_adhoc_symbol():
    """Test strategy upgrades adhoc symbol to full."""
    # Expected: Metadata updated, full historical loaded, quality calculated

def test_midsession_duplicate_full_symbol():
    """Test duplicate mid-session addition detected."""
    # Expected: Returns False, no duplicate loading

def test_midsession_full_historical_loading():
    """Test mid-session symbol loads full historical."""
    # Expected: 30 days (or config trailing_days) loaded

def test_midsession_all_intervals_added():
    """Test mid-session symbol gets all config intervals."""
    # Expected: All base + derived intervals

def test_midsession_quality_calculation():
    """Test quality calculated for mid-session symbol."""
    # Expected: Quality > 0

def test_midsession_metadata_correctness():
    """Test mid-session symbol metadata."""
    # Expected: meets_session_config_requirements=True, added_by="strategy"

def test_midsession_upgrade_metadata():
    """Test upgrade path metadata correct."""
    # Expected: upgraded_from_adhoc=True
```

---

### 2.6 Phase 3c: Symbol Deletion (4 tests)
**File**: `tests/integration/test_phase3c_symbol_deletion.py`

```python
def test_delete_symbol_removes_data():
    """Test symbol deletion removes SymbolSessionData."""
    # Expected: Symbol not in session_data

def test_delete_symbol_removes_metadata():
    """Test symbol deletion removes metadata."""
    # Expected: No orphaned metadata

def test_delete_symbol_clears_queues():
    """Test symbol deletion clears queues."""
    # Expected: No bars in queues for deleted symbol

def test_delete_symbol_no_persistence():
    """Test deleted symbol not in next session."""
    # Expected: Symbol not loaded in next session
```

---

### 2.7 Phase 4: Session End (5 tests)
**File**: `tests/integration/test_phase4_session_end.py`

```python
def test_session_end_deactivate():
    """Test session deactivated at end."""
    # Expected: session_active=False

def test_session_end_metrics_recorded():
    """Test session metrics recorded."""
    # Expected: Metrics present

def test_session_end_data_intact():
    """Test data left intact for analysis."""
    # Expected: All symbols still present

def test_session_end_no_persistence_to_next():
    """Test data not persisted to next session."""
    # Expected: Next session starts fresh

def test_last_day_data_kept():
    """Test last day data kept for final analysis."""
    # Expected: Last day data present after loop end
```

---

### 2.8 Upgrade Path (5 tests)
**File**: `tests/integration/test_upgrade_path.py`

```python
def test_upgrade_adhoc_to_full():
    """Test complete upgrade path: adhoc → full."""
    # Expected: Metadata updated, full data loaded

def test_upgrade_loads_missing_historical():
    """Test upgrade loads full historical (not just warmup)."""
    # Expected: 30 days loaded (not just warmup)

def test_upgrade_adds_missing_intervals():
    """Test upgrade adds any missing intervals."""
    # Expected: All config intervals present

def test_upgrade_calculates_quality():
    """Test upgrade calculates quality scores."""
    # Expected: Quality > 0 after upgrade

def test_upgrade_preserves_existing_data():
    """Test upgrade doesn't reload existing intervals."""
    # Expected: Existing interval data preserved
```

---

### 2.9 Graceful Degradation (5 tests)
**File**: `tests/integration/test_graceful_degradation.py`

```python
def test_single_symbol_fails_others_proceed():
    """Test one failed symbol doesn't stop others."""
    # Expected: Failed symbol skipped, others loaded

def test_all_symbols_fail_terminates_session():
    """Test session terminates if all symbols fail."""
    # Expected: Session not started

def test_failed_symbol_clear_error_message():
    """Test failed symbol has clear error message."""
    # Expected: Error logged with reason

def test_partial_historical_data():
    """Test symbol with partial historical data."""
    # Expected: Loads available data, quality reflects reality

def test_missing_data_source():
    """Test graceful handling of missing data source."""
    # Expected: Symbol fails validation, clear error
```

---

### 2.10 Thread Safety (5 tests)
**File**: `tests/integration/test_thread_safety.py`

```python
def test_concurrent_symbol_additions():
    """Test multiple threads adding symbols concurrently."""
    # Expected: All additions succeed, no race conditions

def test_concurrent_indicator_additions():
    """Test multiple indicators added concurrently."""
    # Expected: All indicators registered correctly

def test_symbol_operation_lock():
    """Test _symbol_operation_lock prevents race conditions."""
    # Expected: Operations serialized correctly

def test_concurrent_read_write():
    """Test concurrent reads while adding symbols."""
    # Expected: No data corruption

def test_session_data_lock():
    """Test session_data internal lock works correctly."""
    # Expected: Thread-safe access
```

---

## 3. End-to-End Tests (20-30 tests)

### 3.1 Single-Day Session (8 tests)
**File**: `tests/e2e/test_single_day_session.py`

```python
def test_complete_single_day_session():
    """Test complete single-day session from start to end."""
    # Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4

def test_single_day_with_config_symbols():
    """Test single day with symbols from config."""
    # Expected: All config symbols loaded and processed

def test_single_day_with_adhoc_additions():
    """Test single day with adhoc additions during session."""
    # Expected: Adhoc symbols added, processed

def test_single_day_with_midsession_symbol():
    """Test single day with mid-session symbol addition."""
    # Expected: Symbol fully loaded mid-session

def test_single_day_with_upgrade_path():
    """Test single day: scanner adds indicator → strategy upgrades."""
    # Expected: Symbol upgraded during session

def test_single_day_with_deletions():
    """Test single day with symbol deletions."""
    # Expected: Symbols deleted, data cleared

def test_single_day_metadata_export():
    """Test metadata exported correctly at end."""
    # Expected: All metadata in JSON/CSV

def test_single_day_quality_scores():
    """Test quality scores calculated for all symbols."""
    # Expected: Quality > 0 for config symbols
```

---

### 3.2 Multi-Day Backtest (10 tests)
**File**: `tests/e2e/test_multi_day_backtest.py`

```python
def test_3_day_backtest_loop():
    """Test 3-day backtest loop (Phase 1-4 repeated)."""
    # Expected: Each day fresh start, no persistence

def test_5_day_backtest_loop():
    """Test 5-day backtest loop."""
    # Expected: 5 iterations, each day complete

def test_multi_day_no_persistence():
    """Test no state persists between days."""
    # Expected: Day 2 doesn't have Day 1 adhoc symbols

def test_multi_day_clock_advancement():
    """Test clock correctly advanced each day."""
    # Expected: Each day at correct date @ market open

def test_multi_day_skip_holidays():
    """Test multi-day loop skips holidays/weekends."""
    # Expected: Only trading days processed

def test_multi_day_different_symbols_each_day():
    """Test different adhoc symbols each day."""
    # Expected: Each day independent

def test_multi_day_same_config_symbols():
    """Test same config symbols loaded each day."""
    # Expected: Config symbols present every day

def test_multi_day_last_day_data_kept():
    """Test last day data kept after loop."""
    # Expected: Last day data available

def test_multi_day_teardown_completeness():
    """Test complete teardown each day."""
    # Expected: No leftover state

def test_multi_day_performance():
    """Test multi-day backtest completes in reasonable time."""
    # Expected: Performance acceptable (mark as @pytest.mark.slow)
```

---

### 3.3 No Persistence Verification (5 tests)
**File**: `tests/e2e/test_no_persistence.py`

```python
def test_adhoc_symbols_not_persisted():
    """Test adhoc symbols from Day 1 not in Day 2."""
    # Expected: Day 2 starts fresh

def test_metadata_not_persisted():
    """Test metadata not persisted between sessions."""
    # Expected: No metadata from previous day

def test_queues_cleared_between_days():
    """Test queues completely cleared."""
    # Expected: Empty queues at start of each day

def test_indicators_not_persisted():
    """Test indicators not persisted."""
    # Expected: Indicators re-registered each day

def test_config_symbols_reloaded_each_day():
    """Test config symbols loaded fresh each day."""
    # Expected: Full loading every day
```

---

### 3.4 Complete Workflow: Scanner (4 tests)
**File**: `tests/e2e/test_complete_workflow_scanner.py`

```python
def test_scanner_adds_indicator_auto_provision():
    """Test scanner adds indicator, symbol auto-provisioned."""
    # Expected: Symbol created with minimal structure

def test_scanner_indicator_then_strategy_upgrade():
    """Test scanner adds indicator → strategy upgrades to full."""
    # Expected: Symbol upgraded with full data

def test_scanner_multiple_indicators():
    """Test scanner adds multiple indicators to same symbol."""
    # Expected: All indicators registered

def test_scanner_cross_day_no_persistence():
    """Test scanner indicator Day 1 not in Day 2."""
    # Expected: Day 2 fresh, no adhoc symbols
```

---

### 3.5 Complete Workflow: Strategy (3 tests)
**File**: `tests/e2e/test_complete_workflow_strategy.py`

```python
def test_strategy_adds_symbol_full_loading():
    """Test strategy adds symbol, full loading performed."""
    # Expected: Full historical, quality, indicators

def test_strategy_symbol_same_as_config():
    """Test strategy-added symbol same as config loading."""
    # Expected: Identical structure and data

def test_strategy_adds_for_position():
    """Test strategy adds symbol for position management."""
    # Expected: Symbol available for trading
```

---

## 4. Corner Cases & Edge Cases (30+ tests)

### 4.1 Data Availability (8 tests)

```python
def test_symbol_no_parquet_data():
    """Test symbol with no Parquet data fails validation."""

def test_symbol_partial_historical():
    """Test symbol with partial historical data."""

def test_symbol_missing_specific_dates():
    """Test symbol with missing data on specific dates."""

def test_symbol_early_close_day():
    """Test symbol on early close day (half-day)."""

def test_symbol_holiday():
    """Test symbol on holiday (no data)."""

def test_symbol_first_trading_day():
    """Test symbol on its first trading day (no historical)."""

def test_symbol_delisted():
    """Test recently delisted symbol."""

def test_symbol_newly_listed():
    """Test newly listed symbol (limited history)."""
```

---

### 4.2 Interval Edge Cases (8 tests)

```python
def test_unsupported_interval():
    """Test interval that can't be derived (2m from 1m)."""

def test_daily_interval_from_minute():
    """Test daily interval (1d) from minute base."""

def test_second_interval():
    """Test second-based intervals (1s, 5s)."""

def test_hour_interval():
    """Test hour intervals (1h, 4h)."""

def test_week_month_intervals():
    """Test week/month intervals (1w, 1mo)."""

def test_interval_already_exists():
    """Test adding interval that already exists."""

def test_base_interval_different_than_config():
    """Test adhoc interval incompatible with config base."""

def test_multiple_base_intervals():
    """Test scenario with multiple base intervals (error case)."""
```

---

### 4.3 Metadata Edge Cases (6 tests)

```python
def test_metadata_after_multiple_upgrades():
    """Test metadata after multiple operations on same symbol."""

def test_metadata_with_symbol_deletion_readd():
    """Test metadata after delete and re-add."""

def test_metadata_timestamps_accurate():
    """Test added_at timestamp uses TimeManager."""

def test_metadata_added_by_values():
    """Test all possible added_by values (config, strategy, scanner, adhoc)."""

def test_metadata_auto_provisioned_flag():
    """Test auto_provisioned flag accuracy."""

def test_metadata_upgraded_from_adhoc_flag():
    """Test upgraded_from_adhoc flag accuracy."""
```

---

### 4.4 Duplicate Detection (5 tests)

```python
def test_duplicate_full_symbol_config():
    """Test duplicate symbol in config (error case)."""

def test_duplicate_full_symbol_midsession():
    """Test adding symbol that's already fully loaded."""

def test_duplicate_adhoc_symbol():
    """Test adding adhoc symbol twice."""

def test_duplicate_indicator():
    """Test adding same indicator twice."""

def test_duplicate_bar_interval():
    """Test adding same bar interval twice."""
```

---

### 4.5 Validation Edge Cases (5 tests)

```python
def test_validation_all_checks_fail():
    """Test symbol fails all validation checks."""

def test_validation_partial_failure():
    """Test symbol passes some checks, fails others."""

def test_validation_timeout():
    """Test validation with slow data source."""

def test_validation_network_error():
    """Test validation with network errors (live mode)."""

def test_validation_malformed_data():
    """Test validation with malformed Parquet data."""
```

---

## 5. Architectural Compliance Tests (15 tests)

### 5.1 TimeManager API Compliance (8 tests)
**File**: `tests/integration/test_timemanager_compliance.py`

```python
def test_no_datetime_now():
    """Test no direct datetime.now() calls in flow."""
    # Use code inspection + runtime checks

def test_no_hardcoded_trading_hours():
    """Test no hardcoded 9:30/16:00 times."""

def test_all_dates_via_timemanager():
    """Test all date operations use TimeManager."""

def test_holiday_checks_via_timemanager():
    """Test holiday checks use TimeManager."""

def test_market_open_checks_via_timemanager():
    """Test market open checks use TimeManager."""

def test_backtest_time_advancement():
    """Test backtest time advanced via TimeManager."""

def test_current_time_consistency():
    """Test all current time queries return same value."""

def test_added_at_uses_timemanager():
    """Test metadata.added_at uses TimeManager."""
```

---

### 5.2 DataManager API Compliance (7 tests)
**File**: `tests/integration/test_datamanager_compliance.py`

```python
def test_no_direct_parquet_access():
    """Test no direct Parquet file access in flow."""
    # Use code inspection + runtime checks

def test_all_historical_via_datamanager():
    """Test all historical loading via DataManager API."""

def test_all_session_data_via_datamanager():
    """Test all session data via DataManager API."""

def test_data_source_checks_via_datamanager():
    """Test data source checks use DataManager."""

def test_historical_availability_via_datamanager():
    """Test historical availability checks use DataManager."""

def test_load_historical_bars_usage():
    """Test load_historical_bars() called correctly."""

def test_no_hardcoded_file_paths():
    """Test no hardcoded Parquet paths."""
```

---

## 6. Performance Tests (10 tests)

### 6.1 Provisioning Performance (5 tests)
**File**: `tests/performance/test_provisioning_speed.py`

```python
@pytest.mark.slow
def test_single_symbol_provisioning_speed():
    """Test single symbol provisioning completes in < 1 second."""

@pytest.mark.slow
def test_10_symbols_provisioning_speed():
    """Test 10 symbols provision in < 10 seconds."""

@pytest.mark.slow
def test_adhoc_addition_speed():
    """Test adhoc addition completes in < 0.5 seconds."""

@pytest.mark.slow
def test_upgrade_speed():
    """Test upgrade from adhoc to full in < 1 second."""

@pytest.mark.slow
def test_requirement_analysis_speed():
    """Test requirement analysis completes in < 0.1 seconds."""
```

---

### 6.2 Multi-Symbol Loading (5 tests)
**File**: `tests/performance/test_multi_symbol_loading.py`

```python
@pytest.mark.slow
def test_load_20_symbols():
    """Test loading 20 symbols from config."""

@pytest.mark.slow
def test_load_50_symbols():
    """Test loading 50 symbols (stress test)."""

@pytest.mark.slow
def test_concurrent_additions():
    """Test 10 concurrent adhoc additions."""

@pytest.mark.slow
def test_memory_usage():
    """Test memory usage with many symbols."""

@pytest.mark.slow
def test_multi_day_performance_50_symbols():
    """Test 3-day backtest with 50 symbols."""
```

---

## 7. Test Fixtures (New)

### 7.1 Session Coordinator with Data
**File**: `tests/fixtures/session_coordinator_fixture.py`

```python
@pytest.fixture
def session_coordinator_with_data(test_db, mock_time_manager, test_parquet_data):
    """Session coordinator with Parquet test data loaded."""
    # Create coordinator
    # Load test Parquet data
    # Return ready-to-use coordinator
    
@pytest.fixture
def session_coordinator_clean():
    """Clean session coordinator for isolation tests."""
    # Create coordinator
    # No data loaded
    # Return clean coordinator
```

---

### 7.2 Sample Session Configs
**File**: `tests/fixtures/sample_configs.py`

```python
@pytest.fixture
def config_single_symbol():
    """Session config with single symbol."""

@pytest.fixture
def config_multiple_symbols():
    """Session config with 5 symbols."""

@pytest.fixture
def config_with_indicators():
    """Session config with indicators."""

@pytest.fixture
def config_derived_intervals():
    """Session config with multiple derived intervals."""

@pytest.fixture
def config_minimal():
    """Minimal session config (no derived, no indicators)."""
```

---

### 7.3 Mock Indicator Config
**File**: `tests/fixtures/indicator_config_fixture.py`

```python
@pytest.fixture
def sma_indicator_config():
    """SMA indicator config for testing."""

@pytest.fixture
def ema_indicator_config():
    """EMA indicator config for testing."""

@pytest.fixture
def rsi_indicator_config():
    """RSI indicator config for testing."""
```

---

### 7.4 Session State Snapshot
**File**: `tests/fixtures/session_state_fixture.py`

```python
@pytest.fixture
def session_state_snapshot():
    """Capture and compare session state."""
    # Helper to snapshot session_data state
    # Compare before/after operations
    
def snapshot_session(session_data):
    """Take snapshot of session state."""
    # Return dict with symbols, metadata, queues
    
def compare_snapshots(before, after):
    """Compare two snapshots."""
    # Return differences
```

---

### 7.5 Multi-Day Backtest Setup
**File**: `tests/fixtures/multi_day_fixture.py`

```python
@pytest.fixture
def three_day_backtest_setup(test_db, mock_time_manager):
    """Setup for 3-day backtest."""
    # 3 consecutive trading days
    # Parquet data for all days
    # Return setup data

@pytest.fixture
def five_day_backtest_setup(test_db, mock_time_manager):
    """Setup for 5-day backtest with holiday."""
    # 5 days spanning a holiday
    # Return setup data
```

---

## 8. Test Execution Plan

### 8.1 Test Run Commands

```bash
# Run all unit tests (fast, ~2-3 minutes)
pytest tests/unit -v

# Run all integration tests (medium, ~10-15 minutes)
pytest tests/integration -v

# Run all e2e tests (slow, ~30-45 minutes)
pytest tests/e2e -v

# Run specific phase tests
pytest tests/integration/test_phase2_initialization.py -v

# Run all tests except slow
pytest -m "not slow" -v

# Run only provisioning tests
pytest -k "provisioning" -v

# Run with coverage
pytest --cov=app.threads.session_coordinator --cov=app.managers.data_manager.session_data --cov-report=html

# Run parallel (faster)
pytest -n auto  # Requires pytest-xdist
```

---

### 8.2 Continuous Integration

```yaml
# .github/workflows/test-session-lifecycle.yml
name: Session Lifecycle Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run unit tests
        run: pytest tests/unit -v --cov
        
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run integration tests
        run: pytest tests/integration -v
        
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run e2e tests
        run: pytest tests/e2e -v
```

---

## 9. Test Coverage Goals

| Component | Unit | Integration | E2E | Total |
|-----------|------|-------------|-----|-------|
| ProvisioningRequirements | 5 | - | - | 5 |
| Requirement Analysis | 20 | - | - | 20 |
| Provisioning Executor | 15 | - | - | 15 |
| Unified Entry Points | 12 | - | - | 12 |
| Metadata Tracking | 8 | - | - | 8 |
| Validation (Step 0) | 12 | - | - | 12 |
| Phase 0 (Stream Validation) | - | 8 | - | 8 |
| Phase 1 (Teardown) | - | 10 | - | 10 |
| Phase 2 (Initialization) | - | 12 | - | 12 |
| Phase 3a (Adhoc) | - | 10 | - | 10 |
| Phase 3b (Mid-Session) | - | 8 | - | 8 |
| Phase 3c (Deletion) | - | 4 | - | 4 |
| Phase 4 (End Session) | - | 5 | - | 5 |
| Upgrade Path | - | 5 | - | 5 |
| Graceful Degradation | - | 5 | - | 5 |
| Thread Safety | - | 5 | - | 5 |
| Single-Day Session | - | - | 8 | 8 |
| Multi-Day Backtest | - | - | 10 | 10 |
| No Persistence | - | - | 5 | 5 |
| Complete Workflows | - | - | 7 | 7 |
| Corner Cases | - | 32 | - | 32 |
| Architectural Compliance | - | 15 | - | 15 |
| Performance | - | - | 10 | 10 |
| **TOTAL** | **72** | **119** | **40** | **231** |

---

## 10. Test Implementation Priority

### Phase 1 (Week 1): Core Unit Tests
- ProvisioningRequirements
- Requirement Analysis
- Provisioning Executor
- Unified Entry Points
- Validation (Step 0)

**Tests**: ~72 unit tests  
**Time**: 2-3 days

---

### Phase 2 (Week 2): Integration Tests
- Phase 0-4 tests
- Upgrade path
- Graceful degradation
- Thread safety

**Tests**: ~87 integration tests  
**Time**: 4-5 days

---

### Phase 3 (Week 3): E2E & Corner Cases
- Single/multi-day sessions
- Complete workflows
- Corner cases
- Architectural compliance

**Tests**: ~72 tests  
**Time**: 4-5 days

---

### Phase 4 (Week 4): Performance & Polish
- Performance tests
- Fix failures
- Improve coverage
- Documentation

**Tests**: ~10 tests + fixes  
**Time**: 2-3 days

---

## 11. Success Criteria

### Code Coverage
- ✅ Unit: > 90% coverage of new code
- ✅ Integration: > 80% coverage of workflows
- ✅ E2E: All major scenarios covered

### Test Quality
- ✅ All tests pass consistently
- ✅ No flaky tests
- ✅ Clear test names and documentation
- ✅ Fast unit tests (< 0.1s each)
- ✅ Reasonable integration tests (< 5s each)

### Architectural Compliance
- ✅ 100% TimeManager API compliance verified
- ✅ 100% DataManager API compliance verified
- ✅ No hardcoded dates/times/paths
- ✅ Thread safety verified

### Corner Cases
- ✅ All identified edge cases tested
- ✅ Graceful degradation verified
- ✅ Error messages clear and actionable

---

## 12. Test Maintenance

### Ongoing
- Add tests for new features
- Update tests when behavior changes
- Monitor test execution time
- Refactor slow tests

### Monthly
- Review test coverage
- Remove obsolete tests
- Update test data
- Performance regression checks

---

## Summary

**Total Tests**: ~230 tests  
**Unit**: 72 tests (fast)  
**Integration**: 119 tests (medium)  
**E2E**: 40 tests (slow)

**Implementation Time**: 3-4 weeks  
**Maintenance**: Ongoing

**Benefits**:
- Complete coverage of session lifecycle
- High confidence in unified provisioning
- Early detection of regressions
- Clear documentation via tests
- Architectural compliance verified

**Next Steps**: Begin with Phase 1 (Core Unit Tests)
