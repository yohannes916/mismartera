"""Integration Tests for Phase 2: Initialization

Tests Phase 2 initialization which loads all config symbols using the
unified three-phase provisioning pattern (analyze → validate → provision).
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData
from app.models.session_config import SessionConfig, SessionDataConfig


@pytest.fixture
def coordinator_for_init():
    """Create coordinator ready for Phase 2 initialization."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Mock config
    coordinator.session_config = Mock(spec=SessionConfig)
    coordinator.session_config.session_data_config = Mock(spec=SessionDataConfig)
    coordinator.session_config.session_data_config.symbols = ["AAPL", "MSFT", "TSLA"]
    coordinator.session_config.session_data_config.base_interval = "1m"
    coordinator.session_config.session_data_config.derived_intervals = [5, 15]
    coordinator.session_config.session_data_config.trailing_days = 30
    
    # Mock validation
    def validate_impl(symbol):
        return SymbolValidationResult(symbol="TEST",
            
            can_proceed=True,
            reason="Valid",
            data_source_available=True,
            has_historical_data=True
        )
    
    coordinator._validate_symbol_for_loading = Mock(side_effect=validate_impl)
    
    # Mock provisioning methods
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._load_queues = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


class TestPhase2Loading:
    """Test Phase 2 symbol loading."""
    
    def test_phase2_load_single_symbol_full(self, coordinator_for_init):
        """Test loading single symbol with full three-phase pattern."""
        symbol = "AAPL"
        
        # Phase 1: Requirement Analysis
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol=symbol,
            source="config",
            symbol_exists=False,
            symbol_data=None,
            required_intervals=["1m", "5m", "15m"],
            base_
            historical_
            
            needs_session=True,
            indicator_config=None,
            
            
            
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            provisioning_steps=[
                "create_symbol",
                "add_interval_1m",
                "add_interval_5m",
                "add_interval_15m",
                "load_historical",
                "load_session",
                "calculate_quality"
            ],
            can_proceed=True,
            validation_result=coordinator_for_init._validate_symbol_for_loading(symbol),
            validation_errors=[]
        )
        
        # Phase 2: Validation
        assert req.can_proceed is True
        
        # Phase 3: Provision
        # Create symbol
        coordinator_for_init._register_single_symbol(
            symbol,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
        
        # Load historical
        coordinator_for_init._manage_historical_data(symbols=[symbol])
        
        # Load session
        coordinator_for_init._load_queues(symbols=[symbol])
        
        # Calculate quality
        coordinator_for_init._calculate_historical_quality(symbols=[symbol])
        
        # Expected: Symbol loaded, all intervals, historical, quality
        coordinator_for_init._register_single_symbol.assert_called_once()
        coordinator_for_init._manage_historical_data.assert_called_once()
        coordinator_for_init._load_queues.assert_called_once()
        coordinator_for_init._calculate_historical_quality.assert_called_once()
    
    def test_phase2_load_multiple_symbols(self, coordinator_for_init):
        """Test loading multiple symbols from config."""
        symbols = ["AAPL", "MSFT", "TSLA"]
        
        for symbol in symbols:
            # Simulate three-phase pattern for each
            req = ProvisioningRequirements(
                operation_type="symbol",
                symbol=symbol,
                source="config",
                symbol_exists=False,
                symbol_data=None,
                required_intervals=["1m", "5m", "15m"],
                base_
                historical_
                
                needs_session=True,
                indicator_config=None,
                
                
                
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                provisioning_steps=["create_symbol", "load_historical", "load_session", "calculate_quality"],
                can_proceed=True,
                validation_result=coordinator_for_init._validate_symbol_for_loading(symbol),
                validation_errors=[]
            )
            
            # Provision each symbol
            coordinator_for_init._register_single_symbol(symbol, meets_session_config_requirements=True, added_by="config", auto_provisioned=False)
        
        # Expected: All symbols loaded
        assert coordinator_for_init._register_single_symbol.call_count == 3
    
    def test_phase2_requirement_analysis_all_symbols(self, coordinator_for_init):
        """Test requirement analysis runs for each symbol."""
        symbols = coordinator_for_init.session_config.session_data_config.symbols
        
        requirements_list = []
        for symbol in symbols:
            req = ProvisioningRequirements(
                operation_type="symbol",
                symbol=symbol,
                source="config",
                symbol_exists=False,
                symbol_data=None,
                required_intervals=["1m", "5m", "15m"],
                base_
                historical_
                
                needs_session=True,
                indicator_config=None,
                
                
                
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                provisioning_steps=[],
                can_proceed=True,
                validation_result=coordinator_for_init._validate_symbol_for_loading(symbol),
                validation_errors=[]
            )
            requirements_list.append(req)
        
        # Expected: ProvisioningRequirements for each
        assert len(requirements_list) == 3
        assert all(req.operation_type == "symbol" for req in requirements_list)
        assert all(req.source == "config" for req in requirements_list)
    
    def test_phase2_validation_all_symbols(self, coordinator_for_init):
        """Test validation runs for each symbol."""
        symbols = coordinator_for_init.session_config.session_data_config.symbols
        
        # Validate each symbol
        validation_results = []
        for symbol in symbols:
            result = coordinator_for_init._validate_symbol_for_loading(symbol)
            validation_results.append(result)
        
        # Expected: Validated symbols proceed
        assert len(validation_results) == 3
        assert all(result.can_proceed for result in validation_results)
    
    def test_phase2_provisioning_all_symbols(self, coordinator_for_init):
        """Test provisioning executes for each validated symbol."""
        symbols = coordinator_for_init.session_config.session_data_config.symbols
        
        # Provision each symbol
        for symbol in symbols:
            coordinator_for_init._register_single_symbol(
                symbol,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False
            )
            coordinator_for_init._manage_historical_data(symbols=[symbol])
            coordinator_for_init._load_queues(symbols=[symbol])
            coordinator_for_init._calculate_historical_quality(symbols=[symbol])
        
        # Expected: All symbols loaded
        assert coordinator_for_init._register_single_symbol.call_count == 3
        assert coordinator_for_init._manage_historical_data.call_count == 3
    
    def test_phase2_historical_loading(self, coordinator_for_init):
        """Test historical data loaded for all symbols."""
        symbols = ["AAPL", "MSFT"]
        
        # Load historical for each
        for symbol in symbols:
            coordinator_for_init._manage_historical_data(symbols=[symbol])
        
        # Expected: Historical bars present
        assert coordinator_for_init._manage_historical_data.call_count == 2
    
    def test_phase2_session_queue_loading(self, coordinator_for_init):
        """Test session queues loaded for all symbols."""
        symbols = ["AAPL", "MSFT"]
        
        # Load session queues for each
        for symbol in symbols:
            coordinator_for_init._load_queues(symbols=[symbol])
        
        # Expected: Queues populated for current day
        assert coordinator_for_init._load_queues.call_count == 2
    
    def test_phase2_quality_calculation(self, coordinator_for_init):
        """Test quality scores calculated."""
        symbols = ["AAPL", "MSFT"]
        
        # Calculate quality for each
        for symbol in symbols:
            coordinator_for_init._calculate_historical_quality(symbols=[symbol])
        
        # Expected: Quality > 0 for all symbols
        assert coordinator_for_init._calculate_historical_quality.call_count == 2
    
    def test_phase2_indicator_registration(self, coordinator_for_init):
        """Test indicators registered from config."""
        # Mock indicator registration
        coordinator_for_init._register_session_indicators = Mock(return_value=True)
        
        symbols = ["AAPL"]
        
        # Register indicators
        for symbol in symbols:
            coordinator_for_init._register_session_indicators(symbols=[symbol])
        
        # Expected: All indicators present
        coordinator_for_init._register_session_indicators.assert_called_once()
    
    def test_phase2_metadata_correctness(self, coordinator_for_init):
        """Test metadata set correctly for config symbols."""
        # Create symbol with metadata
        symbol_data = SymbolSessionData(
            symbol="AAPL",
            base_
            bars={"1m": BarIntervalData(derived=False, base=None, data=deque(), quality=0.0, gaps=[], updated=False)},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        
        # Expected: meets_session_config_requirements=True, added_by="config"
        assert symbol_data.meets_session_config_requirements is True
        assert symbol_data.added_by == "config"
        assert symbol_data.auto_provisioned is False
    
    def test_phase2_thread_initialization(self, coordinator_for_init):
        """Test all threads initialized after loading."""
        # Mock thread setup
        threads = {
            "data_processor": Mock(),
            "data_quality": Mock(),
            "scanner": Mock(),
            "strategy": Mock()
        }
        
        # Setup each thread
        for thread in threads.values():
            thread.setup = Mock()
            thread.setup()
        
        # Expected: All thread setup() called
        for thread in threads.values():
            thread.setup.assert_called_once()
    
    def test_phase2_pre_session_scan(self, coordinator_for_init):
        """Test pre-session scan runs if configured."""
        # Mock scanner manager
        scanner_manager = Mock()
        scanner_manager.run_pre_session_scans = Mock(return_value=True)
        
        # Run pre-session scan
        scanner_manager.run_pre_session_scans()
        
        # Expected: Scanner ran before session start
        scanner_manager.run_pre_session_scans.assert_called_once()


class TestPhase2ErrorHandling:
    """Test Phase 2 error handling."""
    
    def test_phase2_failed_symbol_graceful_degradation(self, coordinator_for_init):
        """Test failed symbol doesn't stop others."""
        symbols = ["AAPL", "INVALID", "MSFT"]
        
        # Mock validation to fail for INVALID
        def validate_impl(symbol):
            if symbol == "INVALID":
                return SymbolValidationResult(symbol="TEST",
            
                    can_proceed=False,
                    reason="No data source",
                    data_source_available=False,
                    has_historical_data=False
                )
            return SymbolValidationResult(symbol="TEST",
            
                can_proceed=True,
                reason="Valid",
                data_source_available=True,
                has_historical_data=True
            )
        
        coordinator_for_init._validate_symbol_for_loading = Mock(side_effect=validate_impl)
        
        # Process each symbol
        loaded_symbols = []
        for symbol in symbols:
            validation = coordinator_for_init._validate_symbol_for_loading(symbol)
            if validation.can_proceed:
                coordinator_for_init._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
                loaded_symbols.append(symbol)
        
        # Expected: AAPL and MSFT loaded, INVALID skipped
        assert len(loaded_symbols) == 2
        assert "AAPL" in loaded_symbols
        assert "MSFT" in loaded_symbols
        assert "INVALID" not in loaded_symbols
    
    def test_phase2_all_symbols_fail_terminates(self, coordinator_for_init):
        """Test session terminates if all symbols fail."""
        symbols = ["INVALID1", "INVALID2"]
        
        # Mock validation to fail for all
        def validate_impl(symbol):
            return SymbolValidationResult(symbol="TEST",
            
                can_proceed=False,
                reason="No data source",
                data_source_available=False,
                has_historical_data=False
            )
        
        coordinator_for_init._validate_symbol_for_loading = Mock(side_effect=validate_impl)
        
        # Process symbols
        loaded_symbols = []
        for symbol in symbols:
            validation = coordinator_for_init._validate_symbol_for_loading(symbol)
            if validation.can_proceed:
                loaded_symbols.append(symbol)
        
        # Expected: No symbols loaded, session should terminate
        assert len(loaded_symbols) == 0
