# Log Deduplication Feature

## Overview

The log deduplication filter automatically suppresses repeated log messages from the same code location within a configurable time window. This prevents log spam from loops, frequently-called functions, and other repetitive code patterns.

## Problem Solved

**Before (Log Spam):**
```
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered AAPL -> NASDAQ
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered MSFT -> NASDAQ
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered GOOGL -> NASDAQ
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered AMZN -> NASDAQ
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered TSLA -> NASDAQ
```

**After (Deduplicated):**
```
2025-11-29 20:39:58.268 | DEBUG | app.managers.data_manager.symbol_exchange_mapping:register_symbol:24 - Registered AAPL -> NASDAQ
... (4 similar logs suppressed)
```

## How It Works

The filter tracks recent logs using three criteria:
1. **File path** - The source file that logged
2. **Line number** - The exact line in the source file
3. **Timestamp** - When the log occurred

If a new log matches a recent log on both file AND line number, and the time difference is below the threshold, it's suppressed.

### Algorithm

```python
For each new log:
    For each of the last N tracked logs:
        If (same_file AND same_line):
            If (time_since_last < threshold):
                SUPPRESS (return False)
    
    # Not a duplicate - allow and track
    Track this log
    ALLOW (return True)
```

## Configuration

Settings are now organized under the `LOGGER` section in `app/config/settings.py`:

```python
class LoggerConfig(BaseModel):
    # Deduplication filter settings
    filter_enabled: bool = True                      # Enable/disable deduplication filter
    filter_max_history: int = 5                      # Number of recent logs to track
    filter_time_threshold_seconds: float = 1.0       # Time window in seconds
```

See [LOGGER_CONFIGURATION.md](LOGGER_CONFIGURATION.md) for complete configuration documentation.

### Parameters

| Setting | Default | Description |
|---------|---------|-------------|
| `filter_enabled` | `True` | Master switch - set to `False` to disable deduplication entirely |
| `filter_max_history` | `5` | Number of recent log locations to remember (uses circular buffer) |
| `filter_time_threshold_seconds` | `1.0` | Time window in seconds - duplicates within this window are suppressed |

### Environment Variables

You can configure these via environment variables using the nested structure:
```bash
export LOGGER__FILTER_ENABLED=false                    # Disable deduplication
export LOGGER__FILTER_MAX_HISTORY=10                   # Track last 10 locations
export LOGGER__FILTER_TIME_THRESHOLD_SECONDS=2.0       # 2 second threshold
```

**Legacy format (deprecated but still works):**
```bash
export LOG_DEDUP_ENABLED=false          # Use LOGGER__FILTER_ENABLED instead
export LOG_DEDUP_HISTORY=10             # Use LOGGER__FILTER_MAX_HISTORY instead
export LOG_DEDUP_THRESHOLD=2.0          # Use LOGGER__FILTER_TIME_THRESHOLD_SECONDS instead
```

## Use Cases

### ✅ When It Helps

1. **Loop logging** - Registering multiple symbols in a loop
2. **Frequent function calls** - Health checks, heartbeats, polling
3. **Validation loops** - Checking multiple items with same validation
4. **Batch processing** - Processing items one by one with same log

### ❌ When to Disable

1. **Debugging loops** - Need to see every iteration
2. **Counting operations** - Each log represents a counted event
3. **Tracing execution flow** - Need complete execution trace
4. **Performance profiling** - Need precise timing of each call

To disable temporarily:
```bash
export LOGGER__FILTER_ENABLED=false
./start_cli.sh
```

## Examples

### Example 1: Symbol Registration Loop

**Code:**
```python
for symbol in ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]:
    logger.debug(f"Registered {symbol} -> NASDAQ")  # Same line in loop
```

**Without deduplication:**
```
DEBUG | register_symbols:24 - Registered AAPL -> NASDAQ
DEBUG | register_symbols:24 - Registered MSFT -> NASDAQ
DEBUG | register_symbols:24 - Registered GOOGL -> NASDAQ
DEBUG | register_symbols:24 - Registered AMZN -> NASDAQ
DEBUG | register_symbols:24 - Registered TSLA -> NASDAQ
```

**With deduplication (threshold=1.0s):**
```
DEBUG | register_symbols:24 - Registered AAPL -> NASDAQ
(4 similar logs suppressed)
```

### Example 2: Different Lines (Not Suppressed)

**Code:**
```python
logger.debug("Step 1 complete")  # Line 100
logger.debug("Step 2 complete")  # Line 101
logger.debug("Step 3 complete")  # Line 102
```

**Result:** All 3 logs appear (different line numbers)

### Example 3: Time Threshold

**Code:**
```python
logger.debug("Processing batch 1")  # Line 50
time.sleep(1.5)  # Wait 1.5 seconds
logger.debug("Processing batch 2")  # Line 50 (same line)
```

**Result:** Both logs appear (1.5s > 1.0s threshold)

### Example 4: Multiple Files (Not Suppressed)

Even if same line number:
- `file_a.py:24` - "Starting process"
- `file_b.py:24` - "Starting process"

**Result:** Both logs appear (different files)

## Performance

### Memory Usage
- Tracks last N log locations (default: 5)
- Each entry: ~100 bytes (file path string + line int + timestamp float)
- Total: ~500 bytes for default config
- Uses `collections.deque` with `maxlen` for automatic cleanup

### CPU Impact
- O(N) lookup per log message (N = history size, default 5)
- Negligible overhead for small N values
- Filter runs before formatting, so no wasted string formatting

### Thread Safety
- Filter instance is thread-safe via Loguru's internal mechanisms
- Each logger handler gets its own filter instance
- No additional locking needed

## Testing

Run the test script to see deduplication in action:

```bash
cd backend
python3 test_log_dedup.py
```

Then check the log file:
```bash
tail -f data/logs/app.log
```

## Implementation Details

### Filter Class

Located in `app/logger.py`:

```python
class LogDeduplicationFilter:
    """Filter to suppress duplicate log messages from the same location."""
    
    def __init__(self, max_history: int = 5, time_threshold_seconds: float = 1.0):
        self.max_history = max_history
        self.time_threshold = time_threshold_seconds
        self.recent_logs = deque(maxlen=max_history)
    
    def __call__(self, record: Dict[str, Any]) -> bool:
        """Return True to allow log, False to suppress."""
        # Check if matches recent log from same file:line within threshold
        # If yes: return False (suppress)
        # If no: return True (allow) and track this log
```

### Integration

The filter is applied to both handlers:

```python
# Console handler
logger.add(sys.stdout, ..., filter=self.dedup_filter)

# File handler
logger.add(log_file, ..., filter=self.dedup_filter)
```

## Troubleshooting

### Not Suppressing Logs

**Problem:** Logs still appearing that look like duplicates

**Checks:**
1. Verify `LOG_DEDUP_ENABLED=True` in settings
2. Check that logs are from EXACT same file:line (not just similar messages)
3. Check time between logs is < threshold (default 1.0s)
4. Verify not exceeding history size (default tracks last 5 locations)

### Suppressing Too Much

**Problem:** Important logs being suppressed

**Solutions:**
1. Reduce threshold: `LOG_DEDUP_THRESHOLD=0.5` (500ms)
2. Reduce history: `LOG_DEDUP_HISTORY=3`
3. Disable temporarily: `LOG_DEDUP_ENABLED=false`
4. Use different log levels (e.g., INFO vs DEBUG)
5. Move log to different line

### Checking Filter Status

Look for this in the log on startup:
```
Logger initialized with level: DEBUG
Log deduplication enabled: tracking last 5 logs, threshold 1.0s
```

If you don't see the second line, deduplication is disabled.

## Future Enhancements

Possible improvements:
1. **Per-level thresholds** - Different thresholds for DEBUG vs ERROR
2. **Summary logging** - Log "N similar messages suppressed" after threshold expires
3. **Pattern-based exemptions** - Never suppress certain log patterns
4. **Runtime control** - CLI command to enable/disable on the fly
5. **Statistics** - Track suppression rate, most-suppressed locations

## Related Files

- `app/logger.py` - Filter implementation and integration
- `app/config/settings.py` - Configuration settings
- `test_log_dedup.py` - Test script demonstrating feature
- `data/logs/app.log` - Where logs are written

---

**Status:** ✅ Implemented and active (default: enabled with 1s threshold, tracking last 5)
