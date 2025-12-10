"""Strategy configuration models."""
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class StrategyConfig:
    """Strategy configuration from session_config.
    
    Attributes:
        module: Python module path (e.g., "strategies.examples.simple_ma_cross")
        enabled: Whether strategy is enabled
        config: Strategy-specific configuration
    """
    module: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate strategy configuration."""
        if not self.module:
            raise ValueError("Strategy module path is required")
        
        # Module path validation (basic check)
        if not all(part.isidentifier() for part in self.module.split('.')):
            raise ValueError(f"Invalid module path: {self.module}")
