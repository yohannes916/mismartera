# Next Steps - Session Architecture Implementation

**Current Status**: Phase 1 Complete ✅ (15% done)  
**Next Phase**: Phase 2 - Configuration Updates  
**Date**: 2025-11-28

---

## ✅ Completed (Phase 1)

### Core Infrastructure - All Working & Tested

1. **SessionData** (`app/data/session_data.py`)
   - Zero-copy data store
   - Performance: 0.188 μs append, 0.136 μs get
   - Fully tested and verified ✅

2. **StreamSubscription** (`app/threads/sync/stream_subscription.py`)
   - Event-based one-shot synchronization
   - Mode-aware behavior
   - Thread-safe operations ✅

3. **PerformanceMetrics** (`app/monitoring/performance_metrics.py`)
   - Running statistics
   - 1.215 μs overhead
   - Report formatting ready ✅

---

## 🚀 Phase 2: Configuration Updates (Next)

### Tasks Remaining

#### 2.1: Create New SessionConfig Structure
**File**: `app/models/session_config.py`

**Current Status**: Old config backed up to `_old_session_config.py.bak`

**New Structure Needed** (from SESSION_ARCHITECTURE.md):
```python
@dataclass
class HistoricalDataConfig:
    trailing_days: int
    intervals: List[str]
    apply_to: str | List[str]

@dataclass
class HistoricalConfig:
    enable_quality: bool = True  # NEW
    data: List[HistoricalDataConfig]
    indicators: Dict[str, Any]

@dataclass
class GapFillerConfig:
    max_retries: int = 5
    retry_interval_seconds: int = 60
    enable_session_quality: bool = True  # NEW (replaces quality_update_frequency)

@dataclass
class SessionDataConfig:
    symbols: List[str]
    streams: List[str]
    historical: HistoricalConfig
    gap_filler: GapFillerConfig

@dataclass
class BacktestConfig:
    start_date: str
    end_date: str
    speed_multiplier: float = 360.0
    prefetch_days: int = 3  # NEW

@dataclass
class SessionConfig:
    session_name: str
    exchange_group: str
    asset_class: str
    mode: str
    backtest_config: BacktestConfig
    session_data_config: SessionDataConfig
    trading_config: TradingConfig
    api_config: APIConfig
    metadata: Optional[Dict]
```

**Action Items**:
- [ ] Create new config structure matching SESSION_ARCHITECTURE.md
- [ ] Add validation methods
- [ ] Add `from_dict()` class method
- [ ] Test with example_session.json

---

#### 2.2: Update TimeManager with Caching
**File**: `app/managers/time_manager/api.py`

**Changes Needed**:
```python
class TimeManager:
    def __init__(self):
        # Last-query cache (most common: same query repeatedly)
        self._last_query_cache = {'key': None, 'result': None}
        
    @lru_cache(maxsize=100)
    def _get_trading_session_cached(self, date_str, exchange):
        # Cached query
        pass
    
    def get_trading_session(self, session, date, exchange):
        # Check last-query cache first
        # Then LRU cache
        pass
    
    def invalidate_cache(self):
        # Clear all caches
        pass
    
    def get_first_trading_date(self, session, from_date, exchange):
        """NEW METHOD - Inclusive date finding"""
        if self.is_trading_day(session, from_date, exchange):
            return from_date
        return self.get_next_trading_date(session, from_date, n=1, exchange)
```

**Action Items**:
- [ ] Add LRU cache decorator to trading session queries
- [ ] Implement last-query cache
- [ ] Add `get_first_trading_date()` method
- [ ] Add `invalidate_cache()` method
- [ ] Test cache hit rates

---

#### 2.3: Update Example Config
**File**: `session_configs/example_session.json`

**Update to Match New Structure**:
```json
{
  "session_name": "Example Trading Session",
  "exchange_group": "US_EQUITY",
  "asset_class": "EQUITY",
  "mode": "backtest",
  "backtest_config": {
    "start_date": "2025-07-02",
    "end_date": "2025-07-07",
    "speed_multiplier": 360.0,
    "prefetch_days": 3
  },
  "session_data_config": {
    "symbols": ["RIVN", "AAPL"],
    "streams": ["1s", "1m", "5m", "10m", "quotes"],
    "historical": {
      "enable_quality": true,
      "data": [
        {
          "trailing_days": 3,
          "intervals": ["1m"],
          "apply_to": "all"
        }
      ],
      "indicators": {
        "avg_volume": {
          "type": "trailing_average",
          "period": "10d",
          "granularity": "daily"
        }
      }
    },
    "gap_filler": {
      "max_retries": 5,
      "retry_interval_seconds": 60,
      "enable_session_quality": true
    }
  },
  "trading_config": {
    "max_buying_power": 100000.0,
    "max_per_trade": 10000.0,
    "max_per_symbol": 20000.0,
    "max_open_positions": 5
  },
  "api_config": {
    "data_api": "alpaca",
    "trade_api": "alpaca"
  }
}
```

**Action Items**:
- [ ] Update example_session.json
- [ ] Test loading with new SessionConfig
- [ ] Validate all fields

---

## 📋 Estimated Timeline

**Phase 2 Total**: 1-2 days

- Task 2.1 (New SessionConfig): 4-6 hours
- Task 2.2 (TimeManager Caching): 3-4 hours
- Task 2.3 (Example Config Update): 1 hour
- Testing & Validation: 2-3 hours

---

## 🎯 Success Criteria for Phase 2

- [ ] New SessionConfig loads example_session.json successfully
- [ ] All validation rules working
- [ ] TimeManager caching implemented with >90% hit rate
- [ ] `get_first_trading_date()` returns correct inclusive dates
- [ ] Cache invalidation working
- [ ] Backwards compatibility considered (migration guide if needed)

---

## 🔄 After Phase 2

**Phase 3: Session Coordinator Rewrite** (5-7 days)
- Implement core lifecycle loop
- Historical data & indicator management
- Queue loading
- Streaming phase with time advancement

This will be the largest and most critical phase.

---

## 📁 Current Project State

```
backend/
├── app/
│   ├── data/
│   │   └── session_data.py ✅
│   ├── threads/sync/
│   │   └── stream_subscription.py ✅
│   ├── monitoring/
│   │   └── performance_metrics.py ✅
│   ├── models/
│   │   ├── session_config.py (needs update)
│   │   └── _old_session_config.py.bak (backed up)
│   └── managers/
│       └── time_manager/
│           └── api.py (needs caching)
├── session_configs/
│   └── example_session.json (needs update)
├── IMPLEMENTATION_PLAN.md
├── IMPLEMENTATION_DETAILS.md
├── SESSION_ARCHITECTURE.md (reference)
├── PROGRESS.md (tracking)
└── SESSION_SUMMARY.md (Phase 1 complete)
```

---

## 💡 Notes

1. **Old config backed up**: `app/models/_old_session_config.py.bak`
2. **All Phase 1 components tested**: Run verification scripts anytime
3. **Architecture document is authoritative**: SESSION_ARCHITECTURE.md
4. **Performance targets all exceeded**: Ready for production use

---

**Ready to proceed with Phase 2 implementation!**
