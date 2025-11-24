"""Configuration model for DataManager.

Thin wrapper around global app.settings to provide clear defaults
for operating mode and data API provider.
"""
from dataclasses import dataclass

from app.config import settings


@dataclass
class DataManagerConfig:
    """Configuration for DataManager behavior.

    Attributes:
        data_api: Name of the data provider (e.g. "alpaca", "schwab").
        backtest_days: Number of trading days to include in backtest window.
    """

    data_api: str = settings.DATA_MANAGER_DATA_API
    backtest_days: int = settings.DATA_MANAGER_BACKTEST_DAYS
