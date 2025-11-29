"""
MisMartera Trading Backend - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.logger import logger
from app.models import init_db, close_db
from app.api.routes import admin, auth, claude, users, market_data, schwab_oauth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events for startup and shutdown
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Paper trading: {settings.PAPER_TRADING}")
    
    # Initialize database (now sync, run in thread pool)
    import asyncio
    await asyncio.to_thread(init_db)
    logger.success("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    await asyncio.to_thread(close_db)
    logger.success("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Day Trading Backend with CLI and REST API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Electron app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(claude.router, prefix="/api/claude", tags=["claude"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])
app.include_router(schwab_oauth.router, tags=["schwab"])  # No prefix - callback must be at root /callback


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "message": "Authentication required. Login at /auth/login",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server at {settings.API_HOST}:{settings.API_PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
