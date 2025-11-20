"""
Database models and schemas
"""
from app.models.database import Base, engine, AsyncSessionLocal, get_db, init_db, close_db
from app.models.user import User
from app.models.schemas import AccountInfo, PositionLegacy, OrderLegacy, MarketData, Analysis
from app.models.trading_calendar import TradingHoliday, TradingHours

# New models for architecture refactor
from app.models.orders import Order as OrderModel, OrderExecution
from app.models.account import Account, AccountTransaction, Position as PositionModel
from app.models.weights import WeightSet, WeightPerformance
from app.models.analysis_log import AnalysisLog, AnalysisMetrics

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "init_db",
    "close_db",
    "User",
    "AccountInfo",
    "PositionLegacy",
    "OrderLegacy",
    "MarketData",
    "Analysis",
    "TradingHoliday",
    "TradingHours",
    # New models
    "OrderModel",
    "OrderExecution",
    "Account",
    "AccountTransaction",
    "PositionModel",
    "WeightSet",
    "WeightPerformance",
    "AnalysisLog",
    "AnalysisMetrics",
]
