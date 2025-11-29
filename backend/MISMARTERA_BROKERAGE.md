# Mismartera Simulated Trading Brokerage

## Overview

**Mismartera** is an internal simulated trading brokerage for the ExecutionManager, providing full backtesting capabilities with realistic order execution, fees, and slippage.

## Features

✅ **Database-Backed State**
- Account balance and buying power
- Open and closed positions
- Order history (open, filled, cancelled)

✅ **Realistic Order Execution**
- Uses `session_data` for pricing (current 1m bar close)
- Immediate order fills (MARKET orders)
- Limit order logic (only fills if market price allows)
- Configurable slippage for market orders

✅ **Configurable Costs**
- Execution cost percentage (fees + commission + slippage)
- Separate market slippage percentage

✅ **Margin Support**
- Configurable buying power multiplier
- 1.0 = cash account (no margin)
- 2.0 = 2x leverage
- 4.0 = 4x leverage (day trading)

✅ **Full BrokerageInterface Implementation**
- Same interface as Alpaca/Schwab
- Seamless switching: `execution api mismartera`

---

## Configuration

### Settings (`.env` or `settings.py`)

```python
# Mismartera Simulated Trading Configuration
MISMARTERA_INITIAL_BALANCE = 100000.0              # Starting cash
MISMARTERA_BUYING_POWER_MULTIPLIER = 1.0           # Margin (1.0 = cash, 2.0 = 2x)
MISMARTERA_EXECUTION_COST_PCT = 0.001              # Total cost % (0.1%)
MISMARTERA_SLIPPAGE_PCT = 0.0001                   # Market slippage (0.01%)
```

### Defaults
- **Initial Balance:** $100,000
- **Buying Power Multiplier:** 1.0 (cash account)
- **Execution Cost:** 0.1% (10 basis points)
- **Slippage:** 0.01% (1 basis point)

---

## Usage

### Select Mismartera Brokerage

```bash
execution api mismartera
# Output: ✓ Execution API provider set to mismartera and connected
#         Simulated backtesting mode - orders will be executed using session_data pricing
```

### View Balance

```bash
execution balance
```

Output:
```
Account Balance (mismartera)
╭──────────────────────┬─────────────╮
│ Metric               │       Value │
├──────────────────────┼─────────────┤
│ Account ID           │     default │
│ Cash Balance         │ $100,000.00 │
│ Buying Power         │ $100,000.00 │
│ Total Value          │ $100,000.00 │
│ Mode                 │    BACKTEST │
╰──────────────────────┴─────────────╯
```

### Place Orders

```bash
# Market order (buy 100 shares of AAPL)
execution order AAPL 100 --side BUY

# Limit order (buy 50 shares of TSLA at $250)
execution order TSLA 50 --side BUY --type LIMIT --price 250.00

# Sell order
execution order AAPL 50 --side SELL
```

### View Positions

```bash
execution positions
```

### View Orders

```bash
execution orders
execution orders --status FILLED --days 30
```

---

## Order Execution Logic

### Market Orders

1. **Get Current Price** - Latest 1m bar close from `session_data`
2. **Apply Slippage:**
   - BUY: `execution_price = market_price * (1 + slippage_pct)`
   - SELL: `execution_price = market_price * (1 - slippage_pct)`
3. **Calculate Costs:**
   - `order_value = execution_price * quantity`
   - `execution_cost = order_value * execution_cost_pct`
   - `total_cost = order_value + execution_cost` (for buys)
4. **Validate Funds:**
   - BUY: Check `buying_power >= total_cost`
   - SELL: Check `position_quantity >= quantity`
5. **Execute:**
   - Update account balance
   - Update/create position
   - Create order record (status: FILLED)
   - Create execution record

### Limit Orders

1. **Get Current Price** - Latest 1m bar close from `session_data`
2. **Check Fill Conditions:**
   - BUY: Only fills if `market_price <= limit_price`
   - SELL: Only fills if `market_price >= limit_price`
3. **Execute at Market Price** (if conditions met)
4. **Reject** if conditions not met

### Order Costs

Total execution cost includes:
- **Regulatory Fees:** SEC, FINRA, TAF (~$0.02 per $1000)
- **Commission:** Broker fee (typically $0 for major brokers now)
- **Slippage:** Price movement during execution

**Default: 0.1% total** (conservative estimate)

Example:
- Order value: $10,000
- Execution cost: $10 (0.1%)
- Total: $10,010 (for buy)

---

## Position Management

### Opening Positions (BUY)

```python
# First buy: Creates new position
BUY 100 AAPL @ $150.00
→ Position: 100 shares @ $150.00 avg

# Average in: Updates position
BUY 50 AAPL @ $155.00
→ Position: 150 shares @ $151.67 avg
```

### Closing Positions (SELL)

```python
# Partial close
SELL 50 AAPL @ $160.00
→ Position: 100 shares @ $151.67 avg
→ Realized P&L: +$416.50

# Full close
SELL 100 AAPL @ $160.00
→ Position: CLOSED
→ Realized P&L: +$833.00
```

### Realized vs Unrealized P&L

- **Unrealized P&L:** `(current_price - avg_entry_price) * quantity`
- **Realized P&L:** Accumulated from closed/partial closes

---

## Database Schema

### Account Table
```sql
- account_id (PK)
- brokerage = "mismartera"
- mode = "backtest"
- cash_balance
- buying_power
- total_value
```

### Position Table
```sql
- account_id (FK)
- symbol
- quantity
- avg_entry_price
- current_price
- market_value
- unrealized_pnl
- realized_pnl
- opened_at
- closed_at (NULL for open positions)
```

### Order Table
```sql
- order_id = "MSM_XXXXXXXXXXXX"
- account_id
- symbol
- quantity
- side (BUY/SELL)
- order_type (MARKET/LIMIT)
- status (FILLED/CANCELLED)
- filled_quantity
- avg_fill_price
- created_at
- filled_at
```

---

## Examples

### Example 1: Simple Buy/Sell

```bash
# Start with $100,000
execution api mismartera
execution balance
# Cash: $100,000, Buying Power: $100,000

# Buy 100 AAPL @ $150.00
execution order AAPL 100 --side BUY
# Cost: $15,015 ($15,000 + $15 fee)
# Cash: $84,985, Buying Power: $84,985
# Position: 100 AAPL @ $150.00

# View positions
execution positions
# AAPL: 100 shares @ $150.00, Value: $15,000

# Sell all
execution order AAPL 100 --side SELL
# @ $155.00 (market moved up)
# Revenue: $15,485 ($15,500 - $15 fee)
# Cash: $100,470
# Realized P&L: +$470
```

### Example 2: With 2x Margin

Set in `.env`:
```
MISMARTERA_BUYING_POWER_MULTIPLIER=2.0
```

```bash
# Start with $100,000 cash, $200,000 buying power
execution balance
# Cash: $100,000, Buying Power: $200,000

# Buy $150,000 worth of stock (1.5x leverage)
execution order AAPL 1000 --side BUY
# @ $150.00 = $150,150 total
# Cash: -$50,150 (margin used!)
# Buying Power: $49,850
```

### Example 3: Failed Orders

```bash
# Insufficient funds
execution order AAPL 10000 --side BUY
# Error: Insufficient buying power

# Insufficient shares
execution order TSLA 100 --side SELL
# Error: Insufficient shares to sell

# Limit order rejected
execution order AAPL 100 --type LIMIT --price 100.00 --side BUY
# Current price: $150.00
# Error: Limit order cannot be filled
```

---

## Integration with Session Data

Mismartera uses `DataManager.get_latest_bar()` to get current pricing:

```python
# Get execution price
latest_bar = data_mgr.get_latest_bar(session, symbol, interval="1m")
execution_price = latest_bar.close

# Apply slippage for market orders
if order_type == MARKET:
    if side == BUY:
        execution_price *= (1 + slippage_pct)
    else:
        execution_price *= (1 - slippage_pct)
```

**Requirements:**
- `session_data` must have pricing for the symbol
- At least 1 bar must exist
- Backtests: Historical data from database
- Live mode: Real-time data from streams

---

## Advantages over Alpaca/Schwab

| Feature | Mismartera | Alpaca/Schwab |
|---------|-----------|---------------|
| **Setup** | None required | API keys, OAuth |
| **Cost** | Configurable simulation | Real costs |
| **Speed** | Instant execution | Network latency |
| **Control** | Full control over fills | Subject to market |
| **Testing** | Perfect for backtesting | Not ideal for testing |
| **Fees** | Configurable | Fixed/variable |
| **Leverage** | Configurable | Broker limits |

---

## Limitations

1. **No Real Market Impact** - Assumes infinite liquidity
2. **No Partial Fills** - Orders either fill completely or reject
3. **No Order Queuing** - Orders execute immediately
4. **Simplified Slippage** - Percentage-based, not market-depth aware
5. **No Extended Hours** - Only regular market hours
6. **No Options/Futures** - Equities only

---

## Best Practices

### 1. Realistic Configuration

```python
# Conservative (typical retail trader)
MISMARTERA_EXECUTION_COST_PCT = 0.001  # 0.1%
MISMARTERA_SLIPPAGE_PCT = 0.0001       # 0.01%
MISMARTERA_BUYING_POWER_MULTIPLIER = 1.0

# Aggressive (institutional/HFT)
MISMARTERA_EXECUTION_COST_PCT = 0.0001  # 0.01%
MISMARTERA_SLIPPAGE_PCT = 0.00001       # 0.001%
MISMARTERA_BUYING_POWER_MULTIPLIER = 4.0
```

### 2. Test Before Live Trading

```bash
# 1. Develop strategy with mismartera
execution api mismartera
# ... run backtests ...

# 2. Test with Alpaca paper trading
execution api alpaca
# ... paper trade ...

# 3. Go live with real money
# ... deploy to production ...
```

### 3. Monitor P&L

```bash
# Check realized P&L
execution positions  # Shows unrealized P&L
execution orders --status FILLED  # Shows execution prices

# Calculate total P&L
# Total = Realized P&L (from closed positions) + Unrealized P&L (from open positions)
```

---

## Troubleshooting

### "No market data available"
- Ensure `session_data` has bars for the symbol
- Run `data list` to see available symbols
- Import data with `data import-api 1m SYMBOL START END`

### "Insufficient buying power"
- Check balance: `execution balance`
- Reduce order size or increase `MISMARTERA_BUYING_POWER_MULTIPLIER`

### "Cannot determine execution price"
- Symbol not in session_data
- No bars available (check with `data latest-bar SYMBOL`)

---

## Future Enhancements

- [ ] Partial fills (split large orders)
- [ ] Order queuing (limit orders wait for fill)
- [ ] Market depth simulation
- [ ] Short selling support
- [ ] Options trading
- [ ] Futures trading
- [ ] Extended hours trading
- [ ] Advanced order types (OCO, bracket, trailing stop)

---

## Status

✅ **Production Ready** for backtesting and strategy development
🎉 **Fully Integrated** with ExecutionManager and CLI
📊 **Database-Backed** for full auditability
⚡ **High Performance** - instant execution, no network calls

Use `execution api mismartera` to get started!
