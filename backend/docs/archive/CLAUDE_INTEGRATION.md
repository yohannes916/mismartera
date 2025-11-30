# Claude Opus 4.1 Integration

MisMartera integrates Claude Opus 4.1 for AI-powered trading analysis and assistance.

## 🔐 Secure Token Management

Your Claude API token is **safely stored** in the `.env` file and **never exposed** in responses:

```env
# In .env file
ANTHROPIC_API_KEY=sk-ant-api03-...your-key-here...
CLAUDE_MODEL=claude-opus-4-20250514
```

### Security Features

✅ **Environment variable** - Token stored in `.env`, never hardcoded  
✅ **Never exposed in API responses** - Only status is shown  
✅ **Requires authentication** - All Claude endpoints need login  
✅ **Token usage tracking** - Monitor API costs  
✅ **Server-side only** - Token never leaves the backend  

## 📱 CLI Commands

### Check Claude Configuration

```bash
trader@mismartera> claude status
```

Output:
```
┌──────────┬────────────────────────────┐
│ Property │ Value                      │
├──────────┼────────────────────────────┤
│ Status   │ ✓ Configured               │
│ Model    │ claude-opus-4-20250514     │
│ API Key  │ Set                        │
└──────────┴────────────────────────────┘
```

### Ask Claude a Question

```bash
trader@mismartera> ask What are the key indicators for day trading?
```

Claude will provide a detailed response with:
- Complete answer in a formatted panel
- Model and token count displayed
- Thinking spinner while processing

### Analyze a Stock

```bash
trader@mismartera> analyze AAPL
```

Claude will provide:
- Technical analysis
- Price action and trends
- Support/resistance levels
- Trading recommendation
- Entry/exit points
- Risk assessment

## 🌐 API Endpoints

All Claude endpoints require authentication (Bearer token).

### 1. Check Configuration

**GET /api/claude/config**

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/claude/config
```

Response:
```json
{
  "configured": true,
  "model": "claude-opus-4-20250514",
  "status": "ready"
}
```

Note: API key is **never** returned in responses.

### 2. Ask Claude a Question

**POST /api/claude/ask**

Request:
```json
{
  "prompt": "What are the best technical indicators for day trading?",
  "max_tokens": 2048,
  "temperature": 0.7
}
```

Response:
```json
{
  "response": "For day trading, the most effective technical indicators include...",
  "model": "claude-opus-4-20250514",
  "tokens_used": 523,
  "username": "trader"
}
```

Example:
```bash
TOKEN="your-session-token"

curl -X POST http://localhost:8000/api/claude/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain the RSI indicator for day trading",
    "max_tokens": 1024,
    "temperature": 0.5
  }'
```

### 3. Analyze a Stock

**POST /api/claude/analyze**

Request:
```json
{
  "symbol": "TSLA",
  "analysis_type": "technical",
  "market_data": {}
}
```

Analysis types:
- `technical` - Technical analysis with charts and indicators
- `fundamental` - Business and financial analysis
- `sentiment` - Market sentiment and news analysis
- `comprehensive` - All of the above

Response:
```json
{
  "symbol": "TSLA",
  "analysis_type": "technical",
  "analysis": "Tesla (TSLA) Technical Analysis:\n\n1. Price Action...",
  "model": "claude-opus-4-20250514",
  "tokens_used": 1247
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/claude/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "analysis_type": "technical"
  }'
```

## 💰 Cost Management

### Token Usage Tracking

Every response includes `tokens_used`:
- **Input tokens** - Your prompt
- **Output tokens** - Claude's response
- **Total** - Sum of both

### Estimating Costs

Claude Opus 4 pricing (as of 2024):
- Input: ~$15 per million tokens
- Output: ~$75 per million tokens

Example calculation:
- Ask command: ~500 tokens = ~$0.04
- Stock analysis: ~1,500 tokens = ~$0.12

### Best Practices

1. **Be specific** - Clearer prompts = better responses, fewer retries
2. **Set max_tokens** - Control response length and cost
3. **Monitor usage** - Track tokens in responses
4. **Temperature control** - Lower = more consistent, higher = more creative

## 🧪 Testing the Integration

### 1. Test CLI

```bash
./start_cli.sh

# Login
Username: trader
Password: demo123

# Check Claude status
trader@mismartera> claude status

# Ask a simple question
trader@mismartera> ask What is RSI?

# Analyze a stock
trader@mismartera> analyze NVDA
```

### 2. Test API

```bash
# Start API server
./start_api.sh

# In another terminal, login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"trader","password":"demo123"}' \
  | jq -r '.session_token')

# Check Claude config
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/claude/config

# Ask Claude
curl -X POST http://localhost:8000/api/claude/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is a good day trading strategy?"}' \
  | jq .

# Analyze stock
curl -X POST http://localhost:8000/api/claude/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"SPY","analysis_type":"technical"}' \
  | jq .
```

## 🎨 CLI Features

### Beautiful Formatting

Claude responses are displayed in rich, formatted panels:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Claude's Response                                   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│                                                      │
│ For day trading, the RSI (Relative Strength         │
│ Index) is one of the most reliable indicators...    │
│                                                      │
└──────────────────────────────────────────────────────┘

Model: claude-opus-4-20250514 | Tokens: 342
```

### Thinking Spinner

While Claude processes your request:
```
⠋ Thinking...
```

### Error Handling

Friendly error messages:
```
Claude API not configured
Set ANTHROPIC_API_KEY in .env file
```

## 🔧 Configuration

### Setting Up Your API Key

1. **Get an API key** from [Anthropic Console](https://console.anthropic.com/)

2. **Add to `.env` file**:
   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-...your-key...
   CLAUDE_MODEL=claude-opus-4-20250514
   ```

3. **Restart the application**:
   ```bash
   # CLI
   ./start_cli.sh
   
   # API
   ./start_api.sh
   ```

### Verifying Configuration

CLI:
```bash
trader@mismartera> claude status
```

API:
```bash
curl http://localhost:8000/api/claude/config
```

## 📊 Use Cases

### 1. Quick Market Insights

```bash
trader@mismartera> ask What's the market sentiment today?
```

### 2. Stock Analysis

```bash
trader@mismartera> analyze TSLA
```

### 3. Strategy Validation

```bash
trader@mismartera> ask Should I use a breakout or reversal strategy for AAPL?
```

### 4. Learning

```bash
trader@mismartera> ask Explain support and resistance levels
```

### 5. Risk Assessment

```bash
trader@mismartera> ask What are the risks of trading options?
```

## 🛡️ Security Checklist

- [x] API key stored in `.env` (never in code)
- [x] `.env` file in `.gitignore` (never committed)
- [x] Authentication required for all Claude endpoints
- [x] Token never exposed in API responses
- [x] HTTPS recommended for production
- [x] Token usage tracking enabled
- [x] Error messages don't leak sensitive data

## 🚨 Troubleshooting

### "Claude API not configured"

**Solution:** Add `ANTHROPIC_API_KEY` to your `.env` file and restart.

### "Invalid API key"

**Solution:** 
1. Verify key starts with `sk-ant-api03-`
2. Check for extra spaces or quotes
3. Generate a new key from console.anthropic.com

### "Rate limit exceeded"

**Solution:**
1. Wait a moment before retrying
2. Consider upgrading your Anthropic plan
3. Reduce request frequency

### High token usage

**Solution:**
1. Use more specific prompts
2. Reduce `max_tokens` parameter
3. Lower `temperature` for more focused responses

## 📚 Advanced Features (Already Implemented)

The Claude client (`app/integrations/claude_client.py`) includes advanced features:

1. **Stock Analysis** - Technical, fundamental, sentiment analysis
2. **Multi-Stock Scanning** - Scan multiple stocks for opportunities
3. **Strategy Validation** - Validate trading strategies
4. **Custom Prompts** - Build complex analysis prompts

These are available programmatically and can be exposed via CLI/API as needed.

## 🎯 Next Steps

1. **Test with your API key** - Add it to `.env` and try the commands
2. **Explore different prompts** - Ask various trading questions
3. **Analyze your watchlist** - Use the analyze command on stocks you follow
4. **Monitor token usage** - Track costs for budget planning
5. **Build custom workflows** - Combine Claude with other trading tools

---

**Remember:** Your API key is valuable. Keep it secure, never share it, and rotate it if compromised.
