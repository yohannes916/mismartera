# Scanner Framework - Visual Flow Diagrams

## Complete System Integration

```
┌──────────────────────────────────────────────────────────────────────┐
│                         SESSION CONFIG                                │
│  {                                                                    │
│    "symbols": ["AAPL", "MSFT"],  ← Static symbols                    │
│    "scanners": [{                ← Dynamic symbol sources             │
│      "name": "gap_scanner",                                           │
│      "pre_session": true,                                             │
│      "schedule": {...}                                                │
│    }]                                                                 │
│  }                                                                    │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     SESSION COORDINATOR                               │
│                                                                       │
│  1. Load config symbols        → register_symbol("AAPL")             │
│  2. Initialize ScannerManager  → load_scanners()                     │
│  3. Setup scanners             → setup_all()                         │
│  4. Pre-session scans          → execute_pre_session_scans()         │
│  5. Process scan results       → add_symbol_mid_session("TSLA")      │
│  6. Activate session           → session_data.activate_session()     │
│  7. Streaming loop             → execute_scheduled_scans()           │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        SESSION DATA                                   │
│                   (Ultimate Source of Truth)                          │
│                                                                       │
│  symbols: {                                                           │
│    "AAPL":  {bars, indicators, ...}  ← From config                   │
│    "MSFT":  {bars, indicators, ...}  ← From config                   │
│    "TSLA":  {bars, indicators, ...}  ← Added by scanner              │
│    "NVDA":  {bars, indicators, ...}  ← Added by scanner              │
│  }                                                                    │
│                                                                       │
│  Methods:                                                             │
│    add_indicator(symbol, config)     ← Scanner setup                 │
│    get_indicator(symbol, key)        ← Scanner scan                  │
│    get_latest_bar(symbol, interval)  ← Scanner scan                  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      ANALYSIS ENGINE                                  │
│                                                                       │
│  Can now trade:                                                       │
│    - Static symbols (AAPL, MSFT)     ← From config                   │
│    - Dynamic symbols (TSLA, NVDA)    ← From scanner                  │
│                                                                       │
│  Both types treated identically!                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Pre-Session Scan Flow (Backtest)

```
SESSION START
     │
     ├─────────────────────────────────────────────────────────┐
     │                                                          │
     ▼                                                          │
┌─────────────────┐                                            │
│ Load Config     │                                            │
│ Symbols         │                                            │
│ ["AAPL","MSFT"] │                                            │
└────────┬────────┘                                            │
         │                                                     │
         ▼                                                     │
┌─────────────────┐                                            │
│ Initialize      │                                            │
│ ScannerManager  │                                            │
└────────┬────────┘                                            │
         │                                                     │
         ▼                                                     │
┌─────────────────┐                                            │
│ Load Scanners   │                                            │
│ from Config     │                                            │
└────────┬────────┘                                            │
         │                                                     │
         ├─────────── gap_scanner                              │
         └─────────── momentum_scanner                         │
                    │                                          │
                    ▼                                          │
┌────────────────────────────────────────┐                     │
│ scanner.setup(context)                 │                     │
│                                        │                     │
│  for symbol in universe:               │                     │
│    session_data.add_indicator(         │◄────────────────────┤
│      symbol,                           │  Adds indicators     │
│      IndicatorConfig(...)              │  to session_data     │
│    )                                   │                     │
└───────────────────┬────────────────────┘                     │
                    │                                          │
                    ▼                                          │
┌────────────────────────────────────────┐                     │
│ scanner.scan(context)                  │                     │
│ (Pre-session scan)                     │                     │
│                                        │                     │
│  results = []                          │                     │
│  for symbol in universe:               │                     │
│    indicator = session_data.get(...)   │                     │
│    if meets_criteria(indicator):       │                     │
│      results.append(symbol)            │                     │
│                                        │                     │
│  return ScanResult(["TSLA", "NVDA"])   │                     │
└───────────────────┬────────────────────┘                     │
                    │                                          │
                    ▼                                          │
┌────────────────────────────────────────┐                     │
│ Process Results                        │                     │
│                                        │                     │
│  for symbol in results:                │                     │
│    add_symbol_mid_session(symbol)      │◄────────────────────┤
│      ├─ Load historical data           │  Adds symbols to     │
│      ├─ Register with session_data     │  session_data        │
│      └─ Register indicators            │                     │
└───────────────────┬────────────────────┘                     │
                    │                                          │
                    ▼                                          │
┌────────────────────────────────────────┐                     │
│ session_data now has:                  │                     │
│   ["AAPL", "MSFT", "TSLA", "NVDA"]     │◄─────────────────────┘
└───────────────────┬────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────┐
│ Activate Session                       │
│ Start Streaming                        │
└────────────────────────────────────────┘
```

---

## Mid-Session Scan Flow (Backtest - Blocking)

```
STREAMING LOOP (09:30 - 16:00)
     │
     ├── 09:30: Process bars
     ├── 09:31: Process bars
     ├── 09:32: Process bars
     ├── 09:33: Process bars
     ├── 09:34: Process bars
     │
     ├── 09:35: Check scanner schedules
     │          ↓
     │     ┌─────────────────────────────────┐
     │     │ gap_scanner scheduled for 09:35 │
     │     │ should_run() → TRUE             │
     │     └────────────┬────────────────────┘
     │                  │
     │                  ▼
     │     ┌─────────────────────────────────┐
     │     │ ⏸️  PAUSE STREAMING              │
     │     └────────────┬────────────────────┘
     │                  │
     │                  ▼
     │     ┌─────────────────────────────────┐
     │     │ Execute scanner.scan(context)   │
     │     │                                 │
     │     │ ⏱️  Takes 150ms                  │
     │     │                                 │
     │     │ Returns: ["AMD", "INTC"]        │
     │     └────────────┬────────────────────┘
     │                  │
     │                  ▼
     │     ┌─────────────────────────────────┐
     │     │ Process Results                 │
     │     │                                 │
     │     │ add_symbol_mid_session("AMD")   │
     │     │ add_symbol_mid_session("INTC")  │
     │     └────────────┬────────────────────┘
     │                  │
     │                  ▼
     │     ┌─────────────────────────────────┐
     │     │ ▶️  RESUME STREAMING             │
     │     └────────────┬────────────────────┘
     │                  │
     ├──────────────────┘
     │
     ├── 09:36: Process bars (now includes AMD, INTC)
     ├── 09:37: Process bars
     │
     └── ... continues
```

---

## Mid-Session Scan Flow (Live - Async)

```
STREAMING LOOP (Real-time)
     │
     ├── 09:35:00: Process bars
     │             ↓
     │        Check schedules
     │             ↓
     │        gap_scanner due
     │             ↓
     │   ┌──────────────────────────────┐
     │   │ Create async task            │
     │   │ asyncio.create_task(scan)    │
     │   └───────────┬──────────────────┘
     │               │                   
     │               ├─────────────┐     Background
     │               │             │     ──────────
     ├── 09:35:01: Process bars   │
     │                             ▼
     │                        ┌─────────────────┐
     ├── 09:35:02: Process   │ Scanner running │
     │            bars        │ in background   │
     │                        └────────┬────────┘
     │                                 │
     ├── 09:35:03: Process bars        │
     │                                 │
     │                                 ▼
     │                        ┌─────────────────┐
     ├── 09:35:04: Process   │ Scan completes  │
     │            bars        │ Results: [...]  │
     │                        └────────┬────────┘
     │                                 │
     │                                 ▼
     │                        ┌─────────────────┐
     │            ┌───────────┤ Add symbols     │
     │            │           │ (non-blocking)  │
     │            │           └─────────────────┘
     │            │
     ├── 09:35:05: Process bars (AMD, INTC now being loaded)
     │
     ├── 09:50:00: Check schedules
     │             ↓
     │        gap_scanner due again
     │             ↓
     │        Check if previous running
     │             ↓
     │        Previous done? YES → Run
     │                        NO  → Skip (log warning)
     │
     └── ... continues
```

---

## Scanner Setup Phase

```
┌────────────────────────────────────────────────────────────────┐
│                    scanner.setup(context)                       │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Load Universe                                                   │
│                                                                 │
│  universe_name = config.get("universe", "sp500")                │
│  universe = load_symbols_from_file(universe_name)               │
│                                                                 │
│  Result: ["AAPL", "MSFT", "TSLA", ..., "ZM"]  (500 symbols)    │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Register Indicators                                             │
│                                                                 │
│  for symbol in universe:                                        │
│    # Add indicators needed for scanning                         │
│    session_data.add_indicator(                                  │
│      symbol,                                                    │
│      IndicatorConfig(name="sma", period=20, interval="1d")      │
│    )                                                            │
│    session_data.add_indicator(                                  │
│      symbol,                                                    │
│      IndicatorConfig(name="volume_sma", period=10, interval="1d")│
│    )                                                            │
│                                                                 │
│  Result: 1000 indicators registered (500 symbols × 2)           │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│ session_data State After Setup                                  │
│                                                                 │
│  symbols: {                                                     │
│    "AAPL": {                                                    │
│      indicators: {                                              │
│        "sma_20_1d": {value: None, valid: False}  ← Registered   │
│        "volume_sma_10_1d": {value: None, valid: False}          │
│      }                                                          │
│    },                                                           │
│    "MSFT": {...},                                               │
│    ...                                                          │
│  }                                                              │
│                                                                 │
│  ⚠️  Indicators exist but NOT VALID (no historical data yet)    │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Historical Data Loading                                         │
│                                                                 │
│  SessionCoordinator sees indicators in session_data             │
│  Calls requirement_analyzer to determine needed bars            │
│  Loads historical data for all registered symbols               │
│                                                                 │
│  Result: Indicators become VALID                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Scanner Scan Phase

```
┌────────────────────────────────────────────────────────────────┐
│                    scanner.scan(context)                        │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Iterate Universe                                                │
│                                                                 │
│  results = []                                                   │
│  metadata = {}                                                  │
│                                                                 │
│  for symbol in self._universe:  # 500 symbols                   │
│    ─────────────────────────────────────────────────────┐      │
│                                                          │      │
└──────────────────────────────────────────────────────────┼──────┘
                                                           │
                                                           ▼
┌────────────────────────────────────────────────────────────────┐
│ Query session_data (Per Symbol)                                │
│                                                                 │
│  # Get current price                                            │
│  bar = context.session_data.get_latest_bar(symbol, "1m")       │
│  current_price = bar.close                                      │
│                                                                 │
│  # Get SMA indicator                                            │
│  sma_ind = context.session_data.get_indicator(symbol, "sma_20_1d")│
│  sma_value = sma_ind.current_value                              │
│                                                                 │
│  # Get volume indicator                                         │
│  vol_ind = context.session_data.get_indicator(symbol, "volume_sma_10_1d")│
│  avg_volume = vol_ind.current_value                             │
│  current_volume = bar.volume                                    │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Apply Criteria                                                  │
│                                                                 │
│  # Example: Gap scanner criteria                                │
│  gap_pct = ((current_price - sma_value) / sma_value) * 100     │
│  volume_ratio = current_volume / avg_volume                     │
│                                                                 │
│  if gap_pct >= 2.0 and volume_ratio >= 2.0:                    │
│    results.append(symbol)                                       │
│    metadata[symbol] = {                                         │
│      "gap_percent": gap_pct,                                    │
│      "volume_ratio": volume_ratio                               │
│    }                                                            │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│ Return Results                                                  │
│                                                                 │
│  return ScanResult(                                             │
│    symbols=["TSLA", "AMD", "NVDA"],  # 3 out of 500            │
│    metadata={                                                   │
│      "TSLA": {"gap_percent": 3.2, "volume_ratio": 2.5},        │
│      "AMD":  {"gap_percent": 2.8, "volume_ratio": 3.1},        │
│      "NVDA": {"gap_percent": 2.1, "volume_ratio": 2.2}         │
│    },                                                           │
│    execution_time_ms=150.0                                      │
│  )                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Comparison: Config Symbols vs Scanner Symbols

```
┌───────────────────────────────────────────────────────────────┐
│                     CONFIG SYMBOLS                             │
│                     (Static)                                   │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  session_config.json:                                          │
│    "symbols": ["AAPL", "MSFT"]                                 │
│                                                                │
│  When loaded:                                                  │
│    ✓ Immediately registered                                    │
│    ✓ Historical data loaded                                    │
│    ✓ All indicators calculated                                 │
│    ✓ Ready before session starts                               │
│                                                                │
│  Lifecycle:                                                    │
│    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                     │
│    Session Start ──────────────────► Session End               │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                    SCANNER SYMBOLS                             │
│                    (Dynamic)                                   │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  Scanner finds:                                                │
│    results: ["TSLA", "NVDA"]  (at 09:35)                       │
│                                                                │
│  When added:                                                   │
│    ✓ Registered mid-session                                    │
│    ✓ Historical data loaded                                    │
│    ✓ Indicators calculated                                     │
│    ✓ Ready after ~1-2 minutes                                  │
│                                                                │
│  Lifecycle:                                                    │
│    Session Start ────► Scanner ───► Add Symbol ───► End        │
│                        09:35         09:36                     │
│                                      ━━━━━━━━━━━━              │
│                                                                │
└───────────────────────────────────────────────────────────────┘

KEY INSIGHT: Both types treated identically after registration!
             AnalysisEngine sees no difference.
```

---

## Error Handling Flow

```
┌────────────────────────────────────────────────────────────────┐
│                  Scanner Execution                              │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Try: scanner.scan(context)                                      │
└─────────┬──────────────────────────────────────────────────────┘
          │
          ├─── SUCCESS ───────────────────────────┐
          │                                       │
          │                                       ▼
          │                          ┌──────────────────────────┐
          │                          │ Return ScanResult        │
          │                          │   symbols=[...]          │
          │                          │   error=None             │
          │                          └────────┬─────────────────┘
          │                                   │
          │                                   ▼
          │                          ┌──────────────────────────┐
          │                          │ Process Results          │
          │                          │ Add Symbols              │
          │                          └──────────────────────────┘
          │
          └─── EXCEPTION ─────────────────────────┐
                                                  │
                                                  ▼
                                     ┌──────────────────────────┐
                                     │ Catch Exception          │
                                     │ Log Error                │
                                     └────────┬─────────────────┘
                                              │
                                              ▼
                                     ┌──────────────────────────┐
                                     │ Return ScanResult        │
                                     │   symbols=[]             │
                                     │   error="Exception msg"  │
                                     └────────┬─────────────────┘
                                              │
                                              ▼
                                     ┌──────────────────────────┐
                                     │ Skip Processing          │
                                     │ Continue Streaming       │
                                     │ (System stays healthy)   │
                                     └──────────────────────────┘
```

---

## Summary Diagram: The Complete Picture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           THE BIG PICTURE                             │
└──────────────────────────────────────────────────────────────────────┘

           session_config.json              Scanner Modules
                   │                              │
                   │                              │
                   └───────────┬──────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ SessionCoordinator  │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
        ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │Config Symbols│ │Scanner Setup│ │Scanner Scans│
        │             │ │             │ │             │
        │["AAPL",     │ │Register     │ │Find matching│
        │ "MSFT"]     │ │indicators   │ │symbols      │
        └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
               │               │               │
               └───────────────┼───────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    session_data      │
                    │ (Ultimate Source)    │
                    │                      │
                    │ symbols: {           │
                    │   "AAPL":  {...}     │  ← From config
                    │   "MSFT":  {...}     │  ← From config
                    │   "TSLA":  {...}     │  ← From scanner
                    │   "NVDA":  {...}     │  ← From scanner
                    │ }                    │
                    └──────────┬───────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
        ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │DataProcessor│ │IndicatorMgr │ │AnalysisEngine│
        │             │ │             │ │             │
        │Calculates   │ │Updates      │ │Trades ALL   │
        │derived bars │ │indicators   │ │symbols      │
        └─────────────┘ └─────────────┘ └─────────────┘

ALL COMPONENTS QUERY session_data (Single Source of Truth)
```

This visual design makes the architecture clear and ready for implementation!
