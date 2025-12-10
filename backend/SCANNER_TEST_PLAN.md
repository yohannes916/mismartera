# Scanner Framework Test Plan

## Overview

Comprehensive testing plan for the scanner framework implementation.

---

## Test Configurations Created

### 1. Basic Test (Pre-Session Only)
**File**: `session_configs/scanner_test.json`

**Scanners**:
- Gap Scanner (pre-session only)

**Purpose**: Test basic pre-session scanner lifecycle

**Expected Behavior**:
- Scanner loads 62 symbols from sp500_sample.txt
- Setup provisions lightweight data (SMA indicators)
- Scan executes once before session
- Finds 0-5 qualifying gap-up stocks
- Teardown removes unqualified symbols immediately
- Regular session continues with only qualified symbols

---

### 2. Comprehensive Test (Pre-Session + Regular Session)
**File**: `session_configs/scanner_comprehensive_test.json`

**Scanners**:
1. Gap Scanner (pre-session only)
2. Momentum Scanner (regular session: 09:35-10:30, every 5m)

**Purpose**: Test full scanner lifecycle with both schedule types

**Expected Behavior**:
- Gap scanner runs pre-session (setup → scan → teardown)
- Momentum scanner runs regular session (setup → session start → scheduled scans → teardown)
- Both scanners load different universes (sp500_sample vs nasdaq100_sample)
- Momentum scanner scans at: 09:35, 09:40, 09:45, 09:50, 09:55, 10:00, 10:05, 10:10, 10:15, 10:20, 10:25, 10:30 (12 scans)
- Both scanners clean up at appropriate times

---

## Test Execution

### Test 1: Basic Pre-Session Scanner

```bash
cd /home/yohannes/mismartera/backend

# Start system with basic test config
./start_cli.sh

# In CLI
system start session_configs/scanner_test.json

# Wait for completion, then validate
python test_scanner_framework.py
```

**What to Watch For**:
```
[SCANNER_MANAGER] Loading 1 scanners
[SCANNER_MANAGER] Loaded scanner: scanners.examples.gap_scanner_complete
=== PRE-SESSION SCANNER SETUP ===
[SCANNER_MANAGER] Setting up scanner: scanners.examples.gap_scanner_complete
[GAP_SCANNER] Loaded 62 symbols
[SCANNER_MANAGER] Setup complete (timing)
[SCANNER_MANAGER] Running pre-session scan
[GAP_SCANNER] Found X qualifying symbols
[SCANNER_MANAGER] Qualifying symbols: [...]
[SCANNER_MANAGER] Tearing down pre-session-only scanner
[SCANNER_MANAGER] Teardown complete
```

---

### Test 2: Comprehensive Multi-Scanner

```bash
# In CLI
system start session_configs/scanner_comprehensive_test.json

# Wait for completion, then validate
python test_scanner_framework.py
```

**What to Watch For**:

**Pre-Session Phase**:
```
[SCANNER_MANAGER] Loading 2 scanners
[SCANNER_MANAGER] Loaded scanner: scanners.examples.gap_scanner_complete
[SCANNER_MANAGER] Loaded scanner: scanners.examples.momentum_scanner
=== PRE-SESSION SCANNER SETUP ===
[SCANNER_MANAGER] Setting up scanner: scanners.examples.gap_scanner_complete
[SCANNER_MANAGER] Setting up scanner: scanners.examples.momentum_scanner
[SCANNER_MANAGER] Running pre-session scan: scanners.examples.gap_scanner_complete
[GAP_SCANNER] Found X qualifying symbols
[SCANNER_MANAGER] Tearing down pre-session-only scanner: scanners.examples.gap_scanner_complete
```

**Session Start**:
```
[SCANNER_MANAGER] Session started
[SCANNER_MANAGER] Next scan for scanners.examples.momentum_scanner: 2024-01-02 09:35:00
```

**Streaming Phase**:
```
[SCANNER_MANAGER] Scheduled scan triggered: scanners.examples.momentum_scanner at 2024-01-02 09:35:00
[MOMENTUM_SCANNER] Scanning 100 symbols for momentum...
[MOMENTUM_SCANNER] Found X momentum stocks
[SCANNER_MANAGER] Scan complete: X symbols, XXXms
...
(Repeat every 5 minutes until 10:30)
```

**Session End**:
```
[SCANNER_MANAGER] Session ended, tearing down scanners
[SCANNER_MANAGER] Tearing down scanner: scanners.examples.momentum_scanner
[MOMENTUM_SCANNER] Teardown complete: Kept X symbols, removed Y symbols
```

---

## Validation Checklist

### ✅ Initialization Phase
- [ ] Scanner manager created
- [ ] Scanner manager initialized
- [ ] Correct number of scanners loaded
- [ ] Each scanner instantiated successfully

### ✅ Pre-Session Phase
- [ ] setup() called for all scanners
- [ ] scan() called for pre-session scanners only
- [ ] teardown() called for pre-session-only scanners
- [ ] Qualifying symbols identified
- [ ] Symbols promoted via add_symbol()

### ✅ Session Start Phase
- [ ] on_session_start() called
- [ ] next_scan_time initialized for regular session scanners
- [ ] Correct schedule times logged

### ✅ Regular Session Phase
- [ ] Scheduled scans triggered at correct times
- [ ] scan() executes successfully
- [ ] Qualifying symbols found and promoted
- [ ] No scans outside schedule window

### ✅ Session End Phase
- [ ] on_session_end() called
- [ ] teardown() called for remaining scanners
- [ ] Unqualified symbols removed
- [ ] Config symbols protected
- [ ] Locked symbols not removed

### ✅ Error Handling
- [ ] No exceptions during execution
- [ ] Graceful handling of missing data
- [ ] Clear error messages if failures occur

---

## Expected Results

### Gap Scanner (Pre-Session)

**Universe**: 62 symbols from sp500_sample.txt

**Criteria**:
- Gap >= 2% from previous close
- Volume >= 1,000,000 shares
- Price <= $500

**Expected Qualifying Symbols**: 0-5 (depends on market data)

**Lifecycle**:
1. Setup provisions SMA(20) indicators for 62 symbols
2. Scan checks all 62 symbols
3. Promotes qualifying symbols
4. Teardown removes ~57-62 unqualified symbols
5. No activity during regular session

---

### Momentum Scanner (Regular Session)

**Universe**: 100 symbols from nasdaq100_sample.txt

**Criteria**:
- Volume >= 500,000 shares
- Price above SMA(20)
- Positive price change

**Expected Qualifying Symbols**: 5-20 (depends on market conditions)

**Lifecycle**:
1. Setup provisions SMA(20) indicators for 100 symbols
2. No pre-session scan
3. Session starts → next_scan_time = 09:35
4. Scans every 5 minutes from 09:35 to 10:30 (12 scans)
5. Promotes qualifying symbols during any scan
6. Teardown at end removes symbols that never qualified

**Scan Schedule**:
- 09:35:00 - First scan
- 09:40:00 - Second scan
- 09:45:00 - Third scan
- ... (every 5 minutes)
- 10:30:00 - Last scan
- After 10:30 - No more scans

---

## Performance Metrics

### Expected Timing (Approximate)

**Gap Scanner**:
- Setup: 1,000-3,000ms (62 symbols × ~20ms each)
- Scan: 200-500ms (checking 62 symbols)
- Teardown: 100-300ms (removing ~57-62 symbols)

**Momentum Scanner**:
- Setup: 2,000-5,000ms (100 symbols × ~20ms each)
- Each Scan: 300-800ms (checking 100 symbols)
- Teardown: 200-500ms (removing unqualified symbols)

---

## Troubleshooting

### Issue: Scanners Not Loading

**Check**:
1. Module path correct in config?
2. Scanner class inherits from BaseScanner?
3. Scanner has scan() method implemented?

**Look for**:
```
[SCANNER_MANAGER] Failed to load scanner: ...
```

---

### Issue: Pre-Session Scan Not Running

**Check**:
1. `pre_session: true` in config?
2. Scanner setup() returned true?

**Look for**:
```
[SCANNER_MANAGER] Setting up scanner: ...
[SCANNER_MANAGER] Running pre-session scan: ...
```

---

### Issue: Regular Session Scans Not Triggering

**Check**:
1. `regular_session` schedules defined?
2. Current backtest time within schedule window?
3. Interval format correct (e.g., "5m")?

**Look for**:
```
[SCANNER_MANAGER] Session started
[SCANNER_MANAGER] Next scan for ... at ...
[SCANNER_MANAGER] Scheduled scan triggered: ...
```

**Debug**:
```python
# Check if time advanced to 09:35
grep "session_time" logs/latest.log | grep "09:3"
```

---

### Issue: Symbols Not Promoted

**Check**:
1. Criteria met for any symbols?
2. add_symbol() being called?
3. Historical data available?

**Look for**:
```
[SCANNER_NAME] Found X qualifying symbols
[SCANNER_MANAGER] Qualifying symbols: [...]
```

---

### Issue: Teardown Not Removing Symbols

**Check**:
1. Are symbols locked (positions open)?
2. Are symbols config symbols?
3. teardown() being called?

**Look for**:
```
[SCANNER_MANAGER] Tearing down scanner: ...
[SCANNER_NAME] Teardown complete: Kept X, removed Y
```

---

## Validation Script Usage

### Run Validation

```bash
# Automatic (uses latest log)
python test_scanner_framework.py

# Manual (specify log file)
python test_scanner_framework.py logs/mismartera_20241208_182000.log
```

### Expected Output

```
✅ Loaded 5000 log lines from logs/mismartera_20241208_182000.log

================================================================================
SCANNER FRAMEWORK TEST VALIDATION
================================================================================

📋 Checking Scanner Initialization...
  ✅ Scanner manager created and initialized
  ✅ Loaded 2 scanners:
     - scanners.examples.gap_scanner_complete
     - scanners.examples.momentum_scanner
  ✅ Scanner count verified: 2

🔍 Checking Pre-Session Scanner Setup...
  ✅ Setup called for 2 scanners
  ✅ Pre-session scan executed for 1 scanners
  ✅ Teardown executed for 1 pre-session-only scanners
  ✅ Found 3 qualifying symbols:
     ['TSLA', 'NVDA', 'AMD']

⏰ Checking Regular Session Scans...
  ✅ Session start notification sent
  ✅ Scheduled 1 regular session scanners
  ✅ Executed 12 scheduled scans

🧹 Checking Scanner Teardown...
  ✅ Session end notification sent
  ✅ Teardown executed for 1 scanners

⚠️  Checking for Errors and Warnings...
  ✅ No errors found
  ✅ No warnings found

================================================================================
TEST SUMMARY
================================================================================

✅ Initialization: PASSED
✅ Pre-Session: PASSED
✅ Regular Session: PASSED
✅ Teardown: PASSED

📊 Score: 4/4 checks passed

🎉 Scanner framework test: PASSED!
```

---

## Success Criteria

### Minimum Requirements (Basic Test)
- ✅ Scanner manager initializes
- ✅ Gap scanner loads
- ✅ Pre-session scan executes
- ✅ Teardown completes
- ✅ No errors

### Full Success (Comprehensive Test)
- ✅ Both scanners load
- ✅ Gap scanner runs pre-session and tears down
- ✅ Momentum scanner runs 12 scheduled scans
- ✅ Symbols promoted correctly
- ✅ Teardown removes unqualified symbols
- ✅ No errors or warnings

---

## Next Steps After Testing

### If Tests Pass ✅
1. Create more scanner examples
2. Test with larger universes
3. Test error scenarios (missing files, bad data)
4. Performance optimization
5. Move to strategy framework

### If Tests Fail ❌
1. Review error logs
2. Check configuration
3. Verify scanner implementation
4. Debug integration points
5. Fix issues and retest

---

## Manual Verification

Beyond automated validation, manually verify:

1. **Data Loading**:
   - Check session_data has scanner symbols
   - Verify indicators provisioned
   - Confirm historical bars loaded

2. **Symbol Tracking**:
   - Count active symbols before/after scans
   - Verify promoted symbols in session_data
   - Check removed symbols cleaned up

3. **Timing**:
   - Verify scans happen at scheduled times
   - Check no scans outside schedule window
   - Confirm teardown timing correct

4. **State Machine**:
   - Scanner states progress correctly
   - No scanners stuck in ERROR state
   - Proper state transitions logged

---

## Files Reference

- `session_configs/scanner_test.json` - Basic test config
- `session_configs/scanner_comprehensive_test.json` - Full test config
- `test_scanner_framework.py` - Validation script
- `scanners/examples/gap_scanner_complete.py` - Pre-session scanner
- `scanners/examples/momentum_scanner.py` - Regular session scanner

---

## Test Matrix

| Test Case | Gap Scanner | Momentum Scanner | Expected Scans | Duration |
|-----------|-------------|------------------|----------------|----------|
| Basic | ✅ | ❌ | 1 (pre-session) | ~30 sec |
| Comprehensive | ✅ | ✅ | 13 (1 pre + 12 regular) | ~5 min |

---

**Ready to test! Follow the execution steps above.** 🧪
