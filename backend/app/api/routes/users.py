"""
User Management API Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import get_db
from app.repositories.user_repository import UserRepository
from app.services.auth.auth_service import auth_service
from app.api.middleware.auth import get_current_user, get_admin_user
from app.logger import logger

router = APIRouter(prefix="/api/users", tags=["Users"])


class UserCreate(BaseModel):
    """User creation request"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field("trader", pattern="^(admin|trader)$")


class UserResponse(BaseModel):
    """User response model"""
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None


class UserUpdate(BaseModel):
    """User update request"""
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern="^(admin|trader)$")
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_db)
):
    """
    Register a new user
    
    Args:
        user_data: User registration data
        session: Database session
        
    Returns:
        Created user information
    """
    logger.info(f"User registration attempt: {user_data.username}")
    
    # Check if username already exists
    existing_user = await UserRepository.get_user_by_username(session, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = await UserRepository.get_user_by_email(session, user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password
    password_hash = auth_service.hash_password(user_data.password)
    
    # Create user
    try:
        user = await UserRepository.create_user(
            session=session,
            username=user_data.username,
            email=user_data.email,
            password_hash=password_hash,
            role=user_data.role
        )
        
        logger.success(f"User registered successfully: {user.username}")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        
    except Exception as e:
        logger.error(f"User registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get current user's information
    
    Args:
        current_user: Authenticated user
        session: Database session
        
    Returns:
        User information
    """
    # If user has ID, fetch from database
    if "id" in current_user:
        user = await UserRepository.get_user_by_id(session, current_user["id"])
        if user:
            return UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at.isoformat(),
                last_login=user.last_login.isoformat() if user.last_login else None
            )
    
    # Fallback for hardcoded users
    return UserResponse(
        id=0,
        username=current_user["username"],
        email=current_user.get("email", ""),
        role=current_user.get("role", "trader"),
        is_active=True,
        created_at="",
        last_login=None
    )


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    List all users (admin only)
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        List of users
    """
    users = await UserRepository.get_all_users(session, skip=skip, limit=limit)
    
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        for user in users
    ]


@router.get("/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get user by username (admin only)
    
    Args:
        username: Username to fetch
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        User information
    """
    user = await UserRepository.get_user_by_username(session, username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        last_login=user.last_login.isoformat() if user.last_login else None
    )


@router.put("/{username}", response_model=UserResponse)
async def update_user(
    username: str,
    user_update: UserUpdate,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Update user (admin only)
    
    Args:
        username: Username to update
        user_update: Update data
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        Updated user information
    """
    user = await UserRepository.get_user_by_username(session, username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    update_data = user_update.dict(exclude_unset=True)
    user = await UserRepository.update_user(session, user, **update_data)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        last_login=user.last_login.isoformat() if user.last_login else None
    )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Change current user's password
    
    Args:
        password_data: Password change data
        current_user: Authenticated user
        session: Database session
        
    Returns:
        Success message
    """
    # Get user from database
    if "id" not in current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change password for non-database users"
        )
    
    user = await UserRepository.get_user_by_id(session, current_user["id"])
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not auth_service.verify_password(password_data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Hash new password
    new_password_hash = auth_service.hash_password(password_data.new_password)
    
    # Update password
    await UserRepository.update_user(session, user, password_hash=new_password_hash)
    
    logger.info(f"Password changed for user: {user.username}")
    
    return {"message": "Password changed successfully"}


@router.delete("/{username}")
async def delete_user(
    username: str,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Delete user (admin only)
    
    Args:
        username: Username to delete
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        Success message
    """
    user = await UserRepository.get_user_by_username(session, username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-deletion
    if user.username == admin_user["username"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    await UserRepository.delete_user(session, user)
    
    return {"message": f"User {username} deleted successfully"}


@router.post("/{username}/deactivate")
async def deactivate_user(
    username: str,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Deactivate user (admin only)
    
    Args:
        username: Username to deactivate
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        Success message
    """
    user = await UserRepository.get_user_by_username(session, username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await UserRepository.deactivate_user(session, user)
    
    return {"message": f"User {username} deactivated successfully"}


@router.post("/{username}/activate")
async def activate_user(
    username: str,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Activate user (admin only)
    
    Args:
        username: Username to activate
        admin_user: Authenticated admin user
        session: Database session
        
    Returns:
        Success message
    """
    user = await UserRepository.get_user_by_username(session, username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await UserRepository.activate_user(session, user)
    
    return {"message": f"User {username} activated successfully"}
