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
    SCHWAB_API_BASE_URL: str = "https://api.schwabapi.com/trader/v1"
    
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
    DATA_MANAGER_OPERATING_MODE: str = "backtest"  # "backtest" or "realtime"
    DATA_MANAGER_DATA_API: str = "alpaca"          # e.g. "alpaca", "schwab"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
