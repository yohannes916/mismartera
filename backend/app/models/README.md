# Database Architecture & Models - Complete Documentation

**Complete reference for database schema, models, and API**

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Database Setup](#database-setup)
4. [Models Reference](#models-reference)
5. [Session Management](#session-management)
6. [User Authentication](#user-authentication)
7. [Migration Guide](#migration-guide)
8. [Best Practices](#best-practices)

---

## Overview

The system uses SQLAlchemy ORM with SQLite for persistence. All models inherit from a common `Base` class and support both synchronous operations.

### Key Components

- **Database Engine**: SQLAlchemy synchronous engine (thread-safe)
- **Session Management**: Context-managed sessions with automatic commit/rollback
- **Models**: Declarative ORM models with relationships
- **Migrations**: Manual migrations via Python scripts

---

## Architecture

### Database Stack

```
Application Code
    ↓
SQLAlchemy ORM (Synchronous)
    ↓
SQLite Database (File-based)
    ↓
data/mismartera.db
```

### Design Principles

1. **Synchronous Operations**: All DB operations are synchronous (no async/await)
2. **Thread-Safe**: Engine connection pooling ensures thread safety
3. **Session Per Operation**: Each operation gets its own session
4. **Automatic Cleanup**: Context managers handle commit/rollback/close
5. **Type Safety**: SQLAlchemy models provide type checking

---

## Database Setup

### Configuration

**Location:** `app/models/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Database URL from settings
db_url = settings.DATABASE_URL  # "sqlite:///data/mismartera.db"

# Create engine (thread-safe, synchronous)
engine = create_engine(
    db_url,
    echo=False,  # Disable SQL logging
    pool_pre_ping=True,  # Verify connections
    connect_args={"check_same_thread": False}  # SQLite thread safety
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False  # Keep objects accessible after commit
)

# Base for all models
Base = declarative_base()
```

### Initialization

```python
# Initialize database (create tables)
from app.models.database import init_db
init_db()  # Creates all tables from Base.metadata

# Close connections (cleanup)
from app.models.database import close_db
close_db()  # Dispose of connection pool
```

### File Location

- **Database file**: `data/mismartera.db`
- **Auto-created**: Directory created automatically if missing
- **Migrations**: `migrations/` directory

---

## Models Reference

### Core Models

#### User (`user.py`)

User accounts and authentication.

```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    account_info = relationship("AccountInfo", back_populates="user")
```

**Usage:**
```python
with SessionLocal() as session:
    user = session.query(User).filter(User.username == "john").first()
    print(f"User: {user.email}, Active: {user.is_active}")
```

---

#### AccountInfo (`account.py`)

Brokerage account information.

```python
class AccountInfo(Base):
    __tablename__ = "account_info"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    broker = Column(String(50), nullable=False)  # "schwab", "alpaca"
    account_number = Column(String(100))
    account_type = Column(String(50))
    cash_balance = Column(Float, default=0.0)
    buying_power = Column(Float, default=0.0)
    total_value = Column(Float, default=0.0)
    equity = Column(Float, default=0.0)
    last_synced = Column(DateTime(timezone=True))
    
    user = relationship("User", back_populates="account_info")
```

---

#### Position (`account.py`)

Current stock positions.

```python
class Position(Base):
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    account_id = Column(Integer, ForeignKey("account_info.id"))
    symbol = Column(String(10), index=True, nullable=False)
    quantity = Column(Float, nullable=False)
    average_price = Column(Float, nullable=False)
    current_price = Column(Float)
    market_value = Column(Float)
    cost_basis = Column(Float)
    unrealized_pnl = Column(Float)
    day_change = Column(Float)
    last_updated = Column(DateTime(timezone=True))
```

---

#### Order (`orders.py`)

Order history and status.

```python
class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    account_id = Column(Integer, ForeignKey("account_info.id"))
    broker_order_id = Column(String(100), unique=True, index=True)
    symbol = Column(String(10), index=True, nullable=False)
    order_type = Column(String(20))  # MARKET, LIMIT, STOP, STOP_LIMIT
    side = Column(String(10))  # BUY, SELL
    quantity = Column(Float, nullable=False)
    filled_quantity = Column(Float, default=0.0)
    price = Column(Float)
    status = Column(String(20))  # PENDING, FILLED, CANCELLED, REJECTED
    placed_at = Column(DateTime(timezone=True))
    filled_at = Column(DateTime(timezone=True))
```

---

#### MarketHours (`trading_calendar.py`)

Market hours configuration per exchange group and asset class.

```python
class MarketHours(Base):
    __tablename__ = "market_hours"
    
    id = Column(Integer, primary_key=True)
    exchange_group = Column(String(50), nullable=False)
    asset_class = Column(String(50), nullable=False)
    exchanges = Column(String(200))  # Comma-separated
    timezone = Column(String(100), nullable=False)
    
    # Market hours (in local market time)
    regular_open = Column(Time, nullable=False)
    regular_close = Column(Time, nullable=False)
    pre_market_open = Column(Time)
    post_market_close = Column(Time)
    
    trading_days = Column(String(50), default="0,1,2,3,4")  # Mon-Fri
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('exchange_group', 'asset_class'),
    )
```

**Critical:** All `Time` columns must be interpreted with the `timezone` column!

**Helper Methods:**
```python
# Get timezone-aware datetime
open_dt = market_hours.get_regular_open_datetime(date(2025, 7, 2))
close_dt = market_hours.get_regular_close_datetime(date(2025, 7, 2))

# Convert to different timezone
open_utc = market_hours.get_regular_open_datetime(
    date(2025, 7, 2),
    target_timezone="UTC"
)
```

---

#### TradingHoliday (`trading_calendar.py`)

Market holidays and early closes.

```python
class TradingHoliday(Base):
    __tablename__ = "trading_holidays"
    
    id = Column(Integer, primary_key=True)
    exchange = Column(String(50), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    holiday_name = Column(String(100))
    is_closed = Column(Boolean, default=True)
    early_close_time = Column(Time)  # If early close instead of full close
    
    __table_args__ = (
        UniqueConstraint('exchange', 'date'),
    )
```

---

#### SessionConfig (`session_config.py`)

Session configuration storage.

```python
class SessionConfig(Base):
    __tablename__ = "session_configs"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    config_json = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
```

---

### Legacy Models

#### MarketData (`schemas.py`)

OHLCV market data for backtesting.

```python
class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), index=True)
    timestamp = Column(DateTime(timezone=True), index=True)
    interval = Column(String(10), default='1m')  # 1m, 5m, 1h, 1d
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, default=0)
    
    __table_args__ = (
        UniqueConstraint('symbol', 'timestamp', 'interval'),
    )
```

**Note:** Primary storage is now Parquet files. This table used for specific queries only.

---

## Session Management

### Basic Usage

```python
from app.models.database import SessionLocal

# Context manager (recommended)
with SessionLocal() as session:
    user = session.query(User).filter(User.id == 1).first()
    user.email = "new@example.com"
    session.commit()  # Automatic on context exit
# session.close() automatic

# Manual session
session = SessionLocal()
try:
    user = session.query(User).first()
    session.commit()
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```

### Dependency Injection Pattern

```python
from app.models.database import get_db

def some_operation():
    """Using dependency injection"""
    for session in get_db():
        user = session.query(User).first()
        # Automatic commit/rollback/close
```

### Query Patterns

```python
with SessionLocal() as session:
    # Simple query
    user = session.query(User).filter(User.id == 1).first()
    
    # Multiple filters
    users = session.query(User).filter(
        User.is_active == True,
        User.email.like("%@example.com")
    ).all()
    
    # Join query
    positions = session.query(Position).join(User).filter(
        User.username == "john"
    ).all()
    
    # Aggregate
    from sqlalchemy import func
    total = session.query(func.sum(Position.market_value)).scalar()
    
    # Order and limit
    recent = session.query(Order).order_by(
        Order.placed_at.desc()
    ).limit(10).all()
```

### Bulk Operations

```python
with SessionLocal() as session:
    # Bulk insert
    positions = [
        Position(symbol="AAPL", quantity=100, average_price=150),
        Position(symbol="GOOGL", quantity=50, average_price=140),
    ]
    session.bulk_save_objects(positions)
    session.commit()
    
    # Bulk update
    session.query(Position).filter(
        Position.symbol == "AAPL"
    ).update({"current_price": 155})
    session.commit()
    
    # Bulk delete
    session.query(Order).filter(
        Order.status == "CANCELLED"
    ).delete()
    session.commit()
```

---

## User Authentication

### Password Hashing

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash password
hashed = pwd_context.hash("password123")

# Verify password
is_valid = pwd_context.verify("password123", hashed)
```

### User Creation

```python
def create_user(username: str, email: str, password: str):
    """Create new user with hashed password"""
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(password)
    
    with SessionLocal() as session:
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
```

### Authentication

```python
def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user by username and password"""
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        
        if not user:
            return None
        
        if not pwd_context.verify(password, user.hashed_password):
            return None
        
        if not user.is_active:
            return None
        
        return user
```

---

## Migration Guide

### Creating Migrations

**Manual migration script:**

```python
# migrations/add_new_column.py
from app.models.database import engine
from sqlalchemy import text

def upgrade():
    """Add new column"""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN phone VARCHAR(20)"
        ))
        conn.commit()

def downgrade():
    """Remove column"""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users DROP COLUMN phone"
        ))
        conn.commit()

if __name__ == "__main__":
    upgrade()
```

### Running Migrations

```bash
# Run migration
python migrations/add_new_column.py

# Or via CLI
python -m app.models.init_db_if_missing
```

### Schema Changes

**Adding a new model:**

1. Create model class in appropriate file
2. Import in `app/models/__init__.py`
3. Run `init_db()` to create tables

```python
# New model
from app.models.database import Base

class NewModel(Base):
    __tablename__ = "new_table"
    id = Column(Integer, primary_key=True)
    # ... fields

# Initialize
from app.models.database import init_db
init_db()  # Creates new_table
```

---

## Best Practices

### DO ✅

**1. Use Context Managers**
```python
with SessionLocal() as session:
    # Query and modify
    user = session.query(User).first()
# Automatic cleanup
```

**2. Explicit Commits**
```python
with SessionLocal() as session:
    user.email = "new@example.com"
    session.commit()  # Explicit is better
```

**3. Handle Exceptions**
```python
with SessionLocal() as session:
    try:
        # Operations
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.error("Duplicate entry")
    except Exception as e:
        session.rollback()
        raise
```

**4. Use Relationships**
```python
# Define relationship in model
user = relationship("User", back_populates="positions")

# Use it
positions = user.positions  # Automatic join
```

**5. Timezone-Aware Datetimes**
```python
from datetime import datetime
from zoneinfo import ZoneInfo

# Always timezone-aware
created_at = datetime.now(ZoneInfo("UTC"))
```

### DON'T ❌

**1. Share Sessions Across Threads**
```python
# ❌ Wrong
session = SessionLocal()  # Shared!
# Use in multiple threads - UNSAFE!

# ✅ Correct
with SessionLocal() as session:  # New session per operation
    # Thread-safe
```

**2. Keep Sessions Open Long**
```python
# ❌ Wrong
session = SessionLocal()
# ... long-running operations
session.close()  # Too late!

# ✅ Correct
with SessionLocal() as session:
    # Quick operation
    pass  # Auto-close
```

**3. Forget to Commit**
```python
# ❌ Wrong
with SessionLocal() as session:
    user.email = "new@example.com"
    # No commit - changes lost!

# ✅ Correct
with SessionLocal() as session:
    user.email = "new@example.com"
    session.commit()
```

**4. Use Naive Datetimes**
```python
# ❌ Wrong
created_at = datetime.now()  # Naive!

# ✅ Correct
created_at = datetime.now(ZoneInfo("UTC"))  # Aware!
```

**5. Ignore Unique Constraints**
```python
# ❌ Wrong
user = User(username="existing")  # Duplicate!
session.add(user)
session.commit()  # IntegrityError!

# ✅ Correct
existing = session.query(User).filter(User.username == "new").first()
if not existing:
    user = User(username="new")
    session.add(user)
    session.commit()
```

---

## Query Examples

### Simple Queries
```python
with SessionLocal() as session:
    # Get by ID
    user = session.query(User).get(1)
    
    # Filter
    active_users = session.query(User).filter(User.is_active == True).all()
    
    # First match
    user = session.query(User).filter(User.email == "test@example.com").first()
    
    # Count
    count = session.query(User).count()
```

### Complex Queries
```python
with SessionLocal() as session:
    # Multiple filters
    results = session.query(Position).filter(
        Position.symbol == "AAPL",
        Position.quantity > 0
    ).all()
    
    # OR condition
    from sqlalchemy import or_
    results = session.query(User).filter(
        or_(User.username == "john", User.email == "john@example.com")
    ).first()
    
    # IN clause
    symbols = ["AAPL", "GOOGL", "MSFT"]
    positions = session.query(Position).filter(
        Position.symbol.in_(symbols)
    ).all()
    
    # Date range
    from datetime import datetime, timedelta
    start = datetime.now() - timedelta(days=7)
    orders = session.query(Order).filter(
        Order.placed_at >= start
    ).all()
```

### Join Queries
```python
with SessionLocal() as session:
    # Inner join
    results = session.query(Position, User).join(User).filter(
        User.username == "john"
    ).all()
    
    # Left outer join
    results = session.query(User).outerjoin(Position).all()
    
    # Multiple joins
    results = session.query(Order).join(User).join(Position).filter(
        Position.symbol == "AAPL"
    ).all()
```

---

## Troubleshooting

### Common Issues

**1. "No such table" error**
```python
# Solution: Initialize database
from app.models.database import init_db
init_db()
```

**2. "Database is locked" error**
```python
# Solution: Close existing connections
from app.models.database import close_db
close_db()

# Or increase timeout
engine = create_engine(db_url, connect_args={"timeout": 30})
```

**3. "DetachedInstanceError"**
```python
# Problem: Accessing object after session closed
with SessionLocal() as session:
    user = session.query(User).first()
# user is detached here!

# Solution: Refresh or use expire_on_commit=False
SessionLocal = sessionmaker(expire_on_commit=False)
```

---

## Related Documentation

- `DATABASE_USERS.md` - User management details
- `AUTHENTICATION.md` - Authentication system
- `/app/managers/time_manager/README.md` - TimeManager (uses MarketHours)

---

**Version:** 1.0  
**Last Updated:** 2025-11-26  
**Status:** Production Ready
