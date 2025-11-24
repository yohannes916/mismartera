# Authentication System

The MisMartera trading platform uses session-based authentication for both the CLI and API server.

## Overview

- **Session-based authentication** - Secure token-based sessions
- **8-hour timeout** - Sessions expire after 8 hours (trading day length)
- **Role-based access** - Admin and trader roles with different permissions
- **CLI & API integration** - Same authentication system for both interfaces

## Default Users

For development and testing, the following users are available:

### Admin User
- **Username:** `admin`
- **Password:** First 8 characters of `SECRET_KEY` in `.env`
- **Role:** `admin`
- **Access:** Full system access, admin commands

### Demo Trader
- **Username:** `trader`
- **Password:** `demo123`
- **Role:** `trader`
- **Access:** Trading operations, account info

## Interactive CLI

### Starting the CLI

```bash
./start_cli.sh
# or
make run-cli
```

### Login Flow

```
╔══════════════════════════════════════════════════╗
║                                                  ║
║                    MISMARTERA                    ║
║                                                  ║
║           Interactive Trading Terminal           ║
║                                                  ║
╚══════════════════════════════════════════════════╝

Please login to continue

Username: admin
Password: ********

✓ Welcome, admin!
Role: admin

admin@mismartera> 
```

### Available Commands

Once logged in, you have access to:

#### General Commands
```bash
help              # Show all available commands
status            # Show system status
clear             # Clear screen
whoami            # Show current user info
logout            # Logout and exit
exit/quit         # Exit application
```

#### Admin Commands (admin role only)
```bash
log-level <LEVEL>        # Change log level (DEBUG, INFO, WARNING, ERROR)
log-level-get            # Get current log level
sessions                 # List all active sessions
```

#### Account Commands
```bash
account info             # Display account information
account balance          # Display account balance
account positions        # Display current positions
```

#### Trading Commands
```bash
quote <SYMBOL>           # Get real-+time quote
buy <SYMBOL> <QTY>       # Place buy order
sell <SYMBOL> <QTY>      # Place sell order
orders                   # View order history
```

#### Market Data Commands
```bash
market status            # Check market hours
watchlist                # View watchlist
```

### CLI Features

- ✅ **Session management** - Login persists until logout or timeout
- ✅ **Command history** - Use arrow keys to navigate previous commands
- ✅ **Auto-completion** - Tab completion for commands (future)
- ✅ **Rich formatting** - Beautiful tables, colors, and panels
- ✅ **Error handling** - Graceful error messages
- ✅ **Ctrl+C protection** - Requires explicit logout/exit

### Example Session

```bash
$ ./start_cli.sh

# Login
Username: trader
Password: demo123

✓ Welcome, trader!
Role: trader

# Check status
trader@mismartera> status
┌─────────────────┬──────────────────────┐
│ Property        │ Value                │
├─────────────────┼──────────────────────┤
│ Application     │ MisMartera Backend   │
│ Version         │ 1.0.0                │
│ User            │ trader               │
│ Role            │ trader               │
│ Paper Trading   │ True                 │
│ Session Active  │ True                 │
└─────────────────┴──────────────────────┘

# Get quote
trader@mismartera> quote AAPL
Fetching quote for AAPL...
Market data not available (API not configured)

# Place order (paper trading)
trader@mismartera> buy AAPL 100
Placing BUY order: 100 shares of AAPL...
✓ Paper trading order placed: BUY 100 AAPL

# Logout
trader@mismartera> logout
Are you sure you want to logout? [y/n]: y

Goodbye, trader!
```

## API Server Authentication

### Starting the Server

```bash
./start_api.sh
# or
make run-api
```

The server runs continuously and requires authentication for all admin endpoints.

### Login Endpoint

**POST /auth/login**

Request:
```json
{
  "username": "admin",
  "password": "your_password"
}
```

Response:
```json
{
  "session_token": "abc123...",
  "username": "admin",
  "role": "admin",
  "message": "Login successful"
}
```

### Using the Session Token

Include the session token in the `Authorization` header for all authenticated requests:

```bash
curl -H "Authorization: Bearer <session_token>" \
     http://localhost:8000/api/admin/status
```

### Available Endpoints

#### Public Endpoints (No Auth Required)
- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /auth/login` - Login
- `GET /docs` - API documentation

#### Protected Endpoints (Auth Required)
- `GET /auth/me` - Get current user info
- `POST /auth/logout` - Logout
- `GET /auth/sessions` - List active sessions (admin only)
- `GET /api/admin/status` - System status (admin only)
- `GET /api/admin/log-level` - Get log level (admin only)
- `POST /api/admin/log-level` - Set log level (admin only)
- `POST /api/admin/shutdown` - Shutdown server (admin only)

### Example API Usage

```bash
# Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' \
  | jq -r '.session_token')

# Get current user info
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/auth/me

# Get system status (admin only)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/admin/status

# Change log level (admin only)
curl -X POST http://localhost:8000/api/admin/log-level \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"level":"DEBUG"}'

# Logout
curl -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

## Session Management

### Session Properties
- **Token:** Secure random 32-byte token (URL-safe base64)
- **Timeout:** 8 hours of inactivity
- **Storage:** In-memory (resets on server restart)
- **Renewal:** Last activity updated on each authenticated request

### Session Security
- ✅ Passwords hashed with bcrypt
- ✅ Secure token generation
- ✅ Automatic session cleanup
- ✅ Role-based access control
- ✅ Session validation on each request

## Adding Users

Currently, users are hardcoded in `app/services/auth_service.py`. To add database-backed users:

1. Create User model in `app/models/`
2. Update `authenticate_user()` in `auth_service.py`
3. Add user management endpoints
4. Implement password reset flow

## Security Best Practices

1. **Change default passwords** - Never use default credentials in production
2. **Use environment variables** - Store secrets in `.env` file
3. **Enable HTTPS** - Use SSL/TLS in production
4. **Session timeout** - Adjust timeout based on security requirements
5. **Password policy** - Implement strong password requirements
6. **Rate limiting** - Add rate limiting to login endpoint
7. **Audit logging** - Log all authentication events

## Troubleshooting

### Session Expired
If you see "Session expired", simply login again:
```
trader@mismartera> account balance
Session expired. Please login again.

Username: trader
Password: demo123
```

### Invalid Credentials
Check username and password. Remember:
- Admin password is first 8 characters of SECRET_KEY
- Demo trader password is `demo123`

### Permission Denied
Some commands require admin role:
```
trader@mismartera> sessions
Admin access required
```

### API 401 Unauthorized
Check that:
1. Session token is included in Authorization header
2. Token is still valid (not expired)
3. Token format is: `Bearer <token>`

## Future Enhancements

- [ ] Database-backed user storage
- [ ] Password reset functionality
- [ ] Two-factor authentication (2FA)
- [ ] OAuth integration (Google, GitHub)
- [ ] API key authentication
- [ ] Session persistence across restarts
- [ ] Web-based login interface
- [ ] Audit log for authentication events
