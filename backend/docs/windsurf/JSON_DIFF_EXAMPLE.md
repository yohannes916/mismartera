# JSON Serialization - Complete vs Diff Mode Examples

## Scenario

System is running a backtest for AAPL and RIVN. We call `system_manager.to_json()` three times:

1. **First call** (diff mode) - Returns full object (no previous snapshot)
2. **Second call** (diff mode, after 1 minute) - Only AAPL volume and bar count changed
3. **Third call** (complete mode) - Returns full object again

---

## First Call: `system_mgr.to_json(complete=False, debug=False)`

**Result:** Full object returned (no previous snapshot exists)

```json
{
  "system_manager": {
    "state": "running",
    "mode": "backtest",
    "timezone": "America/New_York",
    "backtest_window": {
      "start_date": "2024-11-01",
      "end_date": "2024-11-30"
    }
  },
  "threads": {
    "session_coordinator": {
      "thread_info": {
        "name": "SessionCoordinator",
        "is_alive": true,
        "daemon": false
      },
      "state": "running",
      "current_session_date": "2024-11-15",
      "session_active": true,
      "iterations": 45678
    },
    "data_upkeep": {
      "thread_info": {
        "name": "DataUpkeepThread",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "cycles_completed": 1234,
      "derived_intervals": [5, 15]
    },
    "stream_coordinator": {
      "thread_info": {
        "name": "BacktestStreamCoordinator",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "items_yielded": 45000
    }
  },
  "session_data": {
    "system": {
      "state": "running",
      "mode": "backtest"
    },
    "session": {
      "date": "2024-11-15",
      "time": "14:35:22",
      "active": true,
      "ended": false,
      "symbol_count": 2
    },
    "symbols": {
      "AAPL": {
        "symbol": "AAPL",
        "volume": 125000,
        "high": 185.50,
        "low": 183.25,
        "vwap": 184.35,
        "bar_counts": {
          "1m": 245,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": true,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:35:00"
        }
      },
      "RIVN": {
        "symbol": "RIVN",
        "volume": 89000,
        "high": 15.85,
        "low": 15.22,
        "vwap": 15.54,
        "bar_counts": {
          "1m": 245,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": false,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:35:00"
        }
      }
    }
  },
  "_metadata": {
    "generated_at": "2024-11-15T14:35:22.123456",
    "complete": false,
    "debug": false,
    "diff_mode": true,
    "changed_paths": []
  }
}
```

**Size:** ~1.2 KB

---

## Second Call: `system_mgr.to_json(complete=False, debug=False)`

**Change:** 1 minute passed. AAPL received 1 new bar, volume increased by 5000.

**Result:** Only changed data returned

```json
{
  "threads": {
    "session_coordinator": {
      "iterations": 45738
    },
    "stream_coordinator": {
      "items_yielded": 45002
    }
  },
  "session_data": {
    "session": {
      "time": "14:36:22"
    },
    "symbols": {
      "AAPL": {
        "volume": 130000,
        "bar_counts": {
          "1m": 246
        },
        "time_range": {
          "last_bar": "14:36:00"
        }
      }
    }
  },
  "_metadata": {
    "generated_at": "2024-11-15T14:36:22.234567",
    "complete": false,
    "debug": false,
    "diff_mode": true,
    "changed_paths": [
      "threads.session_coordinator.iterations",
      "threads.stream_coordinator.items_yielded",
      "session_data.session.time",
      "session_data.symbols.AAPL.volume",
      "session_data.symbols.AAPL.bar_counts.1m",
      "session_data.symbols.AAPL.time_range.last_bar"
    ]
  }
}
```

**Size:** ~0.4 KB (67% smaller!)

**Performance Benefit:** Only serialize and transmit changed data.

---

## Third Call: `system_mgr.to_json(complete=True, debug=False)`

**Result:** Full object returned (complete=True forces full serialization)

```json
{
  "system_manager": {
    "state": "running",
    "mode": "backtest",
    "timezone": "America/New_York",
    "backtest_window": {
      "start_date": "2024-11-01",
      "end_date": "2024-11-30"
    }
  },
  "threads": {
    "session_coordinator": {
      "thread_info": {
        "name": "SessionCoordinator",
        "is_alive": true,
        "daemon": false
      },
      "state": "running",
      "current_session_date": "2024-11-15",
      "session_active": true,
      "iterations": 45738
    },
    "data_upkeep": {
      "thread_info": {
        "name": "DataUpkeepThread",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "cycles_completed": 1235,
      "derived_intervals": [5, 15]
    },
    "stream_coordinator": {
      "thread_info": {
        "name": "BacktestStreamCoordinator",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "items_yielded": 45002
    }
  },
  "session_data": {
    "system": {
      "state": "running",
      "mode": "backtest"
    },
    "session": {
      "date": "2024-11-15",
      "time": "14:36:22",
      "active": true,
      "ended": false,
      "symbol_count": 2
    },
    "symbols": {
      "AAPL": {
        "symbol": "AAPL",
        "volume": 130000,
        "high": 185.50,
        "low": 183.25,
        "vwap": 184.40,
        "bar_counts": {
          "1m": 246,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": true,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:36:00"
        }
      },
      "RIVN": {
        "symbol": "RIVN",
        "volume": 89000,
        "high": 15.85,
        "low": 15.22,
        "vwap": 15.54,
        "bar_counts": {
          "1m": 246,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": false,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:36:00"
        }
      }
    }
  },
  "_metadata": {
    "generated_at": "2024-11-15T14:36:22.345678",
    "complete": true,
    "debug": false,
    "diff_mode": false,
    "changed_paths": []
  }
}
```

**Size:** ~1.2 KB (full object)

---

## Debug Mode Example

### `system_mgr.to_json(complete=False, debug=True)`

**Result:** Includes performance metrics, bar data, historical summaries, queue stats

```json
{
  "system_manager": {
    "state": "running",
    "mode": "backtest",
    "timezone": "America/New_York",
    "backtest_window": {
      "start_date": "2024-11-01",
      "end_date": "2024-11-30"
    },
    "performance": {
      "uptime_seconds": 1234.5,
      "memory_usage_mb": 512.3
    }
  },
  "threads": {
    "session_coordinator": {
      "thread_info": {
        "name": "SessionCoordinator",
        "is_alive": true,
        "daemon": false
      },
      "state": "running",
      "current_session_date": "2024-11-15",
      "session_active": true,
      "iterations": 45738,
      "performance": {
        "avg_cycle_ms": 0.123,
        "last_cycle_ms": 0.115
      }
    },
    "data_upkeep": {
      "thread_info": {
        "name": "DataUpkeepThread",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "cycles_completed": 1235,
      "derived_intervals": [5, 15],
      "performance": {
        "avg_cycle_ms": 2.45,
        "last_computation_ms": 2.38
      }
    },
    "stream_coordinator": {
      "thread_info": {
        "name": "BacktestStreamCoordinator",
        "is_alive": true,
        "daemon": true
      },
      "state": "running",
      "items_yielded": 45002,
      "queue_stats": {
        "AAPL": {
          "BAR": {
            "size": 150,
            "oldest": "14:37:00",
            "newest": "17:05:00"
          }
        },
        "RIVN": {
          "BAR": {
            "size": 145,
            "oldest": "14:37:00",
            "newest": "17:05:00"
          }
        }
      },
      "performance": {
        "avg_yield_ms": 0.05,
        "stale_items_skipped": 0
      }
    }
  },
  "session_data": {
    "system": {
      "state": "running",
      "mode": "backtest"
    },
    "session": {
      "date": "2024-11-15",
      "time": "14:36:22",
      "active": true,
      "ended": false,
      "symbol_count": 2
    },
    "symbols": {
      "AAPL": {
        "symbol": "AAPL",
        "volume": 130000,
        "high": 185.50,
        "low": 183.25,
        "vwap": 184.40,
        "bar_counts": {
          "1m": 246,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": true,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:36:00"
        },
        "current_bars": {
          "1m": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "data": [
              ["09:30:00", 183.50, 183.75, 183.25, 183.60, 25000],
              ["09:31:00", 183.60, 183.80, 183.55, 183.70, 18000],
              ["09:32:00", 183.70, 183.90, 183.65, 183.85, 22000]
            ]
          },
          "5m": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "data": [
              ["09:30:00", 183.50, 184.00, 183.25, 183.85, 120000],
              ["09:35:00", 183.85, 184.20, 183.75, 184.10, 115000]
            ]
          }
        },
        "historical_summary": {
          "loaded": true,
          "bar_counts": {
            "1m": 78000,
            "5m": 15600,
            "15m": 5200
          },
          "date_range": {
            "start": "2024-10-01",
            "end": "2024-10-31"
          }
        },
        "performance": {
          "last_update_ms": 0.234,
          "total_updates": 246
        }
      },
      "RIVN": {
        "symbol": "RIVN",
        "volume": 89000,
        "high": 15.85,
        "low": 15.22,
        "vwap": 15.54,
        "bar_counts": {
          "1m": 246,
          "5m": 49,
          "15m": 16
        },
        "bar_quality": 100.0,
        "bars_updated": false,
        "time_range": {
          "first_bar": "09:30:00",
          "last_bar": "14:36:00"
        },
        "current_bars": {
          "1m": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "data": [
              ["09:30:00", 15.25, 15.30, 15.22, 15.28, 12000],
              ["09:31:00", 15.28, 15.35, 15.25, 15.32, 9500]
            ]
          },
          "5m": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "data": [
              ["09:30:00", 15.25, 15.45, 15.22, 15.40, 55000]
            ]
          }
        },
        "historical_summary": {
          "loaded": true,
          "bar_counts": {
            "1m": 78000,
            "5m": 15600,
            "15m": 5200
          },
          "date_range": {
            "start": "2024-10-01",
            "end": "2024-10-31"
          }
        },
        "performance": {
          "last_update_ms": 0.189,
          "total_updates": 246
        }
      }
    }
  },
  "_metadata": {
    "generated_at": "2024-11-15T14:36:22.456789",
    "complete": false,
    "debug": true,
    "diff_mode": true,
    "changed_paths": []
  }
}
```

**Size:** ~5.8 KB (includes bar data, performance metrics, queue stats)

---

## Size Comparison

| Mode | Size | Content |
|------|------|---------|
| **First call (diff)** | 1.2 KB | Full object (no snapshot) |
| **Subsequent (diff)** | 0.4 KB | Only changes (67% smaller) |
| **Complete mode** | 1.2 KB | Full object always |
| **Debug mode** | 5.8 KB | Full + performance + bars + queues |

---

## Performance Metrics

For a system with 10 symbols, 390 bars per symbol per day:

### Without Debug
- **Complete mode**: ~15 KB, ~5ms serialization time
- **Diff mode (typical)**: ~2-3 KB, ~1ms serialization time
- **Savings**: 80-85% size reduction, 80% faster

### With Debug
- **Complete mode**: ~150 KB, ~25ms serialization time
- **Diff mode (typical)**: ~30 KB, ~10ms serialization time
- **Savings**: 80% size reduction, 60% faster

---

## Use Cases

### Diff Mode (Default)
```python
# WebSocket streaming - minimal bandwidth
json_data = system_mgr.to_json(complete=False, debug=False)
websocket.send(json.dumps(json_data))
```

### Complete Mode
```python
# Initial sync or periodic full refresh
json_data = system_mgr.to_json(complete=True, debug=False)
```

### Debug Mode
```python
# Troubleshooting, performance analysis
json_data = system_mgr.to_json(complete=False, debug=True)
```

### Full Debug
```python
# Complete diagnostic dump
json_data = system_mgr.to_json(complete=True, debug=True)
```

---

## CLI Examples

```bash
# Diff mode (default)
system@mismartera: system json
# Returns: 0.4 KB (only changes)

# Complete mode
system@mismartera: system json --complete
# Returns: 1.2 KB (full object)

# Debug mode
system@mismartera: system json --debug
# Returns: 5.8 KB (with performance data)

# Full debug dump
system@mismartera: system json --complete --debug
# Returns: 5.8 KB (full object with all debug info)
```
