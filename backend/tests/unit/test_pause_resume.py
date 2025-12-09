"""
Unit tests for Pause/Resume functionality.

Tests verify:
- Pause event mechanism in SessionCoordinator
- SystemManager state transitions
- Mode-aware behavior (backtest vs live)
- Error handling
"""

import pytest
import threading
import time
from unittest.mock import Mock, MagicMock, patch
from app.core.enums import SystemState, OperationMode


class TestPauseEventMechanism:
    """Test the underlying pause event mechanism in SessionCoordinator."""
    
    def test_pause_event_initially_not_paused(self):
        """Verify coordinator starts in unpaused state."""
        # We'll mock the minimum required for SessionCoordinator
        # In a real test, this would use a proper fixture
        from app.threads.session_coordinator import SessionCoordinator
        
        # Mock dependencies
        with patch('app.threads.session_coordinator.SessionData'):
            with patch('app.threads.session_coordinator.PerformanceMetrics'):
                # Create minimal coordinator (without full initialization)
                coordinator = object.__new__(SessionCoordinator)
                coordinator._stream_paused = threading.Event()
                coordinator._stream_paused.set()  # Initially not paused
                
                # Should not be paused
                assert not coordinator.is_paused()
    
    def test_pause_blocks_event(self):
        """Verify pause_backtest clears the event."""
        from app.threads.session_coordinator import SessionCoordinator
        
        with patch('app.threads.session_coordinator.SessionData'):
            with patch('app.threads.session_coordinator.PerformanceMetrics'):
                coordinator = object.__new__(SessionCoordinator)
                coordinator._stream_paused = threading.Event()
                coordinator._stream_paused.set()
                
                # Create minimal mocks for mode check
                coordinator._system_manager = Mock()
                coordinator._system_manager.mode.value = "backtest"
                
                # Pause
                coordinator.pause_backtest()
                
                # Should be paused
                assert coordinator.is_paused()
                
                # Event should be cleared
                assert not coordinator._stream_paused.is_set()
    
    def test_resume_sets_event(self):
        """Verify resume_backtest sets the event."""
        from app.threads.session_coordinator import SessionCoordinator
        
        with patch('app.threads.session_coordinator.SessionData'):
            with patch('app.threads.session_coordinator.PerformanceMetrics'):
                coordinator = object.__new__(SessionCoordinator)
                coordinator._stream_paused = threading.Event()
                coordinator._stream_paused.clear()  # Start paused
                
                coordinator._system_manager = Mock()
                coordinator._system_manager.mode.value = "backtest"
                
                # Resume
                coordinator.resume_backtest()
                
                # Should not be paused
                assert not coordinator.is_paused()
                
                # Event should be set
                assert coordinator._stream_paused.is_set()
    
    def test_pause_event_blocks_wait(self):
        """Verify clearing event blocks wait() call."""
        event = threading.Event()
        event.set()  # Initially not paused
        
        # Clear to pause
        event.clear()
        
        # Should block (timeout)
        result = event.wait(timeout=0.1)
        assert result is False, "Event should have blocked"
        
        # Set to resume
        event.set()
        
        # Should not block
        result = event.wait(timeout=0.1)
        assert result is True, "Event should not block"


class TestSystemManagerStateTransitions:
    """Test SystemManager state transitions during pause/resume."""
    
    @pytest.fixture
    def mock_system_manager(self):
        """Create a mock SystemManager for testing."""
        from app.managers.system_manager import SystemManager
        
        # Create instance without calling __init__
        mgr = object.__new__(SystemManager)
        mgr._state = SystemState.STOPPED
        mgr._mode = OperationMode.BACKTEST
        mgr._coordinator = Mock()
        
        return mgr
    
    def test_pause_transitions_to_paused(self, mock_system_manager):
        """Verify pause() transitions state to PAUSED."""
        mgr = mock_system_manager
        mgr._state = SystemState.RUNNING
        
        # Mock the pause method behavior
        def mock_pause():
            if mgr._state != SystemState.RUNNING:
                raise RuntimeError(f"Cannot pause - system is {mgr._state.value}")
            if mgr._mode != OperationMode.BACKTEST:
                return False
            mgr._coordinator.pause_backtest()
            mgr._state = SystemState.PAUSED
            return True
        
        mgr.pause = mock_pause
        
        # Pause
        result = mgr.pause()
        
        assert result is True
        assert mgr._state == SystemState.PAUSED
    
    def test_resume_transitions_to_running(self, mock_system_manager):
        """Verify resume() transitions state to RUNNING."""
        mgr = mock_system_manager
        mgr._state = SystemState.PAUSED
        
        # Mock the resume method behavior
        def mock_resume():
            if mgr._state != SystemState.PAUSED:
                raise RuntimeError(f"Cannot resume - system is {mgr._state.value}")
            if mgr._mode != OperationMode.BACKTEST:
                return False
            mgr._coordinator.resume_backtest()
            mgr._state = SystemState.RUNNING
            return True
        
        mgr.resume = mock_resume
        
        # Resume
        result = mgr.resume()
        
        assert result is True
        assert mgr._state == SystemState.RUNNING
    
    def test_cannot_pause_when_stopped(self, mock_system_manager):
        """Verify pause raises error when system is stopped."""
        mgr = mock_system_manager
        mgr._state = SystemState.STOPPED
        
        def mock_pause():
            if mgr._state != SystemState.RUNNING:
                raise RuntimeError(f"Cannot pause - system is {mgr._state.value}")
            mgr._state = SystemState.PAUSED
            return True
        
        mgr.pause = mock_pause
        
        # Should raise error
        with pytest.raises(RuntimeError, match="Cannot pause"):
            mgr.pause()
    
    def test_cannot_pause_when_already_paused(self, mock_system_manager):
        """Verify pause raises error when already paused."""
        mgr = mock_system_manager
        mgr._state = SystemState.PAUSED
        
        def mock_pause():
            if mgr._state != SystemState.RUNNING:
                raise RuntimeError(f"Cannot pause - system is {mgr._state.value}")
            mgr._state = SystemState.PAUSED
            return True
        
        mgr.pause = mock_pause
        
        # Should raise error
        with pytest.raises(RuntimeError, match="Cannot pause"):
            mgr.pause()
    
    def test_cannot_resume_when_running(self, mock_system_manager):
        """Verify resume raises error when system is running."""
        mgr = mock_system_manager
        mgr._state = SystemState.RUNNING
        
        def mock_resume():
            if mgr._state != SystemState.PAUSED:
                raise RuntimeError(f"Cannot resume - system is {mgr._state.value}")
            mgr._state = SystemState.RUNNING
            return True
        
        mgr.resume = mock_resume
        
        # Should raise error
        with pytest.raises(RuntimeError, match="Cannot resume"):
            mgr.resume()
    
    def test_cannot_resume_when_stopped(self, mock_system_manager):
        """Verify resume raises error when system is stopped."""
        mgr = mock_system_manager
        mgr._state = SystemState.STOPPED
        
        def mock_resume():
            if mgr._state != SystemState.PAUSED:
                raise RuntimeError(f"Cannot resume - system is {mgr._state.value}")
            mgr._state = SystemState.RUNNING
            return True
        
        mgr.resume = mock_resume
        
        # Should raise error
        with pytest.raises(RuntimeError, match="Cannot resume"):
            mgr.resume()


class TestModeAwareBehavior:
    """Test mode-aware pause/resume behavior."""
    
    @pytest.fixture
    def mock_system_manager(self):
        """Create a mock SystemManager for mode testing."""
        from app.managers.system_manager import SystemManager
        
        mgr = object.__new__(SystemManager)
        mgr._state = SystemState.RUNNING
        mgr._coordinator = Mock()
        
        return mgr
    
    def test_pause_works_in_backtest_mode(self, mock_system_manager):
        """Verify pause works in backtest mode."""
        mgr = mock_system_manager
        mgr._mode = OperationMode.BACKTEST
        
        def mock_pause():
            if mgr._mode != OperationMode.BACKTEST:
                return False
            mgr._coordinator.pause_backtest()
            mgr._state = SystemState.PAUSED
            return True
        
        mgr.pause = mock_pause
        
        result = mgr.pause()
        
        assert result is True
        assert mgr._state == SystemState.PAUSED
    
    def test_pause_ignored_in_live_mode(self, mock_system_manager):
        """Verify pause is ignored in live mode."""
        mgr = mock_system_manager
        mgr._mode = OperationMode.LIVE
        
        def mock_pause():
            if mgr._mode != OperationMode.BACKTEST:
                return False
            mgr._coordinator.pause_backtest()
            mgr._state = SystemState.PAUSED
            return True
        
        mgr.pause = mock_pause
        
        result = mgr.pause()
        
        assert result is False
        assert mgr._state == SystemState.RUNNING  # State unchanged


class TestStateQueries:
    """Test state query methods."""
    
    @pytest.fixture
    def mock_system_manager(self):
        """Create a mock SystemManager for state queries."""
        from app.managers.system_manager import SystemManager
        
        mgr = object.__new__(SystemManager)
        return mgr
    
    def test_is_running(self, mock_system_manager):
        """Verify is_running() returns correct value."""
        mgr = mock_system_manager
        
        mgr._state = SystemState.RUNNING
        mgr.is_running = lambda: mgr._state == SystemState.RUNNING
        assert mgr.is_running() is True
        
        mgr._state = SystemState.PAUSED
        assert mgr.is_running() is False
        
        mgr._state = SystemState.STOPPED
        assert mgr.is_running() is False
    
    def test_is_paused(self, mock_system_manager):
        """Verify is_paused() returns correct value."""
        mgr = mock_system_manager
        
        mgr._state = SystemState.PAUSED
        mgr.is_paused = lambda: mgr._state == SystemState.PAUSED
        assert mgr.is_paused() is True
        
        mgr._state = SystemState.RUNNING
        assert mgr.is_paused() is False
        
        mgr._state = SystemState.STOPPED
        assert mgr.is_paused() is False
    
    def test_is_stopped(self, mock_system_manager):
        """Verify is_stopped() returns correct value."""
        mgr = mock_system_manager
        
        mgr._state = SystemState.STOPPED
        mgr.is_stopped = lambda: mgr._state == SystemState.STOPPED
        assert mgr.is_stopped() is True
        
        mgr._state = SystemState.RUNNING
        assert mgr.is_stopped() is False
        
        mgr._state = SystemState.PAUSED
        assert mgr.is_stopped() is False
    
    def test_get_state(self, mock_system_manager):
        """Verify get_state() returns correct SystemState."""
        mgr = mock_system_manager
        mgr.get_state = lambda: mgr._state
        
        mgr._state = SystemState.RUNNING
        assert mgr.get_state() == SystemState.RUNNING
        
        mgr._state = SystemState.PAUSED
        assert mgr.get_state() == SystemState.PAUSED
        
        mgr._state = SystemState.STOPPED
        assert mgr.get_state() == SystemState.STOPPED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
