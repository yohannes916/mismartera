# Schwab OAuth Implementation Required

## Current Status

Schwab data provider integration is **framework-complete** but **OAuth authentication is not yet implemented**, which blocks actual data import functionality.

## What Works ✅

1. **Connection Testing**
   ```bash
   schwab connect
   # ✓ Schwab connection successful
   # Configuration validated
   ```

2. **Provider Selection**
   ```bash
   data api schwab
   # ✓ Schwab selected as data provider
   ```

3. **System Status**
   ```bash
   system status
   # Shows: Provider: schwab, Connected: Yes
   ```

## What Doesn't Work ⚠️

### Historical Data Import

```bash
system@mismartera: data import-api 1m AAPL 2025-11-18 2025-11-22

# Error:
✗ Schwab historical data import requires OAuth 2.0 authentication.
The OAuth flow (user authorization → token exchange) is not yet implemented.
To use Schwab data:
  1. Complete OAuth authorization flow
  2. Store access_token and refresh_token
  3. Use access_token in API requests
For now, please use Alpaca for historical data imports: 'data api alpaca'
```

### Why It Fails

**Current Implementation:**
```python
headers = {
    "Authorization": f"Bearer {settings.SCHWAB_APP_KEY}",  # ← WRONG
    "Content-Type": "application/json",
}
```

**Problem:** Using App Key directly as Bearer token

**What's Needed:** OAuth 2.0 access token obtained through proper authorization flow

## The OAuth 2.0 Problem

### Schwab's Authentication Model

Schwab uses **OAuth 2.0** (not simple API keys):

1. **User Authorization** - User must authorize app via Schwab's web interface
2. **Authorization Code** - Schwab redirects back with auth code
3. **Token Exchange** - Exchange auth code for access token
4. **Access Token** - Use this token in API requests
5. **Token Refresh** - Refresh token when it expires

### Alpaca vs Schwab

| Feature | Alpaca | Schwab |
|---------|--------|--------|
| Auth Type | API Keys | OAuth 2.0 |
| Complexity | Simple | Complex |
| User Interaction | None | Required |
| Token Management | None | Required |
| Works Now | ✅ Yes | ⚠️ No (needs OAuth) |

## Workaround: Use Alpaca

Until OAuth is implemented, use Alpaca for data imports:

```bash
# Switch to Alpaca
data api alpaca

# Import data (works immediately)
data import-api 1m AAPL 2024-11-18 2024-11-22
# ✓ Successfully imported 1045 bars
```

## What Needs to Be Implemented

### 1. OAuth Authorization Flow

**User Command:**
```bash
schwab auth-start
```

**What Should Happen:**
1. Generate authorization URL with state parameter
2. Open browser to Schwab authorization page
3. User logs in and authorizes app
4. Schwab redirects to callback URL with auth code
5. Backend receives callback and extracts code

### 2. Token Exchange

**After Receiving Auth Code:**
```python
async def exchange_authorization_code(auth_code: str):
    """Exchange auth code for access token"""
    url = f"{base_url}/v1/oauth/token"
    
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": settings.SCHWAB_CALLBACK_URL,
    }
    
    auth = (settings.SCHWAB_APP_KEY, settings.SCHWAB_APP_SECRET)
    
    response = await client.post(url, data=data, auth=auth)
    tokens = response.json()
    
    # Store tokens securely
    store_tokens(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_in=tokens["expires_in"]
    )
```

### 3. Token Storage

**Secure Storage Options:**
```python
# Option 1: Encrypted file
{
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": "2024-11-23T10:00:00Z"
}

# Option 2: Database
class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    provider = Column(String, primary_key=True)
    access_token = Column(String, encrypted=True)
    refresh_token = Column(String, encrypted=True)
    expires_at = Column(DateTime)

# Option 3: System keyring
import keyring
keyring.set_password("schwab", "access_token", token)
```

### 4. Token Refresh

**Before Each API Call:**
```python
async def get_valid_access_token():
    """Get valid access token, refreshing if needed"""
    tokens = load_tokens()
    
    if tokens["expires_at"] < datetime.now():
        # Token expired, refresh it
        tokens = await refresh_access_token(tokens["refresh_token"])
        store_tokens(tokens)
    
    return tokens["access_token"]
```

**Refresh Implementation:**
```python
async def refresh_access_token(refresh_token: str):
    """Refresh expired access token"""
    url = f"{base_url}/v1/oauth/token"
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    
    auth = (settings.SCHWAB_APP_KEY, settings.SCHWAB_APP_SECRET)
    
    response = await client.post(url, data=data, auth=auth)
    return response.json()
```

### 5. Updated Data Fetching

**With OAuth Token:**
```python
async def fetch_1m_bars(symbol, start, end):
    # Get valid token
    access_token = await get_valid_access_token()
    
    headers = {
        "Authorization": f"Bearer {access_token}",  # ← CORRECT
        "Content-Type": "application/json",
    }
    
    # Make API request
    response = await client.get(url, headers=headers, params=params)
    ...
```

## Implementation Checklist

### Phase 1: Basic OAuth Flow
- [ ] Add `schwab auth-start` command
- [ ] Generate authorization URL
- [ ] Open browser for user authorization
- [ ] Set up callback endpoint/handler
- [ ] Implement token exchange
- [ ] Store tokens securely (encrypted file or keyring)

### Phase 2: Token Management
- [ ] Load tokens on startup
- [ ] Check token expiration before API calls
- [ ] Implement token refresh
- [ ] Handle refresh failures gracefully

### Phase 3: API Integration
- [ ] Update `fetch_1m_bars()` to use access token
- [ ] Update `fetch_ticks()` to use access token
- [ ] Update `fetch_quotes()` to use access token
- [ ] Update `get_latest_quote()` to use access token

### Phase 4: Error Handling
- [ ] Handle token expiration mid-request
- [ ] Handle revoked tokens
- [ ] Handle network errors during refresh
- [ ] Clear error messages for users

### Phase 5: User Experience
- [ ] Add `schwab auth-status` command
- [ ] Add `schwab auth-logout` command
- [ ] Show token expiration in status
- [ ] Auto-refresh in background

## File Changes Needed

### 1. `app/integrations/schwab_client.py`
```python
class SchwabClient:
    def __init__(self):
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
    
    async def start_oauth_flow(self) -> str:
        """Generate and return authorization URL"""
        
    async def handle_callback(self, auth_code: str):
        """Exchange auth code for tokens"""
        
    async def get_valid_access_token(self) -> str:
        """Get valid token, refreshing if needed"""
        
    async def refresh_token_if_needed(self):
        """Refresh token if expired"""
```

### 2. `app/cli/interactive.py`
```python
# New commands
elif cmd == 'schwab':
    if subcmd == 'auth-start':
        await schwab_auth_start()
    elif subcmd == 'auth-status':
        await schwab_auth_status()
    elif subcmd == 'auth-logout':
        await schwab_auth_logout()
```

### 3. `app/managers/data_manager/integrations/schwab_data.py`
```python
async def fetch_1m_bars(symbol, start, end):
    # Get valid OAuth token
    from app.integrations.schwab_client import schwab_client
    access_token = await schwab_client.get_valid_access_token()
    
    # Use token in request
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
```

## Estimated Effort

| Task | Complexity | Estimated Time |
|------|-----------|----------------|
| OAuth flow & callback | Medium | 4-6 hours |
| Token storage | Low | 2-3 hours |
| Token refresh logic | Medium | 3-4 hours |
| API integration | Low | 1-2 hours |
| Error handling | Medium | 2-3 hours |
| Testing | Medium | 3-4 hours |
| **Total** | **Medium-High** | **15-22 hours** |

## Security Considerations

### Token Storage
- ✅ **Encrypt at rest** - Don't store tokens in plain text
- ✅ **File permissions** - Restrict access to token file (chmod 600)
- ✅ **Environment separation** - Different tokens for dev/prod
- ✅ **Rotation** - Support token rotation/re-authorization

### Token Transmission
- ✅ **HTTPS only** - Always use TLS for API calls
- ✅ **No logging** - Don't log access tokens
- ✅ **Memory cleanup** - Clear tokens from memory when done

### Error Handling
- ✅ **Graceful degradation** - Handle expired/revoked tokens
- ✅ **User notification** - Alert user when re-auth needed
- ✅ **No token leak** - Don't include tokens in error messages

## Testing Plan

### 1. OAuth Flow
- [ ] Test authorization URL generation
- [ ] Test callback handling
- [ ] Test token exchange success
- [ ] Test token exchange failures

### 2. Token Management
- [ ] Test token storage/loading
- [ ] Test token refresh before expiration
- [ ] Test token refresh after expiration
- [ ] Test refresh failure handling

### 3. API Calls
- [ ] Test data import with valid token
- [ ] Test data import with expired token (auto-refresh)
- [ ] Test data import with revoked token (error)

## Current Recommendation

**For Now:** Use Alpaca for data imports
```bash
data api alpaca
data import-api 1m AAPL 2024-11-18 2024-11-22
```

**Future:** Implement OAuth 2.0 for full Schwab integration

## Summary

✅ **Schwab infrastructure ready** - Provider selection, commands, framework  
⚠️ **OAuth not implemented** - Blocks actual data fetching  
🔧 **Clear error messages** - Users know what's missing  
📋 **Implementation plan ready** - Know exactly what to build  
🔄 **Workaround available** - Use Alpaca in the meantime  

Schwab is "integration complete" but "authentication incomplete" - the framework is there, we just need OAuth! 🔐
