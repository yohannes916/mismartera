"""
User Repository - Database operations for users
"""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models.user import User
from app.logger import logger


class UserRepository:
    """Repository for user database operations"""
    
    @staticmethod
    async def create_user(
        session: AsyncSession,
        username: str,
        email: str,
        password_hash: str,
        role: str = "trader"
    ) -> User:
        """
        Create a new user
        
        Args:
            session: Database session
            username: Username
            email: Email address
            password_hash: Hashed password
            role: User role (default: trader)
            
        Returns:
            Created user
        """
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True
        )
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"User created: {username} ({role})")
        return user
    
    @staticmethod
    async def get_user_by_username(
        session: AsyncSession,
        username: str
    ) -> Optional[User]:
        """
        Get user by username
        
        Args:
            session: Database session
            username: Username to search for
            
        Returns:
            User if found, None otherwise
        """
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_email(
        session: AsyncSession,
        email: str
    ) -> Optional[User]:
        """
        Get user by email
        
        Args:
            session: Database session
            email: Email to search for
            
        Returns:
            User if found, None otherwise
        """
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(
        session: AsyncSession,
        user_id: int
    ) -> Optional[User]:
        """
        Get user by ID
        
        Args:
            session: Database session
            user_id: User ID
            
        Returns:
            User if found, None otherwise
        """
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all_users(
        session: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        Get all users with pagination
        
        Args:
            session: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of users
        """
        result = await session.execute(
            select(User).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def update_user(
        session: AsyncSession,
        user: User,
        **kwargs
    ) -> User:
        """
        Update user attributes
        
        Args:
            session: Database session
            user: User to update
            **kwargs: Attributes to update
            
        Returns:
            Updated user
        """
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"User updated: {user.username}")
        return user
    
    @staticmethod
    async def update_last_login(
        session: AsyncSession,
        user: User
    ) -> User:
        """
        Update user's last login timestamp
        
        Args:
            session: Database session
            user: User to update
            
        Returns:
            Updated user
        """
        user.last_login = datetime.now()
        await session.commit()
        await session.refresh(user)
        return user
    
    @staticmethod
    async def delete_user(
        session: AsyncSession,
        user: User
    ) -> bool:
        """
        Delete a user
        
        Args:
            session: Database session
            user: User to delete
            
        Returns:
            True if deleted successfully
        """
        await session.delete(user)
        await session.commit()
        logger.info(f"User deleted: {user.username}")
        return True
    
    @staticmethod
    async def deactivate_user(
        session: AsyncSession,
        user: User
    ) -> User:
        """
        Deactivate a user (soft delete)
        
        Args:
            session: Database session
            user: User to deactivate
            
        Returns:
            Updated user
        """
        user.is_active = False
        await session.commit()
        await session.refresh(user)
        logger.info(f"User deactivated: {user.username}")
        return user
    
    @staticmethod
    async def activate_user(
        session: AsyncSession,
        user: User
    ) -> User:
        """
        Activate a user
        
        Args:
            session: Database session
            user: User to activate
            
        Returns:
            Updated user
        """
        user.is_active = True
        await session.commit()
        await session.refresh(user)
        logger.info(f"User activated: {user.username}")
        return user
    
    @staticmethod
    async def count_users(session: AsyncSession) -> int:
        """
        Count total number of users
        
        Args:
            session: Database session
            
        Returns:
            Number of users
        """
        from sqlalchemy import func
        result = await session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar()
