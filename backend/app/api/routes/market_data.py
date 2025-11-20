"""
Market Data API Routes
Endpoints for importing and managing historical market data
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import get_db
from app.repositories.market_data_repository import MarketDataRepository
from app.services.csv_import_service import csv_import_service
from app.api.middleware.auth import get_current_user, get_admin_user
from app.logger import logger

router = APIRouter(prefix="/api/market-data", tags=["Market Data"])


class ImportCSVRequest(BaseModel):
    """CSV import configuration"""
    symbol: str = Field(..., min_length=1, max_length=10)
    date_format: str = Field(default="%Y-%m-%d")
    time_format: str = Field(default="%H:%M:%S")
    skip_header: bool = Field(default=True)
    skip_duplicates: bool = Field(default=True)


class ImportResponse(BaseModel):
    """Import result"""
    success: bool
    message: str
    total_rows: int
    imported: int
    symbol: str
    date_range: Optional[Dict] = None
    quality_score: Optional[float] = None
    missing_bars: Optional[int] = None


class DataQualityResponse(BaseModel):
    """Data quality metrics"""
    symbol: str
    total_bars: int
    expected_bars: int
    missing_bars: int
    duplicate_timestamps: int
    quality_score: float
    date_range: Optional[Dict] = None


class SymbolInfo(BaseModel):
    """Symbol information"""
    symbol: str
    bar_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/import", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def import_csv_file(
    file: UploadFile = File(..., description="CSV file with OHLCV data"),
    symbol: str = Form(..., description="Stock symbol"),
    date_format: str = Form(default="%Y-%m-%d", description="Date format"),
    time_format: str = Form(default="%H:%M:%S", description="Time format"),
    skip_header: bool = Form(default=True, description="Skip first row"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Import historical OHLCV data from CSV file
    
    **CSV Format (time can be HH:MM or HH:MM:SS):**
    ```
    Date,Time,Open,High,Low,Close,Volume
    2024-01-15,09:30:00,180.50,181.20,180.10,180.90,1000000
    2024-01-15,09:31,180.90,181.00,180.70,180.85,950000
    2024-01-15,09:32:00,180.85,180.95,180.60,180.75,850000
    ```
    
    **Authentication required.**
    """
    logger.info(f"CSV upload requested by {current_user['username']}: {file.filename} for {symbol}")
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    try:
        # Read file content
        content = await file.read()
        
        # Import CSV
        result = await csv_import_service.import_csv_from_bytes(
            session=session,
            file_content=content,
            symbol=symbol,
            filename=file.filename,
            date_format=date_format,
            time_format=time_format,
            skip_header=skip_header
        )
        
        return ImportResponse(**result)
        
    except Exception as e:
        logger.error(f"CSV import error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}"
        )


@router.get("/symbols", response_model=List[SymbolInfo])
async def list_symbols(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get list of all symbols in database with statistics
    
    **Authentication required.**
    """
    symbols = await MarketDataRepository.get_symbols(session)
    
    result = []
    for symbol in symbols:
        count = await MarketDataRepository.get_bar_count(session, symbol)
        start_date, end_date = await MarketDataRepository.get_date_range(session, symbol)
        
        result.append(SymbolInfo(
            symbol=symbol,
            bar_count=count,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None
        ))
    
    return result


@router.get("/quality/{symbol}", response_model=DataQualityResponse)
async def check_data_quality(
    symbol: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Check data quality for a symbol
    
    **Authentication required.**
    """
    quality = await MarketDataRepository.check_data_quality(session, symbol.upper())
    
    if quality['total_bars'] == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for symbol {symbol}"
        )
    
    return DataQualityResponse(symbol=symbol.upper(), **quality)


@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = 1000,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Get market data bars for a symbol
    
    **Authentication required.**
    
    Args:
        symbol: Stock symbol
        start_date: Filter bars after this date (ISO format)
        end_date: Filter bars before this date (ISO format)
        limit: Maximum number of bars (default: 1000, max: 10000)
    """
    if limit and limit > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 10000"
        )
    
    bars = await MarketDataRepository.get_bars_by_symbol(
        session=session,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    if not bars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for symbol {symbol}"
        )
    
    return {
        "symbol": symbol.upper(),
        "count": len(bars),
        "bars": [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume
            }
            for bar in bars
        ]
    }


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_symbol_data(
    symbol: str,
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Delete all market data for a symbol (admin only)
    
    **Admin authentication required.**
    """
    deleted = await MarketDataRepository.delete_bars_by_symbol(session, symbol)
    
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for symbol {symbol}"
        )
    
    logger.info(f"Admin {admin_user['username']} deleted {deleted} bars for {symbol}")
    
    return None


@router.delete("/all/delete-everything", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_data(
    confirm: str = Form(..., description="Must be 'DELETE_ALL' to confirm"),
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Delete ALL market data from database (admin only, requires confirmation)
    
    **Admin authentication required.**
    **Confirmation required: Set confirm='DELETE_ALL'**
    """
    if confirm != "DELETE_ALL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation failed. Set confirm='DELETE_ALL' to proceed."
        )
    
    deleted = await MarketDataRepository.delete_all_bars(session)
    
    logger.warning(
        f"Admin {admin_user['username']} deleted ALL market data: {deleted} bars"
    )
    
    return None
