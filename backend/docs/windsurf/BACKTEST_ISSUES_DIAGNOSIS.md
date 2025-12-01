# Backtest Issues Diagnosis

**Date:** December 1, 2025  
**Session:** example_session.json  
**Reported Issues:**
1. `speed_multiplier: 720.0` not being respected
2. Quality stuck at 0.0% not updating

---

## 🔍 **Issue 1: Speed Multiplier Not Working**

### **Configuration**
```json
"backtest_config": {
  "speed_multiplier": 720.0
}
```

**Expected:** 1 minute of market time = 60/720 = 0.083 seconds real time (12x faster than real-time)  
**Observed:** Session runs at maximum speed (appears instant)

### **Code Flow**

1. **Config Loaded** ✅  
   - `session_configs/example_session.json` line 9: `720.0`
   - SystemManager reads config successfully

2. **Value Propagated** ✅  
   - `session_coordinator.py` line 1234: reads `speed_multiplier` from config
   - Value is accessible in session loop

3. **Delay Applied** ✅  
   - `session_coordinator.py` line 1236: calls `_apply_clock_driven_delay(speed_multiplier)`
   - `session_coordinator.py` lines 2276-2290: calculates and applies delay

### **Likely Causes**

#### **A. Subscription Mode Override**
```python
# system_manager/api.py line 539
elif self._session_config.backtest_config and self._session_config.backtest_config.speed_multiplier == 0:
    subscription_mode = "data-driven"
else:
    subscription_mode = "clock-driven"
```

**Check:** Is subscription mode being set to "data-driven" when it should be "clock-driven"?

#### **B. Delay Too Small**
```python
# session_coordinator.py line 2282
delay_seconds = 60.0 / speed_multiplier
# With 720.0: delay = 60 / 720 = 0.083 seconds

# line 2287 - Only sleeps if > 1ms
if delay_seconds > 0.001:  
    time.sleep(delay_seconds)
```

With 720x speed, each 1-minute bar should pause for 83ms. This is working correctly if condition passes.

#### **C. Time Not Advancing Properly**
```python
# session_coordinator.py line 1221
self._time_manager.set_backtest_time(next_timestamp)
```

If TimeManager time advances happen outside the delay loop, the session might complete instantly.

### **Recommended Checks**

1. **Check Subscription Mode**
   ```bash
   # Look for this log during startup:
   grep "Using subscription mode" logs/*.log
   ```
   Should show: `Using subscription mode: clock-driven`

2. **Check Delay Calculation**
   Add debug logging to `_apply_clock_driven_delay`:
   ```python
   logger.debug(f"Speed: {speed_multiplier}x, Delay: {delay_seconds}s")
   ```

3. **Check Loop Timing**
   Add timestamps to session loop:
   ```python
   logger.info(f"Iteration {iteration} at {time.time()}")
   ```

---

## 🔍 **Issue 2: Quality Stuck at 0.0%**

### **Configuration**
```json
"gap_filler": {
  "enable_session_quality": true
}
```

**Expected:** Quality updates as bars stream  
**Observed:** Quality remains 0.0% for all symbols

### **Code Flow**

1. **Quality Manager Created** ✅  
   - `system_manager/api.py` line 505: DataQualityManager instance created
   - Config value `enable_session_quality: true` read at line 129

2. **Quality Manager Started** ✅  
   - `system_manager/api.py` line 429: `self._quality_manager.start()`
   - Thread should be running

3. **Quality Manager Wired** ✅  
   - `system_manager/api.py` line 564: `set_quality_manager()` called
   - Coordinator has reference to quality manager

4. **Notifications Sent** ❓  
   - `session_coordinator.py` lines 2245-2246: sends notifications
   ```python
   if hasattr(self, 'quality_manager') and self.quality_manager:
       self.quality_manager.notify_data_available(symbol, interval, bar.timestamp)
   ```

5. **Quality Calculated** ❓  
   - `data_quality_manager.py` line 254: `_calculate_quality()` called
   - `data_quality_manager.py` line 334: `set_quality()` called

### **Likely Causes**

#### **A. Quality Manager Not Receiving Notifications**

**Check:** Are notifications being sent?

```python
# session_coordinator.py line 2245
if hasattr(self, 'quality_manager') and self.quality_manager:
```

If `quality_manager` is None or not set, no notifications are sent.

#### **B. Quality Manager Thread Not Running**

**Check:** Thread lifecycle

```python
# Verify thread is alive:
if self._quality_manager and self._quality_manager.is_alive():
    logger.info("Quality manager running")
```

#### **C. Quality Calculation Returns None**

```python
# data_quality_manager.py line 329
if quality is None:
    logger.debug(f"Cannot calculate quality for {symbol} {interval}")
    return
```

Possible reasons:
- Time not set yet (line 296)
- No bars in session data (line 315)
- `calculate_quality_for_current_session` returns None

#### **D. Only Calculating for Base Intervals**

```python
# data_quality_manager.py line 163
if interval in ["1m", "1s", "1d"]:  # Streamed intervals
    self._notification_queue.put((symbol, interval, timestamp))
```

Quality notifications only sent for base intervals (1m, 1s, 1d), NOT for derived intervals (5m, 10m).

#### **E. Quality Display Issue**

The session data display might be:
- Looking at the wrong field
- Rounding to 0.0%
- Showing quality before it's calculated

### **Recommended Checks**

1. **Verify Thread is Running**
   ```bash
   # Look for startup log:
   grep "DataQualityManager thread started" logs/*.log
   ```

2. **Verify Notifications Sent**
   Add debug logging to `notify_data_available`:
   ```python
   logger.info(f"Quality notification: {symbol} {interval} @ {timestamp}")
   ```

3. **Verify Quality Calculation**
   Add debug logging to `_calculate_quality`:
   ```python
   logger.info(f"Calculated quality for {symbol} {interval}: {quality}%")
   ```

4. **Check Session Data Quality Field**
   ```python
   # In session_data_display.py
   quality = symbol_data.quality_1m
   logger.info(f"Quality field value: {quality}")
   ```

---

## 🎯 **Action Items**

### **For Speed Multiplier**

1. ✅ Verify subscription mode is "clock-driven" in logs
2. ✅ Add debug logging to `_apply_clock_driven_delay`
3. ✅ Measure actual elapsed time vs expected time
4. ✅ Check if delay is being skipped due to condition

### **For Quality**

1. ✅ Verify DataQualityManager thread is running
2. ✅ Verify notifications are being sent from coordinator
3. ✅ Verify notifications are being received by quality manager
4. ✅ Verify quality calculation is not returning None
5. ✅ Check if quality is calculated but not displayed properly

---

## 📝 **Debug Commands**

```bash
# Start system with debug logging
system start

# Check thread status (while running in another terminal)
grep "thread started" backend/logs/*.log | tail -10

# Check quality notifications
grep "quality" backend/logs/*.log | tail -20

# Check speed/delay
grep "delay\|speed" backend/logs/*.log | tail -20
```

---

## 🔧 **Quick Fix Attempts**

### **1. Enable Debug Logging**
Add to top of `data_quality_manager.py`:
```python
logger.setLevel("DEBUG")
```

### **2. Force Quality Calculation**
In `session_coordinator.py`, after processing bars:
```python
# Force immediate quality calculation
if self.quality_manager:
    for symbol in symbols:
        self.quality_manager.notify_data_available(symbol, "1m", bar.timestamp)
```

### **3. Verify Speed Multiplier Read**
Add after reading config:
```python
logger.critical(f"SPEED MULTIPLIER: {self.session_config.backtest_config.speed_multiplier}")
```

---

**Status:** ✅ Debug logging added - Ready to test

**Next:** Run debug session and analyze logs

---

## 🔬 **Debug Logging Added**

### **Quality Manager Debug** (data_quality_manager.py)

1. **Notification Receipt** (line 165):
   ```
   📬 QUALITY MANAGER: Received notification AAPL 1m @ 09:30:00
   ```

2. **Thread Processing** (line 248):
   ```
   🔄 QUALITY THREAD: Processing notification from queue: AAPL 1m @ 09:30:00
   ```

3. **Quality Enabled Check** (line 252, 255):
   ```
   ⛔ QUALITY DISABLED: enable_session_quality=False
   OR
   ✅ QUALITY ENABLED: Proceeding to calculate quality for AAPL 1m
   ```

4. **Quality Calculation** (line 334, 338):
   ```
   ❌ QUALITY CALC: Cannot calculate quality for AAPL 1m (returned None)
   OR
   ✅ QUALITY CALC: AAPL 1m = 74.5% (actual_bars=289)
   ```

5. **Quality Saved** (line 340):
   ```
   💾 QUALITY SAVED: AAPL 1m quality set in session_data
   ```

### **Coordinator Quality Wiring** (session_coordinator.py)

1. **Quality Manager Check** (line 2249):
   ```
   🔍 QUALITY CHECK: has_attr=True, is_not_none=True
   ```

2. **Notification Sent** (line 2253):
   ```
   📊 SENDING QUALITY NOTIFICATION: AAPL 1m @ 09:30:00
   ```

3. **Manager Not Available** (line 2256):
   ```
   ❌ QUALITY MANAGER NOT AVAILABLE!
   ```

### **Speed Multiplier Debug** (session_coordinator.py)

1. **Data-Driven Mode** (line 2287):
   ```
   ⏱️  SPEED: Data-driven mode (no delay)
   ```

2. **Clock-Driven Mode** (line 2299):
   ```
   ⏱️  SPEED: 720.0x, CALCULATED DELAY: 0.083s
   ```

3. **Sleep Execution** (line 2306):
   ```
   ⏱️  SLEPT: 0.084s (expected 0.083s)
   ```

4. **Sleep Skipped** (line 2308):
   ```
   ⏱️  SKIPPED SLEEP: delay too small (0.000014s)
   ```

---

## 🚀 **Running Debug Session**

### **Option 1: Using Debug Script**
```bash
cd /home/yohannes/mismartera/backend
./scripts/debug_backtest_issues.sh

# In CLI:
system start
data session
```

### **Option 2: Manual**
```bash
./start_cli.sh

# In CLI:
system start
data session

# In another terminal, watch logs:
tail -f logs/*.log | grep -E "🔍|📊|❌|📬|🔄|✅|💾|⏱️"
```

### **What to Look For**

#### **Quality Issue Diagnosis**

1. **Is quality manager wired?**
   - Look for: `🔍 QUALITY CHECK: has_attr=True, is_not_none=True`
   - If False: Quality manager not set on coordinator

2. **Are notifications sent?**
   - Look for: `📊 SENDING QUALITY NOTIFICATION:`
   - If missing: Coordinator not sending notifications

3. **Are notifications received?**
   - Look for: `📬 QUALITY MANAGER: Received notification`
   - If missing: Notifications not reaching quality manager

4. **Is thread processing?**
   - Look for: `🔄 QUALITY THREAD: Processing notification`
   - If missing: Thread stalled or crashed

5. **Is quality enabled?**
   - Look for: `✅ QUALITY ENABLED:` or `⛔ QUALITY DISABLED:`
   - If disabled: Config issue

6. **Is quality calculated?**
   - Look for: `✅ QUALITY CALC:` or `❌ QUALITY CALC:`
   - If None: Calculation failing

7. **Is quality saved?**
   - Look for: `💾 QUALITY SAVED:`
   - If missing: Not reaching set_quality()

#### **Speed Issue Diagnosis**

1. **What mode is active?**
   - Look for: `⏱️  SPEED: Data-driven` or `⏱️  SPEED: 720.0x`
   - Should show: Clock-driven with 720.0x

2. **Is delay calculated correctly?**
   - Look for: `CALCULATED DELAY: 0.083s`
   - Should be: 60 / 720 = 0.083 seconds

3. **Is sleep executed?**
   - Look for: `⏱️  SLEPT: 0.084s (expected 0.083s)`
   - Should match calculated delay

4. **How many sleeps occur?**
   - Count occurrences of `⏱️  SLEPT:`
   - Should be: ~390 times (one per 1-minute bar)

---

## 📊 **Expected Output (Healthy System)**

```
🔍 QUALITY CHECK: has_attr=True, is_not_none=True
📊 SENDING QUALITY NOTIFICATION: AAPL 1m @ 09:30:00
📬 QUALITY MANAGER: Received notification AAPL 1m @ 09:30:00
🔄 QUALITY THREAD: Processing notification from queue: AAPL 1m @ 09:30:00
✅ QUALITY ENABLED: Proceeding to calculate quality for AAPL 1m
✅ QUALITY CALC: AAPL 1m = 0.3% (actual_bars=1)
💾 QUALITY SAVED: AAPL 1m quality set in session_data
⏱️  SPEED: 720.0x, CALCULATED DELAY: 0.083s
⏱️  SLEPT: 0.084s (expected 0.083s)
```

**Quality should increase:** 0.3% → 25% → 50% → 75% → 100% as session progresses

---

**Status:** ✅ Debug logging complete - Ready for testing
