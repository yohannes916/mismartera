"""
Authentication Middleware for FastAPI
"""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

from app.services.auth.auth_service import auth_service
from app.logger import logger

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from bearer token
    
    Args:
        credentials: HTTP Authorization credentials
        
    Returns:
        Current user data
        
    Raises:
        HTTPException: If authentication fails
    """
    if credentials is None:
        logger.warning(f"Missing authentication credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    
    # Validate session
    user = auth_service.get_current_user(token)
    
    if not user:
        logger.warning(f"Invalid or expired session token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_admin_user(
    current_user: Dict[str, Any] = Security(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency to get current user with admin role
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Current admin user data
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("role") != "admin":
        logger.warning(f"Non-admin user attempted admin action: {current_user.get('username')}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user
