"""Scanner Base Classes

Defines the base scanner interface and supporting classes for the
dynamic symbol scanning framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.logger import logger


@dataclass
class ScanContext:
    """Context provided to scanner methods.
    
    Provides access to session data and system components.
    
    Attributes:
        session_data: SessionData instance for data access and manipulation
        time_manager: TimeManager instance for time operations
        mode: Execution mode ("backtest" or "live")
        current_time: Current time (simulated in backtest, real in live)
        config: Scanner-specific configuration from session config
    """
    session_data: Any  # SessionData
    time_manager: Any  # TimeManager
    mode: str
    current_time: datetime
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Result of a scan operation.
    
    Attributes:
        symbols: List of qualifying symbols found
        metadata: Optional metadata about the scan (counts, criteria, etc.)
        execution_time_ms: Time taken to execute scan in milliseconds
        skipped: Whether scan was skipped (previous scan still running)
        error: Error message if scan failed
    """
    symbols: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    skipped: bool = False
    error: Optional[str] = None


class BaseScanner(ABC):
    """Base class for all scanners.
    
    Scanners implement dynamic symbol discovery and provisioning.
    
    Lifecycle:
    1. setup() - Called once before session starts
       - Load universe from config
       - Provision lightweight data (indicators with auto-bars)
       
    2. scan() - Called on schedule (pre-session and/or regular session)
       - Query lightweight data
       - Find qualifying symbols
       - Promote to full symbols via add_symbol()
       
    3. teardown() - Called after last scheduled scan
       - Remove symbols that didn't qualify
       - Free resources
    
    Usage:
        class MyScanner(BaseScanner):
            def setup(self, context):
                # Load universe
                self._universe = self._load_universe_from_file(
                    context.config.get("universe")
                )
                
                # Provision lightweight data
                for symbol in self._universe:
                    context.session_data.add_indicator(symbol, "sma", {
                        "period": 20,
                        "interval": "1d"
                    })
                
                return True
            
            def scan(self, context):
                results = []
                
                for symbol in self._universe:
                    # Check criteria
                    if self._meets_criteria(symbol, context.session_data):
                        # Promote to full symbol
                        context.session_data.add_symbol(symbol)
                        results.append(symbol)
                
                return ScanResult(symbols=results)
            
            def teardown(self, context):
                # Remove unqualified symbols
                for symbol in self._universe:
                    if symbol not in qualifying_symbols:
                        context.session_data.remove_symbol_adhoc(symbol)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize scanner with configuration.
        
        Args:
            config: Scanner-specific configuration from session config
        """
        self.config = config
        self._universe: List[str] = []
        logger.info(f"[{self.__class__.__name__}] Initialized with config: {config}")
    
    def setup(self, context: ScanContext) -> bool:
        """Setup lightweight screening data for universe.
        
        Called once before session starts (or before first scan).
        
        Responsibilities:
        - Load universe from config
        - Provision lightweight data (add_indicator with auto-bars)
        - Register any needed resources
        
        Do NOT:
        - Promote symbols to full (use scan() for that)
        - Perform heavy data loading (keep it lightweight)
        
        Args:
            context: Scan context with session_data access
        
        Returns:
            True if setup successful, False otherwise
        """
        logger.info(f"[{self.__class__.__name__}] Default setup (no-op)")
        return True
    
    @abstractmethod
    def scan(self, context: ScanContext) -> ScanResult:
        """Scan universe and add qualifying symbols.
        
        Called on schedule (pre-session and/or regular session).
        
        Responsibilities:
        - Query lightweight data
        - Apply criteria to find qualifying symbols
        - Promote qualifying symbols via add_symbol() (idempotent)
        - Return results
        
        Note: add_symbol() is IDEMPOTENT - safe to call multiple times.
        
        Args:
            context: Scan context with session_data access
        
        Returns:
            ScanResult with qualifying symbols and metadata
        """
        pass
    
    def teardown(self, context: ScanContext) -> None:
        """Cleanup after scanner completes (no more schedules).
        
        Called after the last scheduled scan completes.
        
        Responsibilities:
        - Remove symbols that didn't qualify
        - Free resources
        - Cleanup temporary data
        
        Use remove_symbol_adhoc() which:
        - Checks if symbol is locked (position open)
        - Only removes if not locked and not a config symbol
        
        Args:
            context: Scan context with session_data access
        """
        logger.info(f"[{self.__class__.__name__}] Default teardown (no-op)")
    
    def _load_universe_from_file(self, file_path: str) -> List[str]:
        """Load universe symbols from text file (one per line).
        
        File format:
        - One symbol per line
        - Lines starting with # are comments
        - Blank lines ignored
        - Symbols automatically uppercased
        
        Args:
            file_path: Path to universe file (relative or absolute)
        
        Returns:
            List of symbols
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty or invalid
        
        Example:
            # data/universes/sp500.txt
            AAPL
            MSFT
            GOOGL
            # Tech stocks
            NVDA
            AMD
        """
        path = Path(file_path)
        
        # Handle relative paths (relative to backend directory)
        if not path.is_absolute():
            # Assume relative to backend directory
            backend_dir = Path(__file__).parent.parent
            path = backend_dir / file_path
        
        if not path.exists():
            raise FileNotFoundError(f"Universe file not found: {path}")
        
        symbols = []
        
        with open(path, 'r') as f:
            for line in f:
                # Strip whitespace
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Extract symbol (first word, uppercased)
                symbol = line.split()[0].upper()
                symbols.append(symbol)
        
        if not symbols:
            raise ValueError(f"No symbols found in universe file: {path}")
        
        logger.info(f"Loaded {len(symbols)} symbols from {path}")
        return symbols
    
    def _get_scanner_name(self) -> str:
        """Get scanner name from class name.
        
        Returns:
            Scanner name (e.g., "GapScanner" -> "gap_scanner")
        """
        # Convert CamelCase to snake_case
        name = self.__class__.__name__
        
        # Remove "Scanner" suffix if present
        if name.endswith("Scanner"):
            name = name[:-7]
        
        # Convert to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
        
        return name
