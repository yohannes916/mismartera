# Database-Backed User Storage

MisMartera now uses SQLite database for persistent user storage with full user management capabilities.

## 🎉 Features

- ✅ **Persistent user storage** - Users saved to SQLite database
- ✅ **User registration** - Create new user accounts via API
- ✅ **Password management** - Change passwords securely
- ✅ **Role-based access** - Admin and trader roles
- ✅ **User activation/deactivation** - Soft delete users
- ✅ **Secure password hashing** - bcrypt encryption
- ✅ **Last login tracking** - Track user activity
- ✅ **Fallback support** - Hardcoded demo users still work

## 📦 Database Schema

### User Model

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'trader' NOT NULL,  -- 'admin' or 'trader'
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    last_login TIMESTAMP
);
```

## 🚀 Quick Start

### 1. Initialize Database

```bash
cd backend

# Create database tables
python run_cli.py init-db

# Create default users
python -m app.scripts.init_users
```

This creates:
- **Admin user**: `admin` / (first 16 chars of SECRET_KEY)
- **Demo trader**: `trader` / `demo123`

### 2. Test Login

```bash
./start_cli.sh

# Login with database user
Username: trader
Password: demo123
```

## 📱 API Endpoints

All user management endpoints are available at `/api/users/*`

### Public Endpoints

#### Register New User

**POST /api/users/register**

```bash
curl -X POST http://localhost:8000/api/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "secure_password_123",
    "role": "trader"
  }'
```

Response:
```json
{
  "id": 3,
  "username": "johndoe",
  "email": "john@example.com",
  "role": "trader",
  "is_active": true,
  "created_at": "2025-11-17T20:30:00",
  "last_login": null
}
```

### Authenticated Endpoints

#### Get Current User Info

**GET /api/users/me**

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/users/me
```

#### Change Password

**POST /api/users/change-password**

```bash
curl -X POST http://localhost:8000/api/users/change-password \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "old_password",
    "new_password": "new_secure_password_456"
  }'
```

### Admin-Only Endpoints

#### List All Users

**GET /api/users/**

```bash
curl -H "Authorization: Bearer <admin_token>" \
  http://localhost:8000/api/users/
```

#### Get User by Username

**GET /api/users/{username}**

```bash
curl -H "Authorization: Bearer <admin_token>" \
  http://localhost:8000/api/users/trader
```

#### Update User

**PUT /api/users/{username}**

```bash
curl -X PUT http://localhost:8000/api/users/johndoe \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newemail@example.com",
    "role": "admin",
    "is_active": true
  }'
```

#### Deactivate User

**POST /api/users/{username}/deactivate**

```bash
curl -X POST http://localhost:8000/api/users/johndoe/deactivate \
  -H "Authorization: Bearer <admin_token>"
```

#### Activate User

**POST /api/users/{username}/activate**

```bash
curl -X POST http://localhost:8000/api/users/johndoe/activate \
  -H "Authorization: Bearer <admin_token>"
```

#### Delete User

**DELETE /api/users/{username}**

```bash
curl -X DELETE http://localhost:8000/api/users/johndoe \
  -H "Authorization: Bearer <admin_token>"
```

## 🔄 Migration from Hardcoded Users

### Before (Hardcoded)
```python
# Users defined in code
if username == "admin" and password == settings.SECRET_KEY[:8]:
    # Hardcoded authentication
```

### After (Database)
```python
# Users in database
user = await UserRepository.get_user_by_username(session, username)
if user and auth_service.verify_password(password, user.password_hash):
    # Database authentication
```

### Fallback Behavior

The system still supports hardcoded users as fallback:
- If database query fails → Uses hardcoded users
- If user not in database → Tries hardcoded users
- Ensures system works even without database

## 🛠️ User Management Workflow

### Creating Users

#### Via API (Recommended)
```bash
# Register new user
POST /api/users/register
{
  "username": "newuser",
  "email": "user@example.com",
  "password": "secure_password",
  "role": "trader"
}
```

#### Via Script
```python
# In Python script
from app.repositories.user_repository import UserRepository
from app.services.auth_service import auth_service

password_hash = auth_service.hash_password("password123")
user = await UserRepository.create_user(
    session=session,
    username="newuser",
    email="user@example.com",
    password_hash=password_hash,
    role="trader"
)
```

### Modifying Users

#### Change Password (Self)
```bash
POST /api/users/change-password
{
  "current_password": "old_password",
  "new_password": "new_password"
}
```

#### Update User (Admin)
```bash
PUT /api/users/{username}
{
  "email": "newemail@example.com",
  "role": "admin"
}
```

### Deleting Users

#### Soft Delete (Deactivate)
```bash
POST /api/users/{username}/deactivate
```
User can be reactivated later.

#### Hard Delete
```bash
DELETE /api/users/{username}
```
User permanently removed from database.

## 🔐 Security Features

### Password Hashing
- **Algorithm**: bcrypt
- **Automatic salting**: Each password gets unique salt
- **Cost factor**: Configurable (default: 12 rounds)

### Session Management
- **Tokens**: Cryptographically secure random tokens
- **Timeout**: 8-hour sessions (trading day)
- **Validation**: Every request validates session

### Role-Based Access
- **Admin**: Full access to all endpoints
- **Trader**: Limited to own data and trading functions

## 📊 Database Location

```
backend/
└── data/
    └── trading_app.db    # SQLite database file
```

**Backup regularly!** This file contains all user data.

## 🧪 Testing

### Test User Registration

```bash
# Start API server
./start_api.sh

# In another terminal
curl -X POST http://localhost:8000/api/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "test1234567890",
    "role": "trader"
  }' | jq .
```

### Test Login with New User

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test1234567890"
  }' | jq .
```

### Test CLI Login

```bash
./start_cli.sh

Username: testuser
Password: test1234567890
```

## 🔧 Troubleshooting

### "User not found" after creating user

**Check database:**
```bash
sqlite3 data/trading_app.db "SELECT * FROM users;"
```

### Reset database

```bash
# Delete database
rm data/trading_app.db

# Reinitialize
python run_cli.py init-db
python -m app.scripts.init_users
```

### Hardcoded users still working

This is intentional! Hardcoded users serve as fallback.
To disable, remove fallback code in `auth_service.py`.

### Password requirements

- Minimum 8 characters
- Mix of letters, numbers recommended
- Special characters allowed

## 📈 Advanced Usage

### Custom User Attributes

Add fields to User model:
```python
class User(Base):
    # Existing fields...
    phone = Column(String(20))
    timezone = Column(String(50))
    trading_limit = Column(Float, default=10000.0)
```

### Email Verification

Add email verification:
```python
email_verified = Column(Boolean, default=False)
verification_token = Column(String(100))
```

### Password Reset

Implement password reset flow:
1. Generate reset token
2. Send email with link
3. Verify token and update password

## 📚 Related Documentation

- [AUTHENTICATION.md](AUTHENTICATION.md) - Session management
- [API Documentation](http://localhost:8000/docs) - Full API reference
- [User Model](app/models/user.py) - Database schema
- [User Repository](app/repositories/user_repository.py) - DB operations

## 🎯 Next Steps

- [x] Database-backed user storage
- [x] User registration API
- [x] Password management
- [x] Role-based access control
- [ ] Email verification
- [ ] Password reset via email
- [ ] Two-factor authentication (2FA)
- [ ] OAuth integration (Google, GitHub)
- [ ] User profiles with preferences
- [ ] Audit logging

---

**Pro Tip:** Always initialize default users after creating the database:
```bash
python run_cli.py init-db
python -m app.scripts.init_users
```
