# Alpaca Historical Data Download - Progress Logging

## Overview

Enhanced logging has been added to all Alpaca historical data download functions to provide real-time progress visibility during pagination. This helps identify when downloads are stuck or slow.

## Enhanced Functions

All four data fetching functions now include detailed progress logging:

1. **`fetch_1m_bars()`** - 1-minute bars
2. **`fetch_1d_bars()`** - Daily bars  
3. **`fetch_ticks()`** - Trade ticks
4. **`fetch_quotes()`** - Bid/ask quotes

## Log Output Format

### Before Each Request (Per Page)
```
[Alpaca] Requesting 1m bars for AAPL (page 3, total fetched: 20000) | Range: 2024-01-01T09:30:00Z to 2024-12-31T16:00:00Z
```

**Shows:**
- Data type (1m bars, daily bars, ticks, quotes)
- Symbol being fetched
- Current page number
- Cumulative total already fetched
- Date range being requested

### After Receiving Response
```
[Alpaca] Received 10000 bars in page 3 for AAPL
```

**Shows:**
- Number of items in current page
- Page number
- Symbol

### When More Data Available
```
[Alpaca] → More data available, fetching next page for AAPL...
```

**Indicates:**
- Pagination will continue
- Another request is about to be made

### When Pagination Complete
```
[Alpaca] ✓ Completed pagination for AAPL (total: 78390 bars from 8 pages)
```

**Shows:**
- Total items fetched
- Total pages processed
- Symbol

### Final Summary
```
[Alpaca] ✓ Final: Fetched 78390 1m bars from Alpaca for AAPL
```

## Example Complete Session Log

```log
2025-11-24 19:40:00.123 | INFO | [Alpaca] Requesting 1m bars for AAPL (page 1, total fetched: 0) | Range: 2024-11-01T09:30:00Z to 2024-11-30T16:00:00Z
2025-11-24 19:40:01.456 | INFO | [Alpaca] Received 10000 bars in page 1 for AAPL
2025-11-24 19:40:01.457 | INFO | [Alpaca] → More data available, fetching next page for AAPL...

2025-11-24 19:40:01.458 | INFO | [Alpaca] Requesting 1m bars for AAPL (page 2, total fetched: 10000) | Range: 2024-11-01T09:30:00Z to 2024-11-30T16:00:00Z
2025-11-24 19:40:02.789 | INFO | [Alpaca] Received 10000 bars in page 2 for AAPL
2025-11-24 19:40:02.790 | INFO | [Alpaca] → More data available, fetching next page for AAPL...

2025-11-24 19:40:02.791 | INFO | [Alpaca] Requesting 1m bars for AAPL (page 3, total fetched: 20000) | Range: 2024-11-01T09:30:00Z to 2024-11-30T16:00:00Z
2025-11-24 19:40:03.912 | INFO | [Alpaca] Received 1390 bars in page 3 for AAPL
2025-11-24 19:40:03.913 | INFO | [Alpaca] ✓ Completed pagination for AAPL (total: 21390 bars from 3 pages)

2025-11-24 19:40:03.914 | INFO | [Alpaca] ✓ Final: Fetched 21390 1m bars from Alpaca for AAPL
```

## Troubleshooting with Enhanced Logs

### Problem: Download Appears Stuck

**What to Look For:**
1. **Last log entry shows "Requesting..."** 
   - Network request is taking too long (>30s timeout)
   - Check network connectivity
   - Alpaca API may be slow/down

2. **Last log shows "Received X items"**
   - Processing items is slow (CPU bound)
   - Large dataset being parsed
   - This is normal, just slow

3. **Repeatedly showing page 1**
   - Pagination token not working
   - API error not being logged
   - Check error logs

### Problem: Slow Downloads

**Diagnosis from Logs:**
- **Small pages (< 1000 items):** Many requests needed, slow
- **Large gaps between logs:** Network latency high
- **Fast "Received" logs:** Network OK, processing fast

### Problem: Incomplete Data

**What Logs Show:**
- Final count vs expected count
- Number of pages processed
- Any warning messages about malformed data

## Benefits

✅ **Real-time visibility** - Know exactly what's happening  
✅ **Progress tracking** - See cumulative totals grow  
✅ **Stuck detection** - Quickly identify when downloads hang  
✅ **Performance insight** - Measure items/page and request timing  
✅ **Debug friendly** - Clear context for troubleshooting  

## Log Levels

All progress logs use **INFO** level:
- Visible in production
- Not overly verbose
- Filtered out if needed with log level configuration

## Configuration

No configuration needed - logging is automatic for all Alpaca downloads.

To view logs:
```bash
# Watch log file in real-time
tail -f data/logs/app.log | grep "\[Alpaca\]"

# Filter for specific symbol
tail -f data/logs/app.log | grep "\[Alpaca\]" | grep "AAPL"

# Filter for specific data type
tail -f data/logs/app.log | grep "\[Alpaca\]" | grep "1m bars"
```

## Performance Metrics

With enhanced logging, you can calculate:

**Average items per page:**
```
Total items / Total pages
Example: 78390 / 8 = 9,798 items/page
```

**Average request time:**
```
Total time / Total requests
Monitor timestamps between "Requesting" logs
```

**Data rate:**
```
Total items / Total time
Example: 21390 bars / 3.8 seconds = 5,629 bars/sec
```

## Related Files

- `/app/managers/data_manager/integrations/alpaca_data.py` - All fetch functions
- `/app/logger.py` - Logger configuration
- `/data/logs/app.log` - Log output location

---

**Status:** ✅ Implemented for all Alpaca data download functions

Use `data import-api` commands to see the enhanced logging in action!
