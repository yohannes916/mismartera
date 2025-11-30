# Session Data Validation Requirements
**Purpose**: Verify correct operation of stream coordinator, session_data, and data flow during backtest

## 1. SYSTEM STATE INVARIANTS

### 1.1 Basic State Consistency
- [ ] `system_state` must be one of: `running`, `paused`, `stopped`
- [ ] `system_mode` must be `backtest` throughout the session
- [ ] Once `system_state` becomes `stopped`, it must never return to `running`
- [ ] `session_active` must be `True` while `system_state == running`
- [ ] `session_ended` must be `False` while `system_state == running`

### 1.2 Session Date/Time
- [ ] `session_date` must remain constant throughout the backtest (same trading day)
- [ ] `session_time` must be monotonically increasing (never go backwards)
- [ ] `session_time` must be in format `HH:MM:SS`
- [ ] `session_time` must be within market hours (09:30:00 - 16:00:00) or slightly beyond at end
- [ ] `session_time` progression is independent of backtest speed (60x, 1x, etc.)

---

## 2. STREAM COORDINATOR QUEUE INVARIANTS

### 2.1 Queue Size Behavior
- [ ] Queue size must be monotonically decreasing over time (items consumed faster than produced)
- [ ] Queue size must eventually reach 0 when stream exhausted
- [ ] Queue size must never be negative
- [ ] For each symbol, queue size at row N+1 <= queue size at row N (or same if no consumption)

### 2.2 Queue Timestamps
- [ ] `{SYMBOL}_queue_BAR_oldest` must be monotonically increasing (or same)
- [ ] `{SYMBOL}_queue_BAR_newest` must stay constant or increase (new batches added)
- [ ] `oldest` timestamp must always be <= `newest` timestamp
- [ ] `oldest` must be <= current `session_time` (not from future)
- [ ] When queue size = 0, both `oldest` and `newest` should be "N/A"

### 2.3 Queue Time Progression
- [ ] As items are consumed, `oldest` timestamp should advance
- [ ] The gap between `oldest` and current `session_time` should shrink over time
- [ ] Once `oldest` reaches `newest`, queue should drain completely soon after
- [ ] `oldest` should never jump backwards (only advance or stay same)

---

## 3. BAR DATA INVARIANTS

### 3.1 1m Bar Accumulation
- [ ] `{SYMBOL}_1m_bars` must be monotonically increasing (new bars added)
- [ ] `{SYMBOL}_1m_bars` must never decrease (bars are not removed)
- [ ] Final bar count should match expected bars for trading day (390 bars = 6.5 hours)
- [ ] Bar count at row N+1 >= bar count at row N

### 3.2 Derived Bars (5m, 15m, etc.)
- [ ] `{SYMBOL}_5m_bars` must be monotonically increasing
- [ ] 5m bars should start appearing when `1m_bars >= 5`
- [ ] Ratio: `5m_bars` should be approximately `1m_bars / 5` (may lag slightly)
- [ ] 5m bars must never exceed `floor(1m_bars / 5) + 1` (accounting for partial bars)
- [ ] Once 5m bar count > 0, it should continuously increase (not stay stagnant for long)

### 3.3 Bar Quality
- [ ] `{SYMBOL}_bar_quality` must be between 0.0 and 100.0
- [ ] Bar quality should generally be >= 95.0 for clean data
- [ ] Bar quality should not fluctuate wildly (no jumps > 5% between consecutive rows)
- [ ] Bar quality should stabilize or improve as session progresses

---

## 4. PRICE AND VOLUME INVARIANTS

### 4.1 Session High/Low
- [ ] `{SYMBOL}_high` must be >= `{SYMBOL}_low` (always)
- [ ] `{SYMBOL}_high` must be monotonically increasing or same (new highs discovered)
- [ ] `{SYMBOL}_low` must be monotonically decreasing or same (new lows discovered)
- [ ] High/Low should stabilize near end of session (no more updates)

### 4.2 Volume
- [ ] `{SYMBOL}_volume` must be monotonically increasing
- [ ] Volume must never decrease between consecutive rows
- [ ] Volume should correlate with bar count increases
- [ ] Final volume should be realistic for the symbol (millions of shares)

---

## 5. TEMPORAL CONSISTENCY

### 5.1 Time Alignment
- [ ] All symbols must show same `session_time` in each row (synchronized)
- [ ] Session time must advance in sync with bar accumulation
- [ ] Session time progression is based on data timestamps, not real-time clock

### 5.2 Bar Timestamp Lag (Critical!)
- [ ] 1m bar with timestamp 09:30:00 represents interval [09:30:00 - 09:30:59]
- [ ] Session time should be 09:31:00 when 09:30 bar is yielded (bar complete)
- [ ] When `session_time` = T, all bars with timestamp < T-1min should be in session_data
- [ ] Queue `oldest` timestamp + 1 minute should be approximately <= `session_time`

### 5.3 Queue-to-SessionData Flow
- [ ] When queue `oldest` timestamp is T, session_data should have bars up to approximately T-1min
- [ ] As queue drains, session_data bar count should increase
- [ ] Rate of queue drainage should approximately match rate of bar accumulation
- [ ] Total bars consumed from queue should equal final bar count in session_data

---

## 6. MULTI-SYMBOL SYNCHRONIZATION

### 6.1 Chronological Ordering
- [ ] All symbols must advance in session_time synchronously
- [ ] No symbol should be "ahead" of another in terms of session_time
- [ ] Queue oldest timestamps may differ between symbols (different data density)
- [ ] But all symbols should show same current session_time

### 6.2 Symbol Fairness
- [ ] Stream coordinator should interleave data from all symbols chronologically
- [ ] No symbol should monopolize consumption (starvation check)
- [ ] If Symbol A has older data than Symbol B, Symbol A's data should be consumed first

---

## 7. THREAD SYNCHRONIZATION

### 7.1 Data Consistency
- [ ] No race conditions: same row should show consistent state across all fields
- [ ] Bar counts and volume should never be inconsistent with each other
- [ ] Queue stats and session_data should be in sync (within 1-2 bars tolerance)

### 7.2 Update Atomicity
- [ ] All fields for a symbol should update together (no partial updates visible)
- [ ] If 1m_bars increases by N, volume should increase proportionally

---

## 8. DERIVED BAR COMPUTATION (Upkeep Thread)

### 8.1 Timeliness
- [ ] 5m bars should appear within 60 seconds (upkeep check interval) after enough 1m bars
- [ ] Once triggered, derived bars should compute for all intervals that have enough data
- [ ] Derived bars should not lag more than 2-3 minutes behind 1m bars

### 8.2 Correctness
- [ ] 5m bar count should match expected: `floor(1m_bars / 5)`
- [ ] 15m bar count should match expected: `floor(1m_bars / 15)` (if configured)
- [ ] Derived bars must never exceed theoretical maximum

---

## 9. SESSION LIFECYCLE

### 9.1 Startup Phase (First N rows)
- [ ] Session starts with `session_active = True`
- [ ] Initial queue sizes should be > 0 (data loaded)
- [ ] Initial bar counts should be 0 or very small
- [ ] Session time should start near market open (09:30:00 or shortly after)

### 9.2 Running Phase (Middle rows)
- [ ] Steady decrease in queue sizes
- [ ] Steady increase in bar counts
- [ ] Steady increase in volume
- [ ] Session time advancing smoothly

### 9.3 Completion Phase (Last N rows)
- [ ] Queue sizes should reach 0
- [ ] Bar counts should stabilize
- [ ] Session time should reach near market close (16:00:00)
- [ ] `session_ended` should eventually become `True`
- [ ] System state should eventually become `stopped`

---

## 10. PERFORMANCE EXPECTATIONS

### 10.1 Backtest Time Progression
- [ ] Session time must advance smoothly (no large gaps > 5 minutes)
- [ ] Session time should not stall (same value for > 10 consecutive rows)
- [ ] Backtest speed multiplier should not affect correctness (validation is speed-agnostic)

### 10.2 Data Flow Rate
- [ ] Bars should accumulate at ~1 bar per minute of backtest time (session_time)
- [ ] Queue drainage rate should match bar accumulation rate
- [ ] Rate is consistent regardless of replay speed (60x, 1x, etc.)

---

## 11. DATA COMPLETENESS (Perfect Data Assumption)

### 11.1 Session Data + Queue = Complete Data
- [ ] Last bar in session_data + queue oldest should be consecutive (no gap)
- [ ] If `last_bar_ts` = T and `queue_oldest` = T+1min, data is continuous
- [ ] If queue is empty, last_bar_ts should be near session_time (all data consumed)
- [ ] No overlaps: last_bar_ts < queue_oldest (no duplicate data)

### 11.2 Chronological Ordering Verification
- [ ] Pending items timestamps must be >= queue oldest (staging holds oldest from each queue)
- [ ] Pending items across symbols should be interleaved chronologically
- [ ] If pending_AAPL = 09:30 and pending_RIVN = 09:31, AAPL should be consumed first
- [ ] Pending item timestamp should match queue oldest (they are the same item)

### 11.3 bars_updated Flag Behavior
- [ ] Flag should be True when new bars added to session_data
- [ ] Flag should reset to False after derived bars computed
- [ ] If bars_updated = True for > 10 rows, derived bar computation may be stalled
- [ ] When bars increase, bars_updated should become True

### 11.4 Complete Day Coverage (for full session)
- [ ] First bar should be near market open (09:30:00 or shortly after)
- [ ] Last bar (in queue or session_data) should be near market close (15:59:00 or 16:00:00)
- [ ] Total bars (1m_bars + queue_size) should be ~390 bars for full trading day
- [ ] No large gaps (> 5 minutes) in bar sequence

---

## 12. ERROR CONDITIONS (Must NOT occur)

### 12.1 Data Anomalies
- [ ] NO negative queue sizes
- [ ] NO decreasing bar counts
- [ ] NO decreasing volumes
- [ ] NO high < low
- [ ] NO session_time going backwards
- [ ] NO first_bar_ts > last_bar_ts

### 12.2 Synchronization Issues
- [ ] NO queue oldest > session_time + 1min (data from future)
- [ ] NO stale queues (queue size > 0 but oldest not advancing for > 10 rows)
- [ ] NO gaps between last_bar_ts and queue_oldest (should be consecutive)
- [ ] NO pending item timestamp < queue oldest (staging should match queue front)

### 12.3 Thread Issues
- [ ] NO data inconsistencies within a row (e.g., bars increase but volume doesn't)
- [ ] NO race conditions visible (partial updates)
- [ ] NO bars_updated stuck at True for > 10 rows

---

## 13. DATABASE CROSS-VALIDATION

### 13.1 Source Data Verification
- [ ] Total bars (session_data + queue) should match bars available in database for session_date
- [ ] Final volume should match database total volume for the day
- [ ] High/Low should match database day high/low
- [ ] First bar timestamp should match database first bar for the day
- [ ] Last bar timestamp (in queue or session_data) should match database last bar

### 13.2 Queue Timestamp Verification
- [ ] Queue oldest/newest timestamps should correspond to actual bar timestamps in database
- [ ] When queue oldest = T, database should have bars starting at T
- [ ] Pending item timestamps should match actual bar timestamps in database

---

## 14. EDGE CASES

### 14.1 Partial Bars
- [ ] Last bar of session may be partial (not full minute)
- [ ] Derived bars may have one "incomplete" bar at end

### 14.2 Data Gaps (Should NOT occur with perfect data)
- [ ] With perfect data assumption, bar quality should be 100%
- [ ] Any gaps in 1m data should be flagged as ERROR (not expected)
- [ ] Missing bars should cause validation failure

### 14.3 Symbol-Specific Issues
- [ ] If one symbol has fewer bars (started late), gap should be explained
- [ ] Symbols with different data density should all reach completion
- [ ] All symbols should have same market hours coverage

---

## VALIDATION SCRIPT REQUIREMENTS

The validation script should:
1. Load CSV file
2. Iterate through rows sequentially
3. Check all invariants listed above
4. Report violations with row number and details
5. Generate summary statistics
6. Query database for cross-validation
7. Export detailed violation report

### Output Format:
```
PASSED: 156 / 160 checks
FAILED: 4 checks
  - Row 45: Queue oldest went backwards (AAPL: 09:45:00 -> 09:44:55)
  - Row 123: Derived bars lagging (5m: 15 bars, expected ~25 from 128 1m bars)
  - Row 234: Bar count decreased (RIVN: 250 -> 249)
  - Row 456: Session time stalled for 15 rows

WARNINGS: 2
  - Rows 100-110: Bar quality dropped to 94.5% (acceptable but noteworthy)
  - Row 300: Queue drainage slowed (took 10 rows to consume 1 bar)
```
