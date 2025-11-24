"""
Application configuration using pydantic-settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "MisMartera Trading Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # System defaults
    SYSTEM_OPERATING_MODE: str = "backtest"        # "backtest" or "live"
    DISABLE_CLI_LOGIN_REQUIREMENT: bool = True # Disable login requirement for CLI (HTTP API still requires login)
    
    # API Configuration
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/trading_app.db"
    
    # Charles Schwab API
    SCHWAB_APP_KEY: str = ""
    SCHWAB_APP_SECRET: str = ""
    SCHWAB_CALLBACK_URL: str = "https://127.0.0.1:8000/callback"
    SCHWAB_API_BASE_URL: str = "https://api.schwabapi.com"
    
    # Alpaca API
    ALPACA_API_KEY_ID: str = ""
    ALPACA_API_SECRET_KEY: str = ""
    # Trading API base URL (orders, account, etc.)
    ALPACA_API_BASE_URL: str = "https://api.alpaca.markets"
    # Historical data API base URL (bars, quotes, etc.)
    ALPACA_DATA_BASE_URL: str = "https://data.alpaca.markets"
    ALPACA_PAPER_TRADING: bool = True
    
    # Anthropic Claude API
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-opus-4-20250514"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "./data/logs/app.log"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    # Trading Configuration
    PAPER_TRADING: bool = True
    MAX_POSITION_SIZE: float = 10000.0
    DEFAULT_ORDER_TIMEOUT: int = 60

    # DataManager defaults
    DATA_MANAGER_DATA_API: str = "alpaca"          # e.g. "alpaca", "schwab"
    DATA_MANAGER_BACKTEST_DAYS: int = 60           # trading days for backtests
    # Backtest speed multiplier: 0 = max speed (no pacing), 1.0 = realtime, 2.0 = 2x speed, 0.5 = half speed
    DATA_MANAGER_BACKTEST_SPEED: float = 60.0
    
    # Data-Upkeep Thread Configuration (Phase 2)
    DATA_UPKEEP_ENABLED: bool = True
    DATA_UPKEEP_CHECK_INTERVAL_SECONDS: int = 60   # How often to check data quality
    DATA_UPKEEP_RETRY_MISSING_BARS: bool = True    # Automatically fill gaps
    DATA_UPKEEP_MAX_RETRIES: int = 5               # Max retries for failed gap fills
    DATA_UPKEEP_DERIVED_INTERVALS: list = [5, 15]  # Derived bar intervals (minutes)
    DATA_UPKEEP_AUTO_COMPUTE_DERIVED: bool = True  # Auto-compute derived bars
    
    # Historical Bars Configuration (Phase 3)
    HISTORICAL_BARS_ENABLED: bool = True
    HISTORICAL_BARS_TRAILING_DAYS: int = 5         # Number of trailing days to keep
    HISTORICAL_BARS_INTERVALS: list = [1, 5]       # Which intervals to load (minutes)
    HISTORICAL_BARS_AUTO_LOAD: bool = True         # Auto-load on session start
    
    # Prefetch Configuration (Phase 4)
    PREFETCH_ENABLED: bool = True
    PREFETCH_WINDOW_MINUTES: int = 60              # Start prefetch 60min before session
    PREFETCH_CHECK_INTERVAL_MINUTES: int = 5       # Check for prefetch every 5 minutes
    PREFETCH_AUTO_ACTIVATE: bool = True            # Auto-activate prefetch on session start
    
    # Session Boundary Configuration (Phase 5)
    SESSION_AUTO_ROLL: bool = True                 # Automatically roll to next session
    SESSION_TIMEOUT_SECONDS: int = 300             # Timeout if no data for 5 minutes
    SESSION_BOUNDARY_CHECK_INTERVAL: int = 60      # Check boundaries every minute
    SESSION_POST_MARKET_ROLL_DELAY: int = 30       # Minutes after close to auto-roll
    
    # Timezone configuration
    TRADING_TIMEZONE: str = "America/New_York"     # canonical market timezone (ET)
    LOCAL_TIMEZONE: str = "America/Los_Angeles"    # default local display timezone
    DISPLAY_LOCAL_TIMEZONE: bool = True            # if True, CLI converts ET to LOCAL_TIMEZONE
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
