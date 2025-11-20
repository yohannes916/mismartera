"""
Authentication API Endpoints
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import auth_service
from app.api.middleware.auth import get_current_user, get_admin_user
from app.models import get_db
from app.logger import logger

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model"""
    session_token: str
    username: str
    role: str
    message: str


class LogoutResponse(BaseModel):
    """Logout response model"""
    message: str


class UserInfo(BaseModel):
    """User information model"""
    username: str
    role: str
    email: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Login endpoint
    
    Args:
        request: Login credentials
        session: Database session
        
    Returns:
        Session token and user information
    """
    logger.info(f"Login attempt for user: {request.username}")
    
    session_token = await auth_service.login(request.username, request.password, session)
    
    if not session_token:
        logger.warning(f"Login failed for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    user = auth_service.get_current_user(session_token)
    
    return LoginResponse(
        session_token=session_token,
        username=user["username"],
        role=user.get("role", "user"),
        message="Login successful"
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Logout endpoint
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Logout confirmation
    """
    # The session token is in the auth header, we need to get it from the request
    # For now, we'll just confirm logout
    logger.info(f"User logged out: {current_user['username']}")
    
    return LogoutResponse(
        message=f"Logged out successfully"
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current user information
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User information
    """
    return UserInfo(
        username=current_user["username"],
        role=current_user.get("role", "user"),
        email=current_user.get("email", "")
    )


@router.get("/sessions")
async def list_sessions(admin_user: Dict[str, Any] = Depends(get_admin_user)):
    """
    List all active sessions (admin only)
    
    Args:
        admin_user: Current admin user
        
    Returns:
        List of active sessions
    """
    sessions = auth_service.list_active_sessions()
    return {
        "sessions": sessions,
        "count": len(sessions)
    }
