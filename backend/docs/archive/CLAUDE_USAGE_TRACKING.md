# Claude API Usage Tracking

Monitor your Claude API token consumption and estimated costs in real-+time.

## 🔍 Features

- ✅ **Token tracking** - Input/output tokens counted separately
- ✅ **Cost estimation** - Real-time USD cost calculations
- ✅ **Per-user stats** - Track usage by username
- ✅ **Operations breakdown** - See which operations use most tokens
- ✅ **Usage history** - View recent API calls
- ✅ **Global stats** - Admin view of all usage (admin only)

## 💰 Pricing (Claude Opus 4)

- **Input tokens:** $15 per million tokens
- **Output tokens:** $75 per million tokens

Typical costs:
- Simple question: ~500 tokens = **~$0.04**
- Stock analysis: ~1,500 tokens = **~$0.12**
- Complex analysis: ~3,000 tokens = **~$0.25**

## 📱 CLI Commands

### View Your Usage

```bash
trader@mismartera> claude usage
```

Output:
```
┌─────────────────────┬─────────────────┐
│ Metric              │ Value           │
├─────────────────────┼─────────────────┤
│ Total Requests      │ 5               │
│ Total Tokens        │ 2,345           │
│ Input Tokens        │ 678             │
│ Output Tokens       │ 1,667           │
│ Estimated Cost      │ $0.1352 USD     │
└─────────────────────┴─────────────────┘

┌─────────────┬───────┬─────────┬──────────┐
│ Operation   │ Count │ Tokens  │ Cost     │
├─────────────┼───────┼─────────┼──────────┤
│ ask         │ 3     │ 1,234   │ $0.0678  │
│ analyze     │ 2     │ 1,111   │ $0.0674  │
└─────────────┴───────┴─────────┴──────────┘
```

### View Recent History

```bash
trader@mismartera> claude history
```

Output:
```
┌──────────┬───────────┬─────────┬──────────┐
│ Time     │ Operation │ Tokens  │ Cost     │
├──────────┼───────────┼─────────┼──────────┤
│ 18:13:07 │ ask       │ 523     │ $0.0456  │
│ 18:10:22 │ analyze   │ 1,245   │ $0.1023  │
│ 18:05:15 │ ask       │ 345     │ $0.0289  │
└──────────┴───────────┴─────────┴──────────┘
```

### Check Configuration

```bash
trader@mismartera> claude status
```

Shows if Claude API is configured and ready.

## 🌐 API Endpoints

All endpoints require authentication.

### 1. Get Your Usage

**GET /api/claude/usage**

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/claude/usage
```

Response:
```json
{
  "username": "trader",
  "total_requests": 5,
  "total_tokens": 2345,
  "total_input_tokens": 678,
  "total_output_tokens": 1667,
  "estimated_total_cost": 0.1352,
  "operations": {
    "ask": {
      "count": 3,
      "tokens": 1234,
      "cost": 0.0678
    },
    "analyze": {
      "count": 2,
      "tokens": 1111,
      "cost": 0.0674
    }
  },
  "first_request": "2025-11-17T18:10:00",
  "last_request": "2025-11-17T18:15:30"
}
```

### 2. Get Global Usage (Admin Only)

**GET /api/claude/usage/global**

```bash
curl -H "Authorization: Bearer <admin_token>" \
  http://localhost:8000/api/claude/usage/global
```

Response:
```json
{
  "total_requests": 25,
  "total_tokens": 12543,
  "total_input_tokens": 3456,
  "total_output_tokens": 9087,
  "estimated_total_cost": 0.7234,
  "unique_users": 3,
  "session_start": "2025-11-17T17:00:00",
  "uptime_hours": 2.5
}
```

### 3. Get Usage History

**GET /api/claude/usage/history?limit=10**

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/claude/usage/history?limit=10"
```

Response:
```json
{
  "history": [
    {
      "timestamp": "2025-11-17T18:13:07",
      "username": "trader",
      "operation": "ask",
      "input_tokens": 234,
      "output_tokens": 289,
      "total_tokens": 523,
      "model": "claude-opus-4-20250514",
      "estimated_cost": 0.0456
    }
  ],
  "count": 10
}
```

## 📊 Understanding the Metrics

### Total Tokens
Sum of all input + output tokens across all requests.

### Input Tokens
Tokens in your prompts/questions. Generally cheaper.

### Output Tokens
Tokens in Claude's responses. More expensive (5x input cost).

### Estimated Cost
Calculated based on current Claude Opus 4 pricing:
- Input: $15 / 1M tokens
- Output: $75 / 1M tokens

**Formula:**
```
cost = (input_tokens / 1,000,000 * 15) + (output_tokens / 1,000,000 * 75)
```

## 🎯 Cost Optimization Tips

### 1. Be Specific
```bash
# ❌ Vague (more tokens)
trader@mismartera> ask Tell me about trading

# ✅ Specific (fewer tokens)
trader@mismartera> ask What is the RSI indicator?
```

### 2. Control Response Length
When using API, set `max_tokens`:
```json
{
  "prompt": "Quick summary of AAPL",
  "max_tokens": 500
}
```

### 3. Lower Temperature
More focused responses use fewer tokens:
```json
{
  "temperature": 0.3  // More consistent, less creative
}
```

### 4. Batch Operations
If analyzing multiple stocks, consider if you really need AI for each one.

## 🔄 Usage Tracking Lifecycle

1. **User makes Claude request** (ask or analyze)
2. **Claude API processes** and returns response with token counts
3. **Tracker records:**
   - Username
   - Operation type
   - Input/output tokens
   - Timestamp
   - Estimated cost
4. **Stats updated** in real-+time
5. **User can view** via CLI or API

## 📈 Monitoring Best Practices

### Daily Check
```bash
trader@mismartera> claude usage
```

### Review History
```bash
trader@mismartera> claude history
```

### Set Budget Alerts
Track your `estimated_total_cost` and set personal limits:
- **Casual use:** ~$1-5/month
- **Active trading:** ~$10-50/month
- **Heavy research:** ~$50-200/month

### Admin Monitoring
Admins can view global stats:
```bash
admin@mismartera> claude usage  # Shows admin's usage
```

Via API:
```bash
GET /api/claude/usage/global  # Requires admin token
```

## 🛡️ Privacy & Security

- ✅ **User-specific tracking** - Each user only sees their own usage
- ✅ **Admin access** - Only admins can see global stats
- ✅ **No prompt storage** - Only metadata tracked (tokens, cost, timestamp)
- ✅ **Session-based** - Data resets on server restart (consider adding persistence)

## 🚨 Important Notes

### Estimates vs Actual
Costs shown are **estimates** based on published pricing. Actual billing from Anthropic may vary slightly due to:
- Pricing changes
- Volume discounts
- Special offers

### Token Counting
- Input tokens = Your prompt
- Output tokens = Claude's response
- Some operations show rough estimates (e.g., analyze splits tokens 1/3 input, 2/3 output)

### Data Persistence
Currently, usage data is **stored in memory** and will be **lost on server restart**.

To add persistence:
1. Store records in database
2. Load on startup
3. Save periodically

## 🧪 Testing Usage Tracking

### Test CLI
```bash
./start_cli.sh

# After login
trader@mismartera> ask Hello Claude
trader@mismartera> claude usage
trader@mismartera> analyze AAPL
trader@mismartera> claude history
```

### Test API
```bash
# Login and get token
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"trader","password":"demo123"}' \
  | jq -r '.session_token')

# Make some Claude requests
curl -X POST http://localhost:8000/api/claude/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello"}' | jq .

# Check usage
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/claude/usage | jq .

# Check history
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/claude/usage/history | jq .
```

## 🔧 Troubleshooting

### "No Claude API usage yet"
You haven't made any Claude requests yet. Try:
```bash
trader@mismartera> ask What is day trading?
```

### Usage stats seem wrong
- Token counts come directly from Claude API
- Costs calculated using standard pricing
- Some operations use rough estimates for input/output split

### Can't see global stats
Global stats require admin role:
- Login as admin user
- Or request admin access

## 📚 Related Documentation

- [CLAUDE_INTEGRATION.md](CLAUDE_INTEGRATION.md) - Claude setup and usage
- [AUTHENTICATION.md](AUTHENTICATION.md) - User authentication
- [API Documentation](http://localhost:8000/docs) - Full API reference

---

**Pro Tip:** Check your usage regularly to understand your patterns and optimize costs!
