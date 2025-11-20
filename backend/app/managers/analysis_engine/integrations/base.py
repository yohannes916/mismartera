"""
Base interface for LLM integrations.
All LLM integrations must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM API"""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    cost_usd: float
    timestamp: datetime
    metadata: Dict[str, Any]


@dataclass
class LLMAnalysis:
    """Structured analysis from LLM"""
    buy_probability: float
    sell_probability: float
    stop_loss_risk: float
    confidence: float
    reasoning: str
    detected_patterns: List[str]
    key_indicators: List[str]
    risk_factors: List[str]
    llm_response: LLMResponse


class LLMInterface(ABC):
    """
    Abstract base class for LLM integrations.
    Ensures all LLM providers provide a consistent interface.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the LLM provider (e.g., 'claude', 'gpt4', 'gemini')"""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the specific model (e.g., 'claude-opus-4', 'gpt-4-turbo')"""
        pass
    
    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text from a prompt.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            LLMResponse object
        """
        pass
    
    @abstractmethod
    async def analyze_trading_opportunity(
        self,
        bar_data: Dict[str, Any],
        indicators: Dict[str, Any],
        recent_bars: Optional[List[Dict[str, Any]]] = None,
        profit_target_pct: float = 1.0,
        stop_loss_pct: float = 0.5
    ) -> LLMAnalysis:
        """
        Analyze a trading opportunity and provide probability estimates.
        
        Args:
            bar_data: Current bar data
            indicators: Technical indicators
            recent_bars: Recent historical bars for context
            profit_target_pct: Profit target percentage
            stop_loss_pct: Stop-loss percentage
            
        Returns:
            LLMAnalysis object with structured analysis
        """
        pass
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the LLM API is accessible.
        
        Returns:
            True if connection is valid
        """
        pass
    
    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost of an API call.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        pass
