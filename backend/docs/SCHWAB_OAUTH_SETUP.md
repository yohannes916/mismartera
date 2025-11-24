# Schwab OAuth 2.0 Setup Guide

## Prerequisites

1. **Schwab Developer Account**: Register at https://developer.schwab.com/
2. **Create an App**: Get your App Key and App Secret
3. **Configure Callback URL**: Set to `https://127.0.0.1` in Schwab Developer Portal

## Environment Configuration

Add these to your `.env` file:

```env
SCHWAB_APP_KEY=your_app_key_here
SCHWAB_APP_SECRET=your_app_secret_here
SCHWAB_CALLBACK_URL=https://127.0.0.1
SCHWAB_API_BASE_URL=https://api.schwabapi.com/trader/v1
```

⚠️ **Important**: The callback URL in `.env` must match exactly what you registered in the Schwab Developer Portal.

## Authentication Flow

### 1. Start Authorization

```bash
cd /home/yohannes/mismartera/backend
source .venv/bin/activate
python -m app.cli.main

# In the CLI:
schwab auth-start
```

This will:
- Generate an authorization URL
- Attempt to open your browser automatically
- Display the URL if browser doesn't open

### 2. Authorize in Browser

1. **Login to Schwab** with your account credentials
2. **Authorize the application**
3. **You'll be redirected** to: `https://127.0.0.1?code=ABC123...`
4. **Browser will show "Connection Refused"** - This is normal!

### 3. Extract Authorization Code

From the URL in your browser address bar:
```
https://127.0.0.1?code=THIS_IS_YOUR_CODE&session=...
```

Copy everything after `code=` and before the next `&` (or end of URL).

### 4. Complete Authorization

```bash
# In the CLI:
schwab auth-callback YOUR_COPIED_CODE
```

### 5. Verify Authentication

```bash
schwab auth-status
```

You should see:
- ✓ Authenticated: Yes
- Access Token: (truncated)
- Token expiration info

## Troubleshooting

### "Failed to exchange authorization code"

**Causes:**
- Code has expired (codes are single-use and expire quickly)
- Code was copied incorrectly
- App key/secret mismatch
- Callback URL mismatch

**Solution:**
1. Start over with `schwab auth-start`
2. Complete the flow quickly (< 5 minutes)
3. Ensure you copy the entire code correctly

### "Callback URL mismatch"

**Solution:**
1. Go to Schwab Developer Portal
2. Check your app's callback URL setting
3. Update `.env` to match exactly (including https:// and port if any)
4. Restart CLI

### Token Expired

Tokens auto-refresh when they expire. If refresh fails:

```bash
schwab auth-logout
schwab auth-start
# Complete flow again
```

## Token Storage

Tokens are stored securely at:
```
~/.mismartera/schwab_tokens.json
```

File permissions are automatically set to `600` (owner read/write only).

## Security Notes

- ✓ Never commit `.env` to version control
- ✓ Tokens are encrypted at rest
- ✓ Refresh tokens valid for 7 days
- ✓ Access tokens valid for 30 minutes (auto-refreshed)
- ⚠️ Revoke access from Schwab Developer Portal if compromised
