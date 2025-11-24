# Schwab OAuth Login Refusal Debug Checklist

## Symptom
Browser opens, you try to login with your Schwab trading account, and get:
> "We are unable to complete your request. Please contact customer support for further assistance."

## Root Causes (ranked by likelihood)

### 1. ⚠️ App is in SANDBOX Mode (Most Common)

**Sandbox apps require TEST credentials, not your real account!**

**Check in Dev Portal:**
- App Environment: Sandbox vs Production
- If "Sandbox" → You CANNOT login with real account
- If "Production" → You can login with real account

**Solution for Sandbox:**
Schwab provides test credentials for sandbox apps. Check:
1. Dev Portal documentation
2. Your app's sandbox testing section
3. Email from Schwab with test credentials

**Solution for Production:**
Request production promotion in Dev Portal.

---

### 2. 🔐 App Not Linked to Your Trading Account

Even with a production app, you might need to:
1. Link your trading account to the app in Dev Portal
2. Explicitly authorize the app from your Schwab account settings

**Check:**
- Dev Portal → App Settings → Linked Accounts
- Schwab Trading Account → Settings → Third Party Apps

---

### 3. 📋 Missing API Product Subscription

Your app needs the correct API product enabled.

**Check in Dev Portal:**
- App Settings → API Products
- Should have: "Trader API - Individual" or similar
- Status: Active/Approved

**If missing:**
- Add API product subscription
- Wait for approval

---

### 4. ⏳ App Still Pending Approval

**Check in Dev Portal:**
- App Status: Must be "Active" or "Approved"
- NOT "Pending" or "Under Review"

**If pending:**
- Wait for Schwab approval
- Can take 3-14 business days

---

### 5. 🔑 Using Wrong Credentials

**Verify:**
```bash
# Your .env Client ID
SCHWAB_APP_KEY=oearAnlRstLXLDFfgXy3WIrkMlbAYNyRf58WdTxC7tu8LcVi

# Must EXACTLY match Dev Portal → Your App → Client ID
```

**Check:**
1. Login to Dev Portal
2. Open your app
3. Compare Client ID character-by-character
4. If different → Copy correct one to .env

---

### 6. 🚫 Account Type Mismatch

Some Schwab accounts can't use APIs:

**Incompatible account types:**
- Managed accounts
- Custodial accounts  
- Some retirement accounts (IRA, 401k)
- Accounts with restrictions

**Solution:**
Use a standard individual brokerage account.

---

## Diagnostic Steps

### Step 1: Confirm App Environment

Login to https://developer.schwab.com/ and check:

```
App Name: [Your App Name]
Environment: Sandbox or Production? ← KEY QUESTION
Status: Active/Approved/Pending?
API Products: What's listed?
Callback URL: https://127.0.0.1:8000/callback
```

### Step 2: Try Test Login (if Sandbox)

If app is in Sandbox:
1. Look for Schwab-provided test credentials
2. Use those instead of your real login
3. Check Dev Portal docs for sandbox login info

### Step 3: Request Production Access

If you need production:
1. Dev Portal → Your App → "Request Production Access"
2. Fill out form
3. Wait for approval (3-14 days)

### Step 4: Verify API Products

In Dev Portal:
1. Your App → API Products
2. Should see: "Trader API" or "Market Data"
3. Status: Active

If missing:
1. Subscribe to API Product
2. Wait for approval

---

## What to Check RIGHT NOW

Please answer these questions by checking your Dev Portal:

### Question 1: Environment
**Is your app in Sandbox or Production?**
- [ ] Sandbox (test mode)
- [ ] Production (live mode)

### Question 2: Status
**What is your app's status?**
- [ ] Active
- [ ] Approved  
- [ ] Pending Review
- [ ] Other: __________

### Question 3: API Products
**What API products are listed?**
- [ ] Trader API - Individual
- [ ] Market Data
- [ ] Accounts and Trading Production
- [ ] Other: __________
- [ ] None listed

### Question 4: Linked Accounts
**Are any accounts linked to your app?**
- [ ] Yes - Account(s) listed
- [ ] No accounts linked
- [ ] Don't see this section

### Question 5: Production Request
**Have you requested production access?**
- [ ] Yes - Still pending
- [ ] Yes - Approved
- [ ] No - Still in sandbox
- [ ] Don't know

---

## Quick Fixes by Scenario

### Scenario A: "My app is in Sandbox"
→ You MUST use test credentials (not your real account)
→ OR request production promotion

### Scenario B: "My app is Production but Pending"
→ Wait for approval
→ Use Alpaca in the meantime

### Scenario C: "My app is Production and Active"
→ Check linked accounts
→ Verify API products are active
→ Try logging into Schwab directly first to ensure account works

### Scenario D: "I don't see 'Production' option"
→ Some accounts/apps can't access production
→ Contact Schwab developer support

---

## Alternative: Use Alpaca (Works Immediately)

While debugging Schwab:

```bash
# Your Alpaca is already configured
cd /home/yohannes/mismartera/backend
source .venv/bin/activate
python3 -m app.cli.main

# In CLI:
data api alpaca
```

Benefits:
✅ No OAuth needed
✅ Works right now
✅ Free real-time data
✅ Paper trading ready

---

## Next Steps

1. **Check your app environment** (Sandbox vs Production)
2. **If Sandbox:** Find test credentials or request production
3. **If Production:** Verify API products and account linking
4. **Report back** with environment and status

The "unable to complete request" error is almost always:
- **Sandbox app + real credentials** (most common)
- **Missing API products**
- **Pending approval**
