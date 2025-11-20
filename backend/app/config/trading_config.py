"""
Trading System Configuration
Includes configurable Claude AI usage parameters
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import app.config as config_module


class ClaudeUsageMode(str, Enum):
    """Claude AI usage modes"""
    NONE = "none"              # Never use Claude (traditional only)
    LOW = "low"                # Use Claude for 5% of bars (high uncertainty only)
    MEDIUM = "medium"          # Use Claude for 10% of bars (recommended)
    HIGH = "high"              # Use Claude for 20% of bars (aggressive)
    AGGRESSIVE = "aggressive"  # Use Claude for 50% of bars (very expensive)
    ALWAYS = "always"          # Use Claude for every bar (maximum cost)


class ClaudeConfig(BaseModel):
    """Claude AI usage configuration"""
    
    # Usage mode
    mode: ClaudeUsageMode = Field(
        default=ClaudeUsageMode.MEDIUM,
        description="How frequently to use Claude AI"
    )
    
    # Uncertainty threshold (0-1)
    # Use Claude when traditional model uncertainty exceeds this
    uncertainty_threshold: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Use Claude when uncertainty > this threshold"
    )
    
    # High stakes threshold (USD)
    # Use Claude for trades above this amount
    high_stakes_threshold: Optional[float] = Field(
        default=10000.0,
        description="Use Claude for positions above this value (USD)"
    )
    
    # Confidence threshold (0-1)
    # Use Claude when traditional confidence is below this
    min_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Use Claude when traditional confidence < this"
    )
    
    # Pattern complexity threshold (0-1)
    # Use Claude for complex patterns above this score
    pattern_complexity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Use Claude when pattern complexity > this"
    )
    
    # Weight for Claude probability in hybrid decision
    claude_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight given to Claude's probability (0=ignore, 1=only Claude)"
    )
    
    # Cost limit per day (USD)
    daily_cost_limit: Optional[float] = Field(
        default=50.0,
        description="Maximum Claude API cost per day (None=unlimited)"
    )
    
    # Enable caching for similar patterns
    enable_caching: bool = Field(
        default=True,
        description="Cache Claude responses for similar patterns"
    )
    
    # Batch size for API calls
    batch_size: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of bars to analyze per API call"
    )
    
    def get_usage_percentage(self) -> float:
        """Get expected Claude usage percentage based on mode"""
        usage_map = {
            ClaudeUsageMode.NONE: 0.0,
            ClaudeUsageMode.LOW: 5.0,
            ClaudeUsageMode.MEDIUM: 10.0,
            ClaudeUsageMode.HIGH: 20.0,
            ClaudeUsageMode.AGGRESSIVE: 50.0,
            ClaudeUsageMode.ALWAYS: 100.0
        }
        return usage_map[self.mode]
    
    def get_estimated_cost_per_day(self, bars_per_day: int = 390) -> float:
        """
        Estimate Claude API cost per day
        
        Args:
            bars_per_day: Number of 1-minute bars per day (default: 390 for 6.5hr trading day)
            
        Returns:
            Estimated cost in USD
        """
        usage_pct = self.get_usage_percentage()
        claude_calls = bars_per_day * (usage_pct / 100.0)
        cost_per_call = 0.15  # Average cost per Claude API call
        
        return claude_calls * cost_per_call
    
    def should_use_claude(
        self,
        traditional_confidence: float,
        uncertainty: float,
        pattern_complexity: float,
        position_size: Optional[float] = None,
        current_daily_cost: float = 0.0
    ) -> bool:
        """
        Determine if Claude should be used for this bar
        
        Args:
            traditional_confidence: Traditional model confidence (0-1)
            uncertainty: Signal uncertainty (0-1)
            pattern_complexity: Pattern complexity score (0-1)
            position_size: Trade position size in USD
            current_daily_cost: Current day's Claude API cost
            
        Returns:
            True if Claude should be used
        """
        # Check cost limit
        if self.daily_cost_limit and current_daily_cost >= self.daily_cost_limit:
            return False
        
        # Mode-based decision
        if self.mode == ClaudeUsageMode.NONE:
            return False
        
        if self.mode == ClaudeUsageMode.ALWAYS:
            return True
        
        # Evaluate conditions
        reasons_to_use_claude = 0
        
        # Low confidence
        if traditional_confidence < self.min_confidence_threshold:
            reasons_to_use_claude += 1
        
        # High uncertainty
        if uncertainty > self.uncertainty_threshold:
            reasons_to_use_claude += 1
        
        # Complex pattern
        if pattern_complexity > self.pattern_complexity_threshold:
            reasons_to_use_claude += 1
        
        # High stakes
        if position_size and self.high_stakes_threshold:
            if position_size >= self.high_stakes_threshold:
                reasons_to_use_claude += 2  # Double weight for high stakes
        
        # Decision based on mode
        if self.mode == ClaudeUsageMode.LOW:
            return reasons_to_use_claude >= 3  # Very selective
        
        elif self.mode == ClaudeUsageMode.MEDIUM:
            return reasons_to_use_claude >= 2  # Moderately selective
        
        elif self.mode == ClaudeUsageMode.HIGH:
            return reasons_to_use_claude >= 1  # Less selective
        
        elif self.mode == ClaudeUsageMode.AGGRESSIVE:
            return True  # Use for most cases
        
        return False


class TradingConfig(BaseModel):
    """Main trading configuration"""
    
    # Probability parameters
    profit_target_pct: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Target profit percentage"
    )
    
    stop_loss_pct: float = Field(
        default=0.5,
        ge=0.1,
        le=5.0,
        description="Stop-loss percentage"
    )
    
    risk_limit_pct: float = Field(
        default=70.0,
        ge=50.0,
        le=95.0,
        description="Force exit if stop-loss probability exceeds this"
    )
    
    # Claude configuration
    claude: ClaudeConfig = Field(
        default_factory=ClaudeConfig,
        description="Claude AI usage configuration"
    )
    
    # Backtesting
    backtest_start_date: Optional[str] = Field(
        default=None,
        description="Backtest start date (YYYY-MM-DD)"
    )
    
    backtest_end_date: Optional[str] = Field(
        default=None,
        description="Backtest end date (YYYY-MM-DD)"
    )
    
    # Position sizing
    max_position_size: float = Field(
        default=10000.0,
        description="Maximum position size in USD"
    )
    
    # Risk management
    max_daily_loss_pct: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Stop trading if daily loss exceeds this %"
    )


# Preset configurations
PRESET_CONFIGS = {
    "conservative": TradingConfig(
        profit_target_pct=0.5,
        stop_loss_pct=0.25,
        risk_limit_pct=65.0,
        claude=ClaudeConfig(
            mode=ClaudeUsageMode.HIGH,
            uncertainty_threshold=0.15,
            claude_weight=0.8
        )
    ),
    
    "balanced": TradingConfig(
        profit_target_pct=1.0,
        stop_loss_pct=0.5,
        risk_limit_pct=70.0,
        claude=ClaudeConfig(
            mode=ClaudeUsageMode.MEDIUM,
            uncertainty_threshold=0.2,
            claude_weight=0.7
        )
    ),
    
    "aggressive": TradingConfig(
        profit_target_pct=2.0,
        stop_loss_pct=1.0,
        risk_limit_pct=75.0,
        claude=ClaudeConfig(
            mode=ClaudeUsageMode.LOW,
            uncertainty_threshold=0.3,
            claude_weight=0.6
        )
    ),
    
    "traditional_only": TradingConfig(
        profit_target_pct=1.0,
        stop_loss_pct=0.5,
        risk_limit_pct=70.0,
        claude=ClaudeConfig(
            mode=ClaudeUsageMode.NONE
        )
    ),
    
    "claude_heavy": TradingConfig(
        profit_target_pct=1.0,
        stop_loss_pct=0.5,
        risk_limit_pct=70.0,
        claude=ClaudeConfig(
            mode=ClaudeUsageMode.AGGRESSIVE,
            uncertainty_threshold=0.1,
            claude_weight=0.9,
            daily_cost_limit=200.0
        )
    )
}


def load_config(preset: str = "balanced") -> TradingConfig:
    """
    Load a preset configuration
    
    Args:
        preset: Configuration preset name
        
    Returns:
        TradingConfig instance
    """
    if preset not in PRESET_CONFIGS:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESET_CONFIGS.keys())}")
    
    return PRESET_CONFIGS[preset]
