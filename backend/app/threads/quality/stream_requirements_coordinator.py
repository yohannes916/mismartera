"""Stream Requirements Coordinator

Coordinates requirement analysis and database validation for stream determination.
This is the integration module that brings together Phase 1 and Phase 2.

Key Principle:
    Validate BEFORE starting session. Fail fast with clear errors.

Requirements Covered:
    All requirements from Phase 1 (Req 1-12) and Phase 2 (Req 13-17)
    
Usage:
    coordinator = StreamRequirementsCoordinator(session_config, time_manager)
    result = coordinator.validate_requirements(data_checker)
    
    if result.valid:
        # Start session with result.required_base_interval
        pass
    else:
        # Display result.error_message and abort
        pass
"""

from typing import Optional, Callable
from datetime import date
from dataclasses import dataclass

from app.logger import logger
from app.threads.quality.requirement_analyzer import (
    analyze_session_requirements,
    validate_configuration,
    SessionRequirements
)
from app.threads.quality.database_validator import (
    validate_all_symbols,
    get_available_base_intervals
)


@dataclass
class ValidationResult:
    """Result of stream requirements validation.
    
    Attributes:
        valid: True if all requirements met, False otherwise
        required_base_interval: The base interval that must be streamed
        derivable_intervals: Intervals that will be generated
        symbols: List of symbols being validated
        error_message: None if valid, error details if not valid
        requirements: Full SessionRequirements object (for detailed inspection)
    """
    valid: bool
    required_base_interval: Optional[str]
    derivable_intervals: list[str]
    symbols: list[str]
    error_message: Optional[str]
    requirements: Optional[SessionRequirements]


class StreamRequirementsCoordinator:
    """Coordinates requirement analysis and database validation.
    
    This is the main integration point for stream determination logic.
    It combines the requirement analyzer (Phase 1) and database validator (Phase 2)
    to provide a single validation interface.
    
    Usage:
        coordinator = StreamRequirementsCoordinator(session_config, time_manager)
        result = coordinator.validate_requirements(data_checker)
        
        if not result.valid:
            logger.error(result.error_message)
            raise RuntimeError(result.error_message)
    """
    
    def __init__(self, session_config, time_manager):
        """Initialize coordinator.
        
        Args:
            session_config: Session configuration object
            time_manager: TimeManager instance (for date ranges)
        """
        self.session_config = session_config
        self.time_manager = time_manager
        
        # Extract config values
        self.symbols = session_config.session_data_config.symbols
        self.streams = session_config.session_data_config.streams
        self.mode = session_config.mode  # "backtest" or "live"
    
    def validate_requirements(
        self,
        data_checker: Optional[Callable[[str, str, date, date], int]] = None
    ) -> ValidationResult:
        """Validate all stream requirements.
        
        This is the main entry point. It:
        1. Validates configuration format
        2. Analyzes requirements to determine base interval
        3. Validates database has required data
        
        Args:
            data_checker: Callable that returns count of available bars
                         Signature: (symbol, interval, start_date, end_date) -> int
                         If None, database validation is skipped
        
        Returns:
            ValidationResult with validation status and details
            
        Examples:
            >>> # With data checker
            >>> result = coordinator.validate_requirements(my_data_checker)
            >>> if result.valid:
            ...     print(f"Stream {result.required_base_interval}")
            >>> else:
            ...     print(f"Error: {result.error_message}")
            
            >>> # Without data checker (config validation only)
            >>> result = coordinator.validate_requirements()
            >>> # Will check config but skip database validation
        """
        logger.info("=" * 70)
        logger.info("STREAM REQUIREMENTS VALIDATION")
        logger.info("=" * 70)
        
        # Step 1: Validate configuration format
        logger.info("Step 1/3: Validating configuration format...")
        try:
            validate_configuration(self.streams, self.mode)
            logger.info("✓ Configuration format valid")
        except ValueError as e:
            logger.error(f"✗ Configuration validation failed: {e}")
            return ValidationResult(
                valid=False,
                required_base_interval=None,
                derivable_intervals=[],
                symbols=self.symbols,
                error_message=f"Configuration error: {str(e)}",
                requirements=None
            )
        
        # Step 2: Analyze requirements
        logger.info("Step 2/3: Analyzing session requirements...")
        try:
            # Note: analyze_session_requirements only needs streams
            # Symbols are used for database validation (Step 3)
            requirements = analyze_session_requirements(self.streams)
            logger.info(f"✓ Required base interval: {requirements.required_base_interval}")
            logger.info(f"  Derivable intervals: {requirements.derivable_intervals}")
        except Exception as e:
            logger.error(f"✗ Requirement analysis failed: {e}")
            return ValidationResult(
                valid=False,
                required_base_interval=None,
                derivable_intervals=[],
                symbols=self.symbols,
                error_message=f"Requirement analysis error: {str(e)}",
                requirements=None
            )
        
        # Step 3: Validate database availability (if data_checker provided)
        if data_checker is None:
            logger.warning("⚠ Database validation skipped (no data_checker provided)")
            return ValidationResult(
                valid=True,
                required_base_interval=requirements.required_base_interval,
                derivable_intervals=requirements.derivable_intervals,
                symbols=self.symbols,
                error_message=None,
                requirements=requirements
            )
        
        logger.info("Step 3/3: Validating database availability...")
        
        # Get date range from TimeManager
        start_date = self.time_manager.backtest_start_date
        end_date = self.time_manager.backtest_end_date
        
        logger.info(f"  Date range: {start_date} to {end_date}")
        logger.info(f"  Symbols: {self.symbols}")
        logger.info(f"  Required interval: {requirements.required_base_interval}")
        
        # Validate all symbols have required data
        db_valid, db_error = validate_all_symbols(
            symbols=self.symbols,
            required_base_interval=requirements.required_base_interval,
            start_date=start_date,
            end_date=end_date,
            data_checker=data_checker
        )
        
        if not db_valid:
            logger.error(f"✗ Database validation failed")
            logger.error(f"  {db_error}")
            
            # Provide helpful diagnostics
            logger.info("  Checking available intervals for each symbol...")
            for symbol in self.symbols:
                available = get_available_base_intervals(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    data_checker=data_checker
                )
                if available:
                    logger.info(f"    {symbol}: {available} available")
                else:
                    logger.info(f"    {symbol}: No base intervals available")
            
            return ValidationResult(
                valid=False,
                required_base_interval=requirements.required_base_interval,
                derivable_intervals=requirements.derivable_intervals,
                symbols=self.symbols,
                error_message=db_error,
                requirements=requirements
            )
        
        logger.info("✓ Database validation passed")
        logger.info("=" * 70)
        logger.info(f"✓ ALL VALIDATION PASSED")
        logger.info(f"  Stream: {requirements.required_base_interval}")
        logger.info(f"  Generate: {requirements.derivable_intervals}")
        logger.info("=" * 70)
        
        return ValidationResult(
            valid=True,
            required_base_interval=requirements.required_base_interval,
            derivable_intervals=requirements.derivable_intervals,
            symbols=self.symbols,
            error_message=None,
            requirements=requirements
        )
    
    def get_validation_summary(self) -> dict:
        """Get a summary of validation configuration.
        
        Returns:
            Dictionary with validation parameters
        """
        return {
            "symbols": self.symbols,
            "streams": self.streams,
            "start_date": str(self.time_manager.backtest_start_date),
            "end_date": str(self.time_manager.backtest_end_date),
        }
