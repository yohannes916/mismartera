# Schwab OAuth Automation Guide

## Summary of Automation Options

### ✅ **Option 1: Auto-Start Server (IMPLEMENTED - Recommended)**

The CLI now automatically starts the OAuth callback server when you run `schwab auth-start`.

**Usage:**
```bash
./start_cli.sh
system@mismartera: schwab auth-start
# Server auto-starts, browser opens, authorize → DONE!
system@mismartera: schwab auth-status
```

**What happens:**
1. CLI checks if server is running
2. If not, starts it automatically in the background
3. Opens browser for authorization
4. Server catches callback and saves tokens
5. Authorization completes automatically!

**Pros:**
- ✅ Zero manual steps after browser authorization
- ✅ No need to manually start server
- ✅ Server stops when CLI exits
- ✅ Works immediately

**Cons:**
- Server only runs while CLI is active

---

### ⚙️ **Option 2: Systemd Service (Always Running)**

Run the OAuth server as a persistent background service.

**Setup (one-time):**
```bash
sudo nano /etc/systemd/system/mismartera-api.service
```

```ini
[Unit]
Description=MisMartera FastAPI OAuth Server
After=network.target

[Service]
Type=simple
User=yohannes
WorkingDirectory=/home/yohannes/mismartera/backend
Environment="PATH=/home/yohannes/mismartera/backend/.venv/bin"
ExecStart=/home/yohannes/mismartera/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable mismartera-api
sudo systemctl start mismartera-api
```

**Check status:**
```bash
sudo systemctl status mismartera-api
```

**Pros:**
- ✅ Server always ready for OAuth callbacks
- ✅ Survives reboots
- ✅ No manual server management

**Cons:**
- Uses resources continuously
- Requires sudo access

---

### 🔄 **Option 3: Token Refresh (Already Implemented)**

Tokens auto-refresh automatically - you don't need to re-authorize!

**How it works:**
- Access token: lasts 30 minutes, auto-refreshes
- Refresh token: lasts 7 days
- Every API call checks token expiration
- Auto-refreshes if < 5 minutes remain

**What you do:**
- Nothing! Just use the API
- Only re-authorize every 7 days (when refresh token expires)

**Check token status:**
```bash
system@mismartera: schwab auth-status
```

---

### 🤖 **Option 4: Startup Script**

Automate the entire flow with a script.

**Create script:**
```bash
nano ~/mismartera_schwab_auth.sh
chmod +x ~/mismartera_schwab_auth.sh
```

```bash
#!/bin/bash

cd /home/yohannes/mismartera/backend
source .venv/bin/activate

# Check if already authenticated
TOKEN_FILE="$HOME/.mismartera/schwab_tokens.json"
if [ -f "$TOKEN_FILE" ]; then
    echo "✓ Already authenticated"
    exit 0
fi

# Start CLI and initiate OAuth
./start_cli.sh <<EOF
schwab auth-start
exit
y
EOF

echo "Please complete authorization in browser"
echo "Then run: ./start_cli.sh"
echo "And check: schwab auth-status"
```

---

### 📅 **Option 5: Cron Job for Token Check**

Monitor token expiration and alert you.

**Add to crontab:**
```bash
crontab -e
```

```cron
# Check Schwab token status daily at 9 AM
0 9 * * * /home/yohannes/mismartera/backend/.venv/bin/python -c "from app.integrations.schwab_client import schwab_client; schwab_client._load_tokens(); import sys; sys.exit(0 if schwab_client.is_authenticated() else 1)" || echo "Schwab tokens expired - run: schwab auth-start" | mail -s "Schwab Auth Needed" yohannes@localhost
```

---

## 🎯 **Recommended Setup**

**For Development:**
- Use **Option 1** (Auto-Start Server) - already implemented!
- Just run `schwab auth-start` and authorize in browser

**For Production/Long-Running:**
- Use **Option 2** (Systemd Service) for persistent server
- Tokens auto-refresh via **Option 3**
- Set up **Option 5** (Cron) for monitoring

---

## 🚀 **Quick Start (Current Implementation)**

```bash
# First time setup
./start_cli.sh
system@mismartera: schwab auth-start
# Browser opens → Login → Authorize → DONE!

# Check status
system@mismartera: schwab auth-status

# Use Schwab API
system@mismartera: schwab connect
```

**That's it!** The server auto-starts, tokens auto-refresh, and you only need to re-authorize every 7 days.

---

## 📊 **Token Lifecycle**

```
Day 0:  schwab auth-start → Get tokens (access + refresh)
        ↓
Day 0-7: Access token auto-refreshes every 30 min
        ↓
Day 7:  Refresh token expires → Run schwab auth-start again
```

---

## 🔧 **Troubleshooting**

### Server won't auto-start
```bash
# Manually start server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Then in another terminal
./start_cli.sh
system@mismartera: schwab auth-start
```

### Tokens not saving
```bash
# Check file exists
ls -la ~/.mismartera/schwab_tokens.json

# Check permissions
chmod 600 ~/.mismartera/schwab_tokens.json

# Reload in CLI
system@mismartera: schwab auth-status  # Auto-reloads from disk
```

### Authorization fails
```bash
# Clear old tokens
system@mismartera: schwab auth-logout

# Start fresh
system@mismartera: schwab auth-start
```

---

## 🎉 **Summary**

With the current implementation (**Option 1**), authorization is **nearly automatic**:

1. Run: `schwab auth-start`
2. Authorize in browser (one click)
3. Done! (server handles everything else)

No manual code copying, no timing issues, no hassle! 

The only manual step is clicking "Allow" in the browser once every 7 days.
