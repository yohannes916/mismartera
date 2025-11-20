"""
Authentication Service
Handles user authentication and session management
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import secrets
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.logger import logger
from app.config import settings
from app.repositories.user_repository import UserRepository
from app.models.user import User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """
    Authentication service for CLI and API
    """
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = timedelta(hours=8)  # 8-hour trading day
        
    def hash_password(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def create_session(self, username: str, user_data: Dict[str, Any]) -> str:
        """
        Create a new session for authenticated user
        
        Args:
            username: Username
            user_data: User information
            
        Returns:
            Session token
        """
        session_token = secrets.token_urlsafe(32)
        
        self.sessions[session_token] = {
            "username": username,
            "user_data": user_data,
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "authenticated": True
        }
        
        logger.info(f"Session created for user: {username}")
        return session_token
    
    def validate_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a session token
        
        Args:
            session_token: Session token to validate
            
        Returns:
            Session data if valid, None otherwise
        """
        if session_token not in self.sessions:
            return None
        
        session = self.sessions[session_token]
        
        # Check if session has expired
        if datetime.now() - session["last_active"] > self.session_timeout:
            logger.warning(f"Session expired for user: {session['username']}")
            self.destroy_session(session_token)
            return None
        
        # Update last active time
        session["last_active"] = datetime.now()
        return session
    
    def destroy_session(self, session_token: str) -> bool:
        """
        Destroy a session
        
        Args:
            session_token: Session token to destroy
            
        Returns:
            True if session was destroyed, False if not found
        """
        if session_token in self.sessions:
            username = self.sessions[session_token].get("username", "unknown")
            del self.sessions[session_token]
            logger.info(f"Session destroyed for user: {username}")
            return True
        return False
    
    async def authenticate_user(
        self, 
        username: str, 
        password: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user with username and password
        
        Args:
            username: Username
            password: Password
            session: Optional database session (if None, uses fallback hardcoded users)
            
        Returns:
            User data if authenticated, None otherwise
        """
        # Try database authentication first if session provided
        if session:
            try:
                user = await UserRepository.get_user_by_username(session, username)
                
                if user and user.is_active:
                    if self.verify_password(password, user.password_hash):
                        # Update last login
                        await UserRepository.update_last_login(session, user)
                        
                        logger.success(f"User authenticated from database: {username}")
                        return {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role,
                            "email": user.email
                        }
            except Exception as e:
                logger.error(f"Database authentication error: {e}")
                # Fall through to hardcoded users
        
        # Fallback to hardcoded demo users (for initial setup / development)
        # Check for demo/admin user from settings
        if username == "admin" and password == settings.SECRET_KEY[:8]:
            logger.success(f"Admin user authenticated (fallback): {username}")
            return {
                "username": username,
                "role": "admin",
                "email": "admin@mismartera.com"
            }
        
        # Check for demo trader
        if username == "trader" and password == "demo123":
            logger.success(f"Demo trader authenticated (fallback): {username}")
            return {
                "username": username,
                "role": "trader",
                "email": "trader@mismartera.com"
            }
        
        logger.warning(f"Authentication failed for user: {username}")
        return None
    
    async def login(
        self, 
        username: str, 
        password: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[str]:
        """
        Login a user and create a session
        
        Args:
            username: Username
            password: Password
            session: Optional database session
            
        Returns:
            Session token if successful, None otherwise
        """
        user_data = await self.authenticate_user(username, password, session)
        
        if user_data:
            return self.create_session(username, user_data)
        
        return None
    
    def logout(self, session_token: str) -> bool:
        """
        Logout a user and destroy their session
        
        Args:
            session_token: Session token
            
        Returns:
            True if logout successful, False otherwise
        """
        return self.destroy_session(session_token)
    
    def get_current_user(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Get current user from session token
        
        Args:
            session_token: Session token
            
        Returns:
            User data if session is valid, None otherwise
        """
        session = self.validate_session(session_token)
        if session:
            return session.get("user_data")
        return None
    
    def list_active_sessions(self) -> list:
        """
        List all active sessions (for admin)
        
        Returns:
            List of active session information
        """
        active = []
        for token, session in list(self.sessions.items()):
            # Clean up expired sessions
            if datetime.now() - session["last_active"] > self.session_timeout:
                self.destroy_session(token)
            else:
                active.append({
                    "username": session["username"],
                    "created_at": session["created_at"],
                    "last_active": session["last_active"]
                })
        return active


# Global authentication service instance
auth_service = AuthService()
