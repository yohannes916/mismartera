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
    """

    data_api: str = settings.DATA_MANAGER.data_api
