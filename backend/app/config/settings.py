"""
Application configuration using pydantic-settings with nested structure
"""
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pathlib import Path


# ============================================================================
# NESTED CONFIGURATION MODELS
# ============================================================================

# Get absolute path to .env file (backend directory)
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BASE_DIR / ".env"


class SystemConfig(BaseSettings):
    """System-level configuration."""
    operating_mode: str = "backtest"
    disable_cli_login: bool = True
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class APIConfig(BaseSettings):
    """HTTP API server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class SecurityConfig(BaseSettings):
    """Security and authentication configuration."""
    secret_key: str = "INSECURE-DEFAULT-CHANGE-IN-PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class DatabaseConfig(BaseSettings):
    """Database connection configuration."""
    url: str = "sqlite+aiosqlite:///./data/trading_app.db"
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class SchwabConfig(BaseSettings):
    """Charles Schwab API credentials and configuration."""
    app_key: str = ""
    app_secret: str = ""
    callback_url: str = "https://127.0.0.1:8000/callback"
    api_base_url: str = "https://api.schwabapi.com"
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class AlpacaConfig(BaseSettings):
    """Alpaca API credentials and configuration."""
    api_key_id: str = ""
    api_secret_key: str = ""
    api_base_url: str = "https://api.alpaca.markets"
    data_base_url: str = "https://data.alpaca.markets"
    paper_trading: bool = True
    
    model_config = SettingsConfigDict(
        env_prefix="ALPACA__",
        env_file=str(_ENV_FILE) if '_ENV_FILE' in globals() else None,
        extra="ignore"
    )


class ClaudeConfig(BaseSettings):
    """Anthropic Claude API configuration."""
    api_key: str = ""
    model: str = "claude-opus-4-20250514"
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class LoggerConfig(BaseSettings):
    """Logger configuration settings."""
    default_level: str = "INFO"
    file_path: str = "./data/logs/app.log"
    rotation: str = "10 MB"
    retention: str = "30 days"
    filter_enabled: bool = True
    filter_max_history: int = 5
    filter_time_threshold_seconds: float = 1.0
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class DataManagerConfig(BaseSettings):
    """Data Manager configuration."""
    data_api: str = "alpaca"
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class ExecutionConfig(BaseSettings):
    """Execution Manager configuration."""
    default_brokerage: str = "mismartera"
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class MismarteraConfig(BaseSettings):
    """Mismartera simulated trading configuration."""
    initial_balance: float = 100000.0
    buying_power_multiplier: float = 1.0
    execution_cost_pct: float = 0.001
    slippage_pct: float = 0.0001
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


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
    
    # Nested configuration sections (manually construct from environment)
    SYSTEM: SystemConfig = None
    API: APIConfig = None
    SECURITY: SecurityConfig = None
    DATABASE: DatabaseConfig = None
    SCHWAB: SchwabConfig = None
    ALPACA: AlpacaConfig = None
    CLAUDE: ClaudeConfig = None
    LOGGER: LoggerConfig = None
    DATA_MANAGER: DataManagerConfig = None
    EXECUTION: ExecutionConfig = None
    MISMARTERA: MismarteraConfig = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Manually construct nested configs AFTER environment is loaded
        import os
        self.SYSTEM = SystemConfig()
        self.API = APIConfig()
        self.SECURITY = SecurityConfig()
        self.DATABASE = DatabaseConfig()
        self.SCHWAB = SchwabConfig()
        
        # ALPACA: Manually override from environment
        self.ALPACA = AlpacaConfig()
        if os.getenv('ALPACA__API_KEY_ID'):
            self.ALPACA.api_key_id = os.getenv('ALPACA__API_KEY_ID')
        if os.getenv('ALPACA__API_SECRET_KEY'):
            self.ALPACA.api_secret_key = os.getenv('ALPACA__API_SECRET_KEY')
        if os.getenv('ALPACA__API_BASE_URL'):
            self.ALPACA.api_base_url = os.getenv('ALPACA__API_BASE_URL')
        if os.getenv('ALPACA__DATA_BASE_URL'):
            self.ALPACA.data_base_url = os.getenv('ALPACA__DATA_BASE_URL')
        if os.getenv('ALPACA__PAPER_TRADING'):
            self.ALPACA.paper_trading = os.getenv('ALPACA__PAPER_TRADING').lower() == 'true'
        
        self.CLAUDE = ClaudeConfig()
        self.LOGGER = LoggerConfig()
        self.DATA_MANAGER = DataManagerConfig()
        self.EXECUTION = ExecutionConfig()
        self.MISMARTERA = MismarteraConfig()
    
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_nested_delimiter="__",
        validate_default=True,
        env_prefix=""
    )


# Global settings instance
from dotenv import load_dotenv

# Load .env file into environment variables
if _ENV_FILE.exists():
    load_dotenv(str(_ENV_FILE), override=True)

settings = Settings()
