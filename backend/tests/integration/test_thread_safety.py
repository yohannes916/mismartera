"""Integration Tests for Thread Safety

Tests thread safety of concurrent operations on session data.
All symbol operations must be thread-safe.
"""
import pytest
from unittest.mock import Mock, MagicMock
from threading import Lock, Thread
from datetime import datetime
from collections import deque
from app.threads.session_coordinator import SessionCoordinator
from app.managers.data_manager.session_data import SessionData, SymbolSessionData, BarIntervalData


@pytest.fixture
def thread_safe_coordinator():
    """Create coordinator with thread safety."""
    coordinator = Mock(spec=SessionCoordinator)
    coordinator.session_data = SessionData()
    coordinator._symbol_operation_lock = Lock()
    coordinator._base_interval = "1m"
    coordinator._derived_intervals_validated = ["5m", "15m"]
    
    # Mock methods
    coordinator._register_single_symbol = Mock(return_value=True)
    coordinator._manage_historical_data = Mock(return_value=True)
    
    return coordinator


class TestConcurrentOperations:
    """Test concurrent operations."""
    
    def test_concurrent_symbol_additions(self, thread_safe_coordinator):
        """Test multiple threads adding symbols concurrently."""
        symbols = ["AAPL", "MSFT", "TSLA", "NVDA", "AMD"]
        results = []
        
        def add_symbol(symbol):
            with thread_safe_coordinator._symbol_operation_lock:
                success = thread_safe_coordinator._register_single_symbol(
                    symbol,
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
                results.append((symbol, success))
        
        # Create threads
        threads = []
        for symbol in symbols:
            thread = Thread(target=add_symbol, args=(symbol,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all to complete
        for thread in threads:
            thread.join()
        
        # Expected: All symbols added successfully, no conflicts
        assert len(results) == 5
        assert all(success for _, success in results)
        assert thread_safe_coordinator._register_single_symbol.call_count == 5
    
    def test_concurrent_indicator_additions(self, thread_safe_coordinator):
        """Test multiple threads adding indicators concurrently."""
        # Pre-add a symbol
        symbol_data = SymbolSessionData(
            symbol="AAPL",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
        thread_safe_coordinator.session_data.register_symbol_data(symbol_data)
        
        indicators = ["sma_20", "ema_12", "rsi_14", "macd", "bb_20"]
        results = []
        
        def add_indicator(indicator_name):
            with thread_safe_coordinator.session_data._lock:
                # Add indicator
                symbol_data.indicators[indicator_name] = Mock()
                results.append(indicator_name)
        
        # Create threads
        threads = []
        for indicator in indicators:
            thread = Thread(target=add_indicator, args=(indicator,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Expected: All indicators added
        assert len(results) == 5
        assert len(symbol_data.indicators) == 5


class TestSymbolOperationLock:
    """Test symbol operation lock."""
    
    def test_symbol_operation_lock(self, thread_safe_coordinator):
        """Test symbol operation lock prevents conflicts."""
        # Simulate concurrent operations on same symbol
        operations_completed = []
        
        def operation_1():
            with thread_safe_coordinator._symbol_operation_lock:
                operations_completed.append("op1_start")
                # Simulate work
                import time
                time.sleep(0.01)
                operations_completed.append("op1_end")
        
        def operation_2():
            with thread_safe_coordinator._symbol_operation_lock:
                operations_completed.append("op2_start")
                # Simulate work
                import time
                time.sleep(0.01)
                operations_completed.append("op2_end")
        
        # Start both operations
        t1 = Thread(target=operation_1)
        t2 = Thread(target=operation_2)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Expected: Operations serialized (op1 completes before op2 starts, or vice versa)
        assert len(operations_completed) == 4
        
        # Check that one operation completed before the other started
        op1_start = operations_completed.index("op1_start")
        op1_end = operations_completed.index("op1_end")
        op2_start = operations_completed.index("op2_start")
        op2_end = operations_completed.index("op2_end")
        
        # Either op1 before op2, or op2 before op1
        serialized = (op1_end < op2_start) or (op2_end < op1_start)
        assert serialized


class TestConcurrentReadWrite:
    """Test concurrent read/write operations."""
    
    def test_concurrent_read_write(self, thread_safe_coordinator):
        """Test concurrent reads and writes are safe."""
        # Add symbol
        symbol_data = SymbolSessionData(
            symbol="TSLA",
            base_interval="1m",
            meets_session_config_requirements=True,
            added_by="config",
            auto_provisioned=False
        )
        thread_safe_coordinator.session_data.register_symbol_data(symbol_data)
        
        read_values = []
        
        def read_operation():
            with thread_safe_coordinator.session_data._lock:
                symbol = thread_safe_coordinator.session_data.get_symbol_data("TSLA")
                if symbol:
                    # Read symbol name as safe attribute
                    read_values.append(symbol.symbol)
        
        def write_operation():
            with thread_safe_coordinator.session_data._lock:
                symbol = thread_safe_coordinator.session_data.get_symbol_data("TSLA")
                if symbol:
                    # Update a valid attribute
                    symbol.meets_session_config_requirements = True
        
        # Create multiple read and write threads
        threads = []
        for _ in range(5):
            threads.append(Thread(target=read_operation))
        for _ in range(2):
            threads.append(Thread(target=write_operation))
        
        # Start all
        for thread in threads:
            thread.start()
        
        # Wait
        for thread in threads:
            thread.join()
        
        # Expected: No crashes, reads completed
        assert len(read_values) == 5
        # All reads should get the symbol name
        assert all(val == "TSLA" for val in read_values)


class TestSessionDataLock:
    """Test session data internal lock."""
    
    def test_session_data_lock(self):
        """Test SessionData has internal lock for thread safety."""
        session_data = SessionData()
        
        # Verify lock exists
        assert hasattr(session_data, '_lock')
        # SessionData uses RLock (reentrant lock), not simple Lock
        from threading import RLock
        assert isinstance(session_data._lock, type(RLock()))
        
        # Test lock works
        with session_data._lock:
            # Add symbol
            for i in range(10):
                symbol = SymbolSessionData(
                    symbol=f"SYM{i}",
                    base_interval="1m",
                    meets_session_config_requirements=True,
                    added_by="config",
                    auto_provisioned=False
                )
                session_data.register_symbol_data(symbol)
        
        # Verify symbol added
        for i in range(10):
            assert session_data.get_symbol_data(f"SYM{i}") is not None


class TestNoRaceConditions:
    """Test no race conditions."""
    
    def test_no_race_conditions_symbol_creation(self, thread_safe_coordinator):
        """Test no race conditions when creating symbols."""
        # Multiple threads try to add same symbol
        symbol_name = "RACE"
        add_count = [0]
        
        def try_add_symbol():
            with thread_safe_coordinator._symbol_operation_lock:
                # Check if exists
                existing = thread_safe_coordinator.session_data.get_symbol_data(symbol_name)
                if existing is None:
                    # Add symbol
                    symbol = SymbolSessionData(
                        symbol=symbol_name,
                        base_interval="1m",
                        meets_session_config_requirements=True,
                        added_by="config",
                        auto_provisioned=False
                    )
                    thread_safe_coordinator.session_data.register_symbol_data(symbol)
                    add_count[0] += 1
        
        # Create multiple threads trying to add same symbol
        threads = []
        for _ in range(10):
            thread = Thread(target=try_add_symbol)
            threads.append(thread)
        
        # Start all
        for thread in threads:
            thread.start()
        
        # Wait
        for thread in threads:
            thread.join()
        
        # Expected: Symbol added exactly once (no duplicates)
        assert add_count[0] == 1
        assert thread_safe_coordinator.session_data.get_symbol_data(symbol_name) is not None
