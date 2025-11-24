# Schwab Developer Portal Setup Guide

## ⚠️ CRITICAL: You Need a Developer Account

**You cannot use Schwab's OAuth API with just a regular trading account.** You must complete the Developer Portal registration and app approval process first.

---

## Step 1: Register for Developer Portal

### 1.1 Create Developer Account
1. Go to: **https://developer.schwab.com/**
2. Click **"Sign Up"** or **"Get Started"**
3. Fill out the developer application:
   - Company/Individual name
   - Use case description
   - Contact information
4. **Submit and wait for approval** (can take 1-7 business days)

### 1.2 Wait for Approval Email
You'll receive an email when your developer account is approved.

---

## Step 2: Create an App

### 2.1 Login to Developer Portal
1. Go to: **https://developer.schwab.com/**
2. Login with your **developer credentials** (not trading account)

### 2.2 Create New App
1. Navigate to **"My Apps"** or **"Applications"**
2. Click **"Create New App"**
3. Fill out app details:
   - **App Name**: MisMartera Trading Bot (or your preference)
   - **App Description**: Automated trading system for personal use
   - **Callback URL**: `https://127.0.0.1:8000/callback`
   - **API Products**: Select "Trader API" or "Market Data"

### 2.3 Important Settings

#### Callback URL Options:
```
Option 1 (Automatic): https://127.0.0.1:8000/callback
Option 2 (Manual):    https://127.0.0.1
```

⚠️ **This must match EXACTLY** what you put in your `.env` file.

#### Environment:
- Start with **Sandbox** for testing (uses test data)
- Request **Production** promotion when ready (uses real data)

---

## Step 3: Get Your Credentials

### 3.1 View App Details
After creating the app, you'll see:
- **Client ID** (also called App Key)
- **Client Secret** (shown once, save it!)

### 3.2 Copy Credentials
```
Client ID:     [Copy this]
Client Secret: [Copy this - shown only once!]
```

⚠️ **Save Client Secret immediately!** If you lose it, you'll need to regenerate it.

### 3.3 Update Your .env File
```bash
cd /home/yohannes/mismartera/backend
nano .env
```

Update these lines:
```env
SCHWAB_APP_KEY=YOUR_CLIENT_ID_HERE
SCHWAB_APP_SECRET=YOUR_CLIENT_SECRET_HERE
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/callback
```

---

## Step 4: Test in Sandbox

### 4.1 Verify App Status
In Developer Portal:
- App Status should be: **"Active"** or **"Approved"**
- Environment: **"Sandbox"**

### 4.2 Test OAuth Flow
```bash
cd /home/yohannes/mismartera/backend
source .venv/bin/activate
python3 -m app.cli.main

# In CLI:
schwab auth-start
```

### 4.3 What Should Happen:
1. Browser opens to Schwab login
2. Login with your **TRADING account** (not developer account)
3. See authorization screen: "Allow MisMartera Trading Bot to access..."
4. Select accounts to authorize
5. Click "Allow" or "Authorize"
6. Get redirected to callback URL
7. Copy authorization code
8. Run: `schwab auth-callback YOUR_CODE`

---

## Step 5: Request Production Access

### 5.1 When Ready
After testing in Sandbox:
1. Go to Developer Portal
2. Find your app
3. Click **"Request Production Access"** or **"Promote to Production"**
4. Fill out production access form
5. **Wait for approval** (can take several days)

### 5.2 Production Requirements
Schwab may require:
- Explanation of app usage
- Security measures
- Compliance with terms of service
- Company documentation (if business)

---

## Troubleshooting

### Error: "Unable to complete your request"

**Causes:**
1. ❌ App not approved/active in Dev Portal
2. ❌ Using Sandbox credentials with production login
3. ❌ Invalid Client ID/Secret
4. ❌ Callback URL mismatch
5. ❌ Developer account not approved

**Solution:**
1. Login to https://developer.schwab.com/
2. Check app status
3. Verify credentials
4. Ensure callback URL matches
5. Test in correct environment (Sandbox vs Production)

### Error: "Invalid client credentials"

**Causes:**
- Wrong Client ID or Secret
- Credentials from wrong app
- Credentials expired/revoked

**Solution:**
- Regenerate credentials in Dev Portal
- Update `.env` file
- Restart CLI

### Error: "Redirect URI mismatch"

**Cause:**
`.env` callback URL doesn't match Dev Portal registration

**Solution:**
Either update `.env` OR update Dev Portal to match:
```env
# In .env
SCHWAB_CALLBACK_URL=https://127.0.0.1:8000/callback

# Must match exactly in Dev Portal
```

### Can't Find Developer Portal

**URLs:**
- Main site: https://developer.schwab.com/
- Login: https://developer.schwab.com/login
- Docs: https://developer.schwab.com/products/trader-api

---

## Current Status Check

### Do You Have These?

- [ ] Schwab Developer Portal account
- [ ] Approved developer account
- [ ] Created app in Dev Portal
- [ ] App status: Active/Approved
- [ ] Valid Client ID (App Key)
- [ ] Valid Client Secret
- [ ] Callback URL registered
- [ ] Credentials in `.env` file

### If You're Missing Any:

**You cannot proceed with OAuth until you complete the Developer Portal setup.**

The OAuth API is **not available** to regular Schwab trading accounts without going through the developer registration process.

---

## Timeline Expectations

| Step | Time Required |
|------|---------------|
| Developer account application | 1-7 business days |
| App creation | Immediate |
| Sandbox testing | Immediate |
| Production promotion request | Immediate |
| Production approval | 3-14 business days |

**Total**: 4-21 business days from start to production access

---

## Alternative: Use Different Broker

If Schwab's approval process is too slow, consider:

### Alpaca (Already Configured!)
```bash
# You already have Alpaca configured in .env
data api alpaca  # Switch to Alpaca for data
```

**Advantages:**
- ✅ Instant API access (no approval needed)
- ✅ Already working in your system
- ✅ Free real-time data
- ✅ Paper trading support

**Your .env already has:**
```env
ALPACA_API_KEY_ID=AKB7BUO3KJ3VQVQNTL2C4DVVTC
ALPACA_API_SECRET_KEY=CCDFRr8eeHPtB8qocKbhgxkdtrAfdk5Cn9pqNf7SHNzb
```

### Interactive Brokers
- Professional-grade API
- Low latency
- Complex approval process

### TD Ameritrade
- ⚠️ Now owned by Schwab
- API being migrated to Schwab platform
- Similar approval process

---

## Next Steps

1. **Check if you have developer account:**
   - Try logging into https://developer.schwab.com/
   - If you can't login → Need to register
   - If you can login → Check app status

2. **If no developer account:**
   - Register at https://developer.schwab.com/
   - Wait for approval
   - Create app
   - Get credentials

3. **If you have developer account:**
   - Check app status (must be Active/Approved)
   - Verify credentials match `.env`
   - Check callback URL matches
   - Test in correct environment

4. **While waiting for Schwab approval:**
   ```bash
   # Use Alpaca instead (works immediately)
   data api alpaca
   ```

---

## Questions to Answer

Before proceeding, please confirm:

1. **Do you have a Schwab Developer Portal account?**
   - Yes/No

2. **Have you created an app in the Dev Portal?**
   - Yes/No

3. **What is your app's current status?**
   - Pending/Active/Approved/Production

4. **Where did the credentials in your .env come from?**
   - My approved app
   - Found online/example
   - Don't remember
   - Don't have an app yet

5. **Are you trying to use Sandbox or Production?**
   - Sandbox (test data)
   - Production (real data)

Please answer these questions so we can determine the next steps!
