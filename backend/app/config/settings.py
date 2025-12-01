"""
Application configuration using pydantic-settings with nested structure
"""
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List


# ============================================================================
# NESTED CONFIGURATION MODELS
# ============================================================================

class SystemConfig(BaseModel):
    """System-level configuration."""
    operating_mode: str = "backtest"                 # "backtest" or "live"
    disable_cli_login: bool = True                   # Disable login requirement for CLI


class APIConfig(BaseModel):
    """HTTP API server configuration."""
    host: str = "127.0.0.1"                         # API server host
    port: int = 8000                                 # API server port


class SecurityConfig(BaseModel):
    """Security and authentication configuration."""
    secret_key: str = "INSECURE-DEFAULT-CHANGE-IN-PRODUCTION"  # JWT secret key (MUST set via SECURITY__SECRET_KEY)
    algorithm: str = "HS256"                         # JWT algorithm
    access_token_expire_minutes: int = 1440          # Token expiration (24 hours)


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    url: str = "sqlite+aiosqlite:///./data/trading_app.db"  # Database connection string


class SchwabConfig(BaseModel):
    """Charles Schwab API credentials and configuration."""
    app_key: str = ""                                # Schwab app key
    app_secret: str = ""                             # Schwab app secret
    callback_url: str = "https://127.0.0.1:8000/callback"  # OAuth callback URL
    api_base_url: str = "https://api.schwabapi.com"  # Schwab API base URL


class AlpacaConfig(BaseModel):
    """Alpaca API credentials and configuration."""
    api_key_id: str = ""                             # Alpaca API key ID
    api_secret_key: str = ""                         # Alpaca API secret key
    api_base_url: str = "https://api.alpaca.markets"  # Trading API base URL
    data_base_url: str = "https://data.alpaca.markets"  # Historical data API base URL
    paper_trading: bool = True                       # Use paper trading account


class ClaudeConfig(BaseModel):
    """Anthropic Claude API configuration."""
    api_key: str = ""                                # Anthropic API key
    model: str = "claude-opus-4-20250514"            # Claude model to use


class LoggerConfig(BaseModel):
    """Logger configuration settings."""
    # Core logging settings
    default_level: str = "INFO"                      # Log level (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
    file_path: str = "./data/logs/app.log"          # Log file location
    rotation: str = "10 MB"                          # Rotate when file reaches this size
    retention: str = "30 days"                       # Keep logs for this duration
    
    # Deduplication filter settings
    filter_enabled: bool = True                      # Enable log deduplication filter
    filter_max_history: int = 5                      # Number of recent log locations to track
    filter_time_threshold_seconds: float = 1.0       # Suppress duplicates within this time window (seconds)


class DataManagerConfig(BaseModel):
    """Data Manager configuration."""
    data_api: str = "alpaca"                         # Data provider: "alpaca" or "schwab"


class ExecutionConfig(BaseModel):
    """Execution Manager configuration."""
    default_brokerage: str = "mismartera"            # Default brokerage: "alpaca", "schwab", or "mismartera"


class MismarteraConfig(BaseModel):
    """Mismartera simulated trading configuration."""
    initial_balance: float = 100000.0                # Starting cash balance
    buying_power_multiplier: float = 1.0             # Margin multiplier (1.0=cash, 2.0=2x leverage)
    execution_cost_pct: float = 0.001                # Total execution cost as % (0.1% = 10 bps)
    slippage_pct: float = 0.0001                     # Market order slippage (0.01% = 1 bp)


# ============================================================================
# MAIN SETTINGS CLASS
# ============================================================================

class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    Configuration is organized into nested sections for better organization.
    Use double underscore (__) in env vars to access nested configs.
    
    Example:
        LOGGER__DEFAULT_LEVEL=DEBUG
        SYSTEM__OPERATING_MODE=live
        SESSION__HISTORICAL_TRAILING_DAYS=10
    """
    
    # Application metadata
    APP_NAME: str = "MisMartera Trading Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Nested configuration sections (initialized with defaults, overridden by env vars via env_nested_delimiter)
    SYSTEM: SystemConfig = Field(default_factory=SystemConfig)
    API: APIConfig = Field(default_factory=APIConfig)
    SECURITY: SecurityConfig = Field(default_factory=SecurityConfig)  # Requires SECURITY__SECRET_KEY in .env
    DATABASE: DatabaseConfig = Field(default_factory=DatabaseConfig)
    SCHWAB: SchwabConfig = Field(default_factory=SchwabConfig)
    ALPACA: AlpacaConfig = Field(default_factory=AlpacaConfig)
    CLAUDE: ClaudeConfig = Field(default_factory=ClaudeConfig)
    LOGGER: LoggerConfig = Field(default_factory=LoggerConfig)
    DATA_MANAGER: DataManagerConfig = Field(default_factory=DataManagerConfig)
    EXECUTION: ExecutionConfig = Field(default_factory=ExecutionConfig)
    MISMARTERA: MismarteraConfig = Field(default_factory=MismarteraConfig)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_nested_delimiter="__"
    )


# Global settings instance
settings = Settings()
