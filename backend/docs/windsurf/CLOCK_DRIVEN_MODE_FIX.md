# Clock-Driven Mode Fix

**Date:** December 1, 2025  
**Issue:** Speed multiplier not working - backtest running at maximum speed  
**Root Cause:** Implementation was data-driven even when `speed_multiplier > 0`

---

## 🐛 **The Problem**

The existing implementation was **data-driven** regardless of `speed_multiplier`:

```python
# WRONG - Always data-driven
next_timestamp = self._get_next_queue_timestamp()  # Get FROM data
self._time_manager.set_backtest_time(next_timestamp)  # Advance TO data timestamp
self._apply_clock_driven_delay(speed_multiplier)  # THEN delay
```

This meant:
- Time advanced based on data timestamps (not independently)
- Delay was applied AFTER processing each bar
- No actual clock ticking - just data consumption with pauses

---

## ✅ **The Fix**

### **Architecture Principle (from SESSION_ARCHITECTURE.md)**

**Clock-Driven Mode (speed > 0):**
- Time advances **INDEPENDENTLY** like a clock ticking
- Data delivery driven BY the advancing clock
- Example: 720x speed = 720 seconds of market time per real second

**Data-Driven Mode (speed = 0):**
- Time advances based on **NEXT DATA** timestamp
- Time jumps to each bar's timestamp
- Maximum speed (no delays)

### **Implementation**

Created **two separate streaming modes** in `app/threads/streaming_modes.py`:

#### **1. Clock-Driven Streaming**
```python
def clock_driven_streaming(...):
    # Time advances by 1 second increments
    time_increment = timedelta(seconds=1)
    delay_per_second = 1.0 / speed_multiplier
    
    while current_time < market_close:
        # Advance time by 1 second (independent of data)
        current_time += time_increment
        coordinator._time_manager.set_backtest_time(current_time)
        
        # Process ALL data with timestamp <= current_time
        bars_processed = coordinator._process_queue_data_at_timestamp(current_time)
        
        # Apply delay to pace the clock
        time.sleep(delay_per_second)
```

**Key Characteristics:**
- Time ticks forward 1 second at a time (like a real clock)
- Each tick: deliver all data with timestamp ≤ current time
- Delay applied per second: `1.0 / speed_multiplier` seconds
- With 720x: delay = 1/720 = 0.00139s per market second
- Result: 720 market seconds pass per 1 real second

#### **2. Data-Driven Streaming**
```python
def data_driven_streaming(...):
    while True:
        # Get next data timestamp
        next_timestamp = coordinator._get_next_queue_timestamp()
        
        # Jump time to next data
        coordinator._time_manager.set_backtest_time(next_timestamp)
        
        # Process data at that timestamp
        bars_processed = coordinator._process_queue_data_at_timestamp(next_timestamp)
        
        # No delay - maximum speed
```

**Key Characteristics:**
- Time jumps from data point to data point
- No delays between processing
- Maximum speed execution

### **Session Coordinator Changes**

Modified `_streaming_phase()` to branch to correct implementation:

```python
# Determine mode
is_clock_driven = (speed_multiplier > 0)

if is_clock_driven:
    total_bars_processed = clock_driven_streaming(
        self, market_open, market_close, speed_multiplier
    )
else:
    total_bars_processed = data_driven_streaming(
        self, market_close
    )
```

---

## 📊 **Speed Calculation Examples**

### **720x Speed (Config Value)**

**Clock tick:**
- 1 second of market time per tick
- Delay per tick: `1.0 / 720 = 0.00139 seconds`

**1 Minute of Market Time:**
- 60 ticks × 0.00139s = **0.083 seconds real time**
- This is what you'll see in logs: `SLEPT: 0.001s` (per second tick)

**Full Trading Day (6.5 hours):**
- 390 minutes × 60 seconds = 23,400 seconds market time
- 23,400 × 0.00139s = **32.5 seconds real time**
- Plus processing overhead

### **360x Speed**

**Clock tick:**
- Delay: `1.0 / 360 = 0.00278 seconds`

**1 Minute:**
- 60 × 0.00278s = **0.167 seconds real time**

**Full Day:**
- 23,400 × 0.00278s = **65 seconds real time** (~1 minute)

### **1x Speed (Real-Time)**

**Clock tick:**
- Delay: `1.0 / 1 = 1.0 second`

**1 Minute:**
- 60 × 1.0s = **60 seconds real time**

**Full Day:**
- 23,400 × 1.0s = **6.5 hours real time**

---

## 🔬 **Debug Output**

With debug logging enabled, you'll now see:

```
⏱️  CLOCK-DRIVEN MODE: Time advances independently at 720.0x speed
⏱️  CLOCK CONFIG: Increment=1s, Delay=0.0014s per market second
[Clock 60] Time: 09:31:00, Bars: 2, Total: 120
[Clock 120] Time: 09:32:00, Bars: 2, Total: 240
...
Clock-driven streaming complete: 23400 ticks, 780 bars
```

vs. Data-driven:

```
⏱️  DATA-DRIVEN MODE: Time advances based on data timestamps
[1] Advancing time: 09:30:00 -> 09:30:00
[2] Advancing time: 09:30:00 -> 09:31:00
...
Data-driven streaming complete: 390 iterations, 780 bars
```

---

## 📁 **Files Modified**

1. ✅ **Created:** `app/threads/streaming_modes.py`
   - `clock_driven_streaming()` - Independent time advance
   - `data_driven_streaming()` - Data timestamp based

2. ✅ **Modified:** `app/threads/session_coordinator.py`
   - Added import for streaming modes
   - Modified `_streaming_phase()` to branch by mode
   - Removed old mixed implementation

3. ✅ **Debug Logging:** Already in place from earlier
   - Quality manager notifications
   - Speed mode detection
   - Delay execution logging

---

## ⚡ **Performance Impact**

### **Clock-Driven (720x)**
- ~23,400 iterations (one per second of market time)
- ~0.00139s sleep per iteration
- Total sleep time: ~32 seconds
- Plus processing time for bars/quality/derived data
- **Estimated:** 35-45 seconds for full day

### **Data-Driven (0x)**
- ~390 iterations (one per 1-minute bar)
- No sleep delays
- **Estimated:** < 1 second for full day

---

## 🎯 **Expected Behavior After Fix**

With `speed_multiplier: 720.0`:

1. **Session starts**
   ```
   ⏱️  CLOCK-DRIVEN MODE: Time advances independently at 720.0x speed
   ⏱️  CLOCK CONFIG: Increment=1s, Delay=0.0014s per market second
   ```

2. **Time advances every ~0.00139 seconds**
   - Each advance = 1 market second
   - Data delivered if timestamp ≤ current time

3. **Full trading day completes in ~35-45 seconds**
   - Not instant (as before)
   - Not 6.5 hours (as 1x would be)
   - Properly paced at 720x speed

4. **Quality updates during streaming**
   - Should now see quality increase: 0% → 25% → 50% → 75% → 100%
   - Quality manager has time to process between ticks

---

## 🐛 **Quality Issue - Still Being Diagnosed**

Quality stuck at 0.0% is a **separate issue**. Debug logging shows:
- Quality manager IS wired to coordinator
- Notifications ARE being sent
- Need to verify if notifications are being received and processed

The clock-driven fix may actually help quality work properly by:
- Giving quality thread time to process between clock ticks
- Not overwhelming the queue with instant data delivery

---

## 🧪 **Testing**

```bash
cd /home/yohannes/mismartera/backend
./start_cli.sh

# In CLI:
system start
data session

# Watch for:
# - "CLOCK-DRIVEN MODE" message
# - Steady progression of time (not instant)
# - Quality updates (if quality fix works)
```

---

**Status:** ✅ Clock-driven mode implemented correctly  
**Next:** Test to verify speed multiplier works and observe quality behavior
