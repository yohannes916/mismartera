# Quick Start: Scanner Framework Testing

## 🚀 Run Tests in 3 Steps

### Step 1: Basic Test (Pre-Session Only)

```bash
cd /home/yohannes/mismartera/backend
./start_cli.sh
```

In the CLI:
```bash
system start session_configs/scanner_test.json
```

**Wait for completion** (look for "Backtest complete" or system stops)

---

### Step 2: Validate Results

```bash
# In a new terminal (or after CLI exits)
cd /home/yohannes/mismartera/backend
python test_scanner_framework.py
```

**Expected**: All 4 checks pass ✅

---

### Step 3: Comprehensive Test (Both Scanner Types)

```bash
./start_cli.sh
```

In the CLI:
```bash
system start session_configs/scanner_comprehensive_test.json
```

**Wait for completion**, then validate:
```bash
python test_scanner_framework.py
```

**Expected**: All 4 checks pass, 12+ scans executed ✅

---

## 📊 What to Look For

### Console Output

**Good Signs** ✅:
```
[SCANNER_MANAGER] Loaded 1 scanners  (or 2 for comprehensive)
[SCANNER_MANAGER] === PRE-SESSION SCANNER SETUP ===
[SCANNER_MANAGER] Setup complete
[GAP_SCANNER] Loaded 62 symbols
[GAP_SCANNER] Found X qualifying symbols
[SCANNER_MANAGER] Qualifying symbols: [...]
[SCANNER_MANAGER] Teardown complete
```

**For Comprehensive Test**:
```
[SCANNER_MANAGER] Session started
[SCANNER_MANAGER] Next scan for scanners.examples.momentum_scanner: 09:35:00
[SCANNER_MANAGER] Scheduled scan triggered at 09:35:00
[MOMENTUM_SCANNER] Found X momentum stocks
... (repeats every 5 minutes)
[SCANNER_MANAGER] Session ended, tearing down scanners
```

**Bad Signs** ❌:
```
ERROR
FAILED
Exception
Traceback
```

---

## 🎯 Success Criteria

### Basic Test
- ✅ Scanner loads
- ✅ Pre-session scan runs
- ✅ Symbols promoted
- ✅ Teardown completes
- ✅ No errors

### Comprehensive Test
- ✅ Both scanners load
- ✅ Gap scanner: pre-session only
- ✅ Momentum scanner: 12 scans (09:35-10:30)
- ✅ Both teardowns complete
- ✅ No errors

---

## 🐛 Quick Troubleshooting

### "No scanners configured"
→ Check config file path is correct

### "Scanner module not found"
→ Check module path: `scanners.examples.gap_scanner_complete`

### "No universe file"
→ Check `data/universes/sp500_sample.txt` exists

### "No scans triggered"
→ Check backtest time reaches 09:35 (for momentum scanner)

---

## 📝 Test Files Created

1. ✅ `session_configs/scanner_test.json` - Basic test
2. ✅ `session_configs/scanner_comprehensive_test.json` - Full test
3. ✅ `scanners/examples/momentum_scanner.py` - Regular session scanner
4. ✅ `test_scanner_framework.py` - Validation script
5. ✅ `SCANNER_TEST_PLAN.md` - Detailed test plan
6. ✅ `RUN_SCANNER_TESTS.md` - This file

---

## 📖 Full Documentation

- **Test Plan**: `SCANNER_TEST_PLAN.md` - Detailed testing guide
- **Implementation**: `SCANNER_FRAMEWORK_COMPLETE.md` - Full overview
- **Phase Docs**: `PHASE_2_*.md` - Implementation details

---

## 🎉 Next Steps

After tests pass:
1. ✅ Scanner framework validated
2. Create more scanner examples
3. Test with larger universes
4. Move to strategy framework

---

**Ready! Run the commands above to test the scanner framework.** 🚀
