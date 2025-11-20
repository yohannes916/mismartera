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
        operating_mode: "backtest" or "realtime".
        data_api: Name of the data provider (e.g. "alpaca", "schwab").
    """

    operating_mode: str = settings.DATA_MANAGER_OPERATING_MODE
    data_api: str = settings.DATA_MANAGER_DATA_API
