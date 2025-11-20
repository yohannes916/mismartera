"""
Claude AI API Endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from app.integrations.claude_client import claude_client
from app.api.middleware.auth import get_current_user, get_admin_user
from app.services.claude_usage_tracker import usage_tracker
from app.logger import logger

router = APIRouter(prefix="/api/claude", tags=["Claude AI"])


class PromptRequest(BaseModel):
    """Simple prompt request"""
    prompt: str = Field(..., description="Question or prompt for Claude")
    max_tokens: Optional[int] = Field(2048, description="Maximum tokens in response")
    temperature: Optional[float] = Field(0.7, description="Temperature (0.0-1.0)")


class PromptResponse(BaseModel):
    """Prompt response"""
    response: str
    model: str
    tokens_used: int
    username: str


class AnalysisRequest(BaseModel):
    """Stock analysis request"""
    symbol: str = Field(..., description="Stock symbol to analyze")
    analysis_type: str = Field("technical", description="technical, fundamental, sentiment, or comprehensive")
    market_data: Dict[str, Any] = Field({}, description="Optional market data")


class AnalysisResponse(BaseModel):
    """Analysis response"""
    symbol: str
    analysis_type: str
    analysis: str
    model: str
    tokens_used: int


@router.post("/ask", response_model=PromptResponse)
async def ask_claude(
    request: PromptRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Ask Claude a question
    
    Requires authentication.
    
    Args:
        request: Prompt request
        current_user: Authenticated user
        
    Returns:
        Claude's response
    """
    if not claude_client.client:
        raise HTTPException(
            status_code=503,
            detail="Claude API not configured. Please set ANTHROPIC_API_KEY in .env"
        )
    
    logger.info(f"Claude prompt from {current_user['username']}: {request.prompt[:50]}...")
    
    try:
        response = await claude_client.client.messages.create(
            model=claude_client.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=[
                {
                    "role": "user",
                    "content": request.prompt
                }
            ]
        )
        
        response_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        tokens_used = input_tokens + output_tokens
        
        # Track usage
        usage_tracker.record_usage(
            username=current_user['username'],
            operation="ask",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=claude_client.model
        )
        
        logger.success(f"Claude response generated ({tokens_used} tokens)")
        
        return PromptResponse(
            response=response_text,
            model=claude_client.model,
            tokens_used=tokens_used,
            username=current_user['username']
        )
        
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_stock(
    request: AnalysisRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Analyze a stock using Claude AI
    
    Requires authentication.
    
    Args:
        request: Analysis request
        current_user: Authenticated user
        
    Returns:
        Stock analysis
    """
    if not claude_client.client:
        raise HTTPException(
            status_code=503,
            detail="Claude API not configured. Please set ANTHROPIC_API_KEY in .env"
        )
    
    logger.info(f"Stock analysis request from {current_user['username']}: {request.symbol}")
    
    try:
        # If no market data provided, use placeholder
        if not request.market_data:
            request.market_data = {
                "note": "No market data provided. Using Claude's knowledge base."
            }
        
        result = await claude_client.analyze_stock(
            symbol=request.symbol,
            market_data=request.market_data,
            analysis_type=request.analysis_type
        )
        
        # Track usage
        usage_tracker.record_usage(
            username=current_user['username'],
            operation=f"analyze_{request.analysis_type}",
            input_tokens=result["tokens_used"] // 2,  # Rough estimate
            output_tokens=result["tokens_used"] // 2,
            model=claude_client.model
        )
        
        return AnalysisResponse(
            symbol=result["symbol"],
            analysis_type=result["analysis_type"],
            analysis=result["analysis"],
            model=result["model"],
            tokens_used=result["tokens_used"]
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/config")
async def get_claude_config(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get Claude configuration (does not expose API key)
    
    Args:
        current_user: Authenticated user
        
    Returns:
        Configuration status
    """
    return {
        "configured": claude_client.client is not None,
        "model": claude_client.model if claude_client.client else None,
        "status": "ready" if claude_client.client else "not_configured"
    }


@router.get("/usage")
async def get_usage(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get Claude API usage statistics for current user
    
    Args:
        current_user: Authenticated user
        
    Returns:
        User's usage statistics
    """
    stats = usage_tracker.get_user_stats(current_user['username'])
    return stats


@router.get("/usage/global")
async def get_global_usage(
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get global Claude API usage statistics (admin only)
    
    Args:
        admin_user: Authenticated admin user
        
    Returns:
        Global usage statistics
    """
    stats = usage_tracker.get_global_stats()
    return stats


@router.get("/usage/history")
async def get_usage_history(
    limit: int = 10,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get recent usage history for current user
    
    Args:
        limit: Maximum number of records to return
        current_user: Authenticated user
        
    Returns:
        Recent usage history
    """
    history = usage_tracker.get_recent_history(
        limit=limit,
        username=current_user['username']
    )
    return {"history": history, "count": len(history)}
