"""
Admin API routes for system management
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any
from app.logger import logger, logger_manager
from datetime import datetime
from app.config import settings
from app.api.middleware.auth import get_admin_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])


class LogLevelRequest(BaseModel):
    """Request model for changing log level"""
    level: str = Field(..., description="Log level: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL")


class LogLevelResponse(BaseModel):
    """Response model for log level operations"""
    success: bool
    level: str
    available_levels: list[str]
    message: str


class SystemStatusResponse(BaseModel):
    """System status information"""
    app_name: str
    version: str
    status: str
    uptime_seconds: float
    log_level: str
    alpaca_paper_trading: bool
    database_url: str
    timestamp: datetime


# Track application start time
_app_start_time = datetime.now()


@router.post("/log-level", response_model=LogLevelResponse)
async def set_log_level(
    request: LogLevelRequest,
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Change application log level at runtime
    
    Args:
        request: LogLevelRequest with desired log level
        
    Returns:
        LogLevelResponse with new level and available options
        
    Raises:
        HTTPException: If invalid log level provided
    """
    try:
        new_level = logger_manager.set_level(request.level)
        logger.success(f"Log level changed to: {new_level} via API")
        
        return LogLevelResponse(
            success=True,
            level=new_level,
            available_levels=logger_manager.get_available_levels(),
            message=f"Log level successfully changed to {new_level}"
        )
    except ValueError as e:
        logger.error(f"Invalid log level requested: {request.level}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error changing log level: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/log-level", response_model=LogLevelResponse)
async def get_log_level(admin_user: Dict[str, Any] = Depends(get_admin_user)):
    """
    Get current log level and available options
    
    Returns:
        LogLevelResponse with current level and available options
    """
    current_level = logger_manager.get_level()
    available_levels = logger_manager.get_available_levels()
    
    logger.debug("Log level queried via API")
    
    return LogLevelResponse(
        success=True,
        level=current_level,
        available_levels=available_levels,
        message=f"Current log level is {current_level}"
    )


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(admin_user: Dict[str, Any] = Depends(get_admin_user)):
    """
    Get system status and configuration information
    
    Returns:
        SystemStatusResponse with system information
    """
    uptime = (datetime.now() - _app_start_time).total_seconds()
    
    logger.debug("System status queried via API")
    
    return SystemStatusResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="running",
        uptime_seconds=uptime,
        log_level=logger_manager.get_level(),
        alpaca_paper_trading=settings.ALPACA.paper_trading,
        database_url=settings.DATABASE.url.split("///")[-1] if "///" in settings.DATABASE.url else settings.DATABASE.url,
        timestamp=datetime.now()
    )


@router.post("/shutdown")
async def shutdown(admin_user: Dict[str, Any] = Depends(get_admin_user)):
    """
    Graceful shutdown endpoint (for development)
    
    Note: This will not work in production with multiple workers
    """
    logger.warning("Shutdown requested via API")
    return {"message": "Shutdown signal sent. Use Ctrl+C to stop the server."}
