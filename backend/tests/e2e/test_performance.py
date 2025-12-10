"""E2E Performance Tests

Tests performance benchmarks for the unified provisioning architecture.
These tests measure speed and scalability of various operations.
"""
import pytest
import time
from unittest.mock import Mock
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator, ProvisioningRequirements, SymbolValidationResult
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def performance_setup():
    """Setup for performance testing."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Mock methods with minimal overhead
    coordinator._validate_symbol_for_loading = Mock(return_value=SymbolValidationResult(symbol="TEST",
            
        can_proceed=True, reason="Valid", data_source_available=True))
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    coordinator._calculate_historical_quality = Mock(return_value=True)
    
    return coordinator


@pytest.mark.e2e
@pytest.mark.performance
class TestProvisioningSpeed:
    """Test provisioning speed."""
    
    def test_single_symbol_speed(self, performance_setup):
        """Test single symbol provisioning completes quickly."""
        coordinator = performance_setup
        
        start = time.time()
        
        # Create requirement
        req = ProvisioningRequirements(
            operation_type="symbol",
            symbol="AAPL",
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
            provisioning_steps=["create_symbol", "load_historical", "calculate_quality"],
            can_proceed=True,
            validation_result=coordinator._validate_symbol_for_loading("AAPL"),
            validation_errors=[]
        )
        
        # Execute provisioning
        coordinator._register_single_symbol("AAPL", meets_session_config_requirements=True,
                                           added_by="config", auto_provisioned=False)
        coordinator._manage_historical_data(symbols=["AAPL"])
        coordinator._calculate_historical_quality(symbols=["AAPL"])
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 0.1 seconds for single symbol (with mocks)
        assert elapsed < 0.1
        print(f"Single symbol provisioning: {elapsed*1000:.2f}ms")
    
    def test_10_symbols_loading(self, performance_setup):
        """Test loading 10 symbols."""
        coordinator = performance_setup
        
        symbols = [f"SYM{i}" for i in range(10)]
        
        start = time.time()
        
        for symbol in symbols:
            coordinator._register_single_symbol(symbol, meets_session_config_requirements=True,
                                               added_by="config", auto_provisioned=False)
            coordinator._manage_historical_data(symbols=[symbol])
            coordinator._calculate_historical_quality(symbols=[symbol])
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 1 second for 10 symbols (with mocks)
        assert elapsed < 1.0
        print(f"10 symbols loading: {elapsed*1000:.2f}ms ({elapsed*100:.2f}ms per symbol)")
    
    def test_20_symbols_loading(self, performance_setup):
        """Test loading 20 symbols."""
        coordinator = performance_setup
        
        symbols = [f"SYM{i}" for i in range(20)]
        
        start = time.time()
        
        for symbol in symbols:
            coordinator._register_single_symbol(symbol, meets_session_config_requirements=True,
                                               added_by="config", auto_provisioned=False)
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 2 seconds for 20 symbols (with mocks)
        assert elapsed < 2.0
        print(f"20 symbols loading: {elapsed*1000:.2f}ms ({elapsed*50:.2f}ms per symbol)")
    
    def test_50_symbols_stress_test(self, performance_setup):
        """Test stress test with 50 symbols."""
        coordinator = performance_setup
        
        symbols = [f"SYM{i}" for i in range(50)]
        
        start = time.time()
        
        for symbol in symbols:
            coordinator._register_single_symbol(symbol, meets_session_config_requirements=True,
                                               added_by="config", auto_provisioned=False)
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 5 seconds for 50 symbols (with mocks)
        assert elapsed < 5.0
        print(f"50 symbols stress test: {elapsed*1000:.2f}ms ({elapsed*20:.2f}ms per symbol)")


@pytest.mark.e2e
@pytest.mark.performance
class TestOperationSpeed:
    """Test individual operation speeds."""
    
    def test_adhoc_addition_speed(self, performance_setup):
        """Test adhoc symbol addition speed."""
        coordinator = performance_setup
        
        start = time.time()
        
        # Adhoc addition (minimal provisioning)
        coordinator._register_single_symbol("ADHOC", meets_session_config_requirements=False,
                                           added_by="scanner", auto_provisioned=True)
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 0.05 seconds (adhoc should be faster than full)
        assert elapsed < 0.05
        print(f"Adhoc addition: {elapsed*1000:.2f}ms")
    
    def test_upgrade_speed(self, performance_setup):
        """Test upgrade from adhoc to full speed."""
        coordinator = performance_setup
        session_data = coordinator.session_data
        
        # Create adhoc symbol
        adhoc = SymbolSessionData(
            symbol="UPGRADE",
            base_
            bars={},
            indicators={},
            quality=0.0,
            session_metrics=None,
            meets_session_config_requirements=False,
            added_by="scanner",
            auto_provisioned=True,
            upgraded_from_adhoc=False,
            added_at=datetime.now()
        )
        session_data.register_symbol_data(adhoc)
        
        start = time.time()
        
        # Upgrade
        adhoc.meets_session_config_requirements = True
        adhoc.upgraded_from_adhoc = True
        coordinator._manage_historical_data(symbols=["UPGRADE"])
        coordinator._calculate_historical_quality(symbols=["UPGRADE"])
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 0.1 seconds for upgrade
        assert elapsed < 0.1
        print(f"Upgrade speed: {elapsed*1000:.2f}ms")
    
    def test_requirement_analysis_speed(self, performance_setup):
        """Test requirement analysis speed."""
        coordinator = performance_setup
        
        start = time.time()
        
        # Analyze 100 requirements
        for i in range(100):
            req = ProvisioningRequirements(
                operation_type="symbol",
                symbol=f"SYM{i}",
                source="config",
                symbol_exists=False,
                symbol_data=None,
                required_intervals=["1m", "5m"],
                base_
                historical_
                
                needs_session=True,
                indicator_config=None,
                
                
                
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                provisioning_steps=[],
                can_proceed=True,
                validation_result=coordinator._validate_symbol_for_loading(f"SYM{i}"),
                validation_errors=[]
            )
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 0.5 seconds for 100 requirement analyses
        assert elapsed < 0.5
        print(f"100 requirement analyses: {elapsed*1000:.2f}ms ({elapsed*10:.2f}ms each)")


@pytest.mark.e2e
@pytest.mark.performance
class TestScalability:
    """Test system scalability."""
    
    def test_concurrent_operations(self, performance_setup):
        """Test concurrent symbol operations."""
        from threading import Thread
        
        coordinator = performance_setup
        results = []
        
        def add_symbol(symbol):
            coordinator._register_single_symbol(symbol, meets_session_config_requirements=True,
                                               added_by="config", auto_provisioned=False)
            results.append(symbol)
        
        start = time.time()
        
        # Create 10 threads
        threads = []
        for i in range(10):
            thread = Thread(target=add_symbol, args=(f"CONCURRENT{i}"))
            threads.append(thread)
            thread.start()
        
        # Wait for all
        for thread in threads:
            thread.join()
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 1 second for 10 concurrent operations
        assert elapsed < 1.0
        assert len(results) == 10
        print(f"10 concurrent operations: {elapsed*1000:.2f}ms")
    
    def test_multi_day_many_symbols(self, performance_setup):
        """Test multi-day backtest with many symbols."""
        coordinator = performance_setup
        
        days = 5
        symbols_per_day = 20
        
        start = time.time()
        
        for day in range(days):
            coordinator.session_data = SessionData()
            
            for sym_num in range(symbols_per_day):
                coordinator._register_single_symbol(
                    f"D{day}_S{sym_num}",
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
            
            coordinator.session_data.clear()
        
        end = time.time()
        elapsed = end - start
        
        # Target: < 5 seconds for 5 days * 20 symbols = 100 operations
        assert elapsed < 5.0
        print(f"5 days × 20 symbols: {elapsed*1000:.2f}ms")
    
    def test_memory_usage(self, performance_setup):
        """Test memory usage with many symbols."""
        import sys
        
        coordinator = performance_setup
        session_data = coordinator.session_data
        
        # Measure baseline
        baseline = sys.getsizeof(session_data)
        
        # Add 50 symbols
        for i in range(50):
            symbol = SymbolSessionData(
                symbol=f"MEM{i}",
                base_
                bars={"1m": BarIntervalData(derived=False, base=None, data=deque(),
                                           quality=0.0, gaps=[], updated=False)},
                indicators={},
                quality=0.0,
                session_metrics=None,
                meets_session_config_requirements=True,
                added_by="config",
                auto_provisioned=False,
                upgraded_from_adhoc=False,
                added_at=datetime.now()
            )
            session_data.register_symbol_data(symbol)
        
        # Measure with symbols
        with_symbols = sys.getsizeof(session_data)
        
        # Memory increase should be reasonable
        increase = with_symbols - baseline
        
        # Just verify it completes without memory issues
        assert len(session_data.symbols) == 50
        print(f"Memory increase for 50 symbols: {increase} bytes")
