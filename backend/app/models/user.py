"""
User Model for Authentication
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.database import Base


class User(Base):
    """
    User model for authentication and authorization
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="trader", nullable=False)  # admin, trader
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships - defined lazily to avoid circular imports
    # These will be populated when other models are loaded
    orders = relationship("OrderLegacy", back_populates="user", lazy="dynamic")
    positions = relationship("PositionLegacy", back_populates="user", lazy="dynamic")
    account_info = relationship("AccountInfo", back_populates="user", uselist=False)
    
    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}', role='{self.role}')>"
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
