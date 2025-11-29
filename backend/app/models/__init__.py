"""
Database models and schemas
"""
from app.models.database import Base, engine, SessionLocal, get_db, init_db, close_db
from app.models.user import User
from app.models.schemas import AccountInfo, MarketData, Analysis
from app.models.trading_calendar import TradingHoliday

# New models for architecture refactor
from app.models.orders import Order as OrderModel, OrderExecution
from app.models.account import Account, AccountTransaction, Position as PositionModel
from app.models.weights import WeightSet, WeightPerformance
from app.models.analysis_log import AnalysisLog, AnalysisMetrics

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "close_db",
    "User",
    "AccountInfo",
    "MarketData",
    "Analysis",
    "TradingHoliday",
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
