"""
Unit tests for StreamSubscription - Thread synchronization primitive.

Tests verify:
- Data-driven mode blocks indefinitely until signaled
- Clock-driven mode respects timeout
- Overrun detection in clock-driven mode
- One-shot pattern (signal→wait→reset)
"""

import pytest
import threading
import time
from app.threads.sync.stream_subscription import StreamSubscription


class TestStreamSubscriptionModes:
    """Test mode-specific behavior of StreamSubscription."""
    
    def test_data_driven_blocks_indefinitely(self):
        """Verify data-driven mode blocks until signaled."""
        subscription = StreamSubscription(mode="data-driven", stream_id="test")
        
        # Track if wait completed
        waited = threading.Event()
        
        def waiter():
            subscription.wait_until_ready()
            waited.set()
        
        # Start waiting in background thread
        thread = threading.Thread(target=waiter, daemon=True)
        thread.start()
        
        # Should still be waiting after 1 second
        time.sleep(1.0)
        assert not waited.is_set(), "Should not have completed without signal"
        
        # Signal ready
        subscription.signal_ready()
        
        # Should complete immediately
        thread.join(timeout=1.0)
        assert waited.is_set(), "Should have completed after signal"
    
    def test_clock_driven_times_out(self):
        """Verify clock-driven mode respects timeout."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        start = time.perf_counter()
        result = subscription.wait_until_ready(timeout=0.5)
        duration = time.perf_counter() - start
        
        assert result is False, "Should return False on timeout"
        assert 0.4 < duration < 0.6, f"Should timeout around 0.5s, got {duration:.3f}s"
    
    def test_clock_driven_returns_true_when_signaled(self):
        """Verify clock-driven mode returns True when signaled before timeout."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        # Signal ready immediately
        subscription.signal_ready()
        
        # Should return True immediately
        start = time.perf_counter()
        result = subscription.wait_until_ready(timeout=1.0)
        duration = time.perf_counter() - start
        
        assert result is True, "Should return True when signaled"
        assert duration < 0.1, f"Should return immediately, took {duration:.3f}s"
    
    def test_live_mode_times_out(self):
        """Verify live mode respects timeout like clock-driven."""
        subscription = StreamSubscription(mode="live", stream_id="test")
        
        start = time.perf_counter()
        result = subscription.wait_until_ready(timeout=0.3)
        duration = time.perf_counter() - start
        
        assert result is False, "Should return False on timeout"
        assert 0.2 < duration < 0.4, f"Should timeout around 0.3s, got {duration:.3f}s"


class TestOverrunDetection:
    """Test overrun detection in clock-driven mode."""
    
    def test_overrun_detection_clock_driven(self):
        """Verify overrun is detected when signal_ready called before reset."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        # First signal - no overrun
        subscription.signal_ready()
        assert subscription.get_overrun_count() == 0
        
        # Second signal before reset - should detect overrun
        subscription.signal_ready()
        assert subscription.get_overrun_count() == 1
        
        # Third signal - should increment again
        subscription.signal_ready()
        assert subscription.get_overrun_count() == 2
        
        # Reset and signal again - no new overrun
        subscription.reset()
        subscription.signal_ready()
        assert subscription.get_overrun_count() == 2  # Still 2, not incremented
    
    def test_no_overrun_in_data_driven_mode(self):
        """Verify overrun detection doesn't apply to data-driven mode."""
        subscription = StreamSubscription(mode="data-driven", stream_id="test")
        
        # Multiple signals without reset
        subscription.signal_ready()
        subscription.signal_ready()
        subscription.signal_ready()
        
        # Overrun count should still be 0 (not tracked in data-driven)
        assert subscription.get_overrun_count() == 0
    
    def test_overrun_with_proper_reset_cycle(self):
        """Verify no overrun when proper signal→wait→reset cycle followed."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        for i in range(5):
            # Proper cycle
            subscription.signal_ready()
            subscription.wait_until_ready(timeout=0.1)
            subscription.reset()
        
        # No overruns should be detected
        assert subscription.get_overrun_count() == 0


class TestOneShotPattern:
    """Test one-shot signal→wait→reset pattern."""
    
    def test_one_shot_requires_reset(self):
        """Verify wait blocks again after reset."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        # First cycle
        subscription.signal_ready()
        assert subscription.wait_until_ready(timeout=0.1) is True
        
        # Without reset, should still be set (return True immediately)
        assert subscription.wait_until_ready(timeout=0.1) is True
        
        # After reset, should block
        subscription.reset()
        assert subscription.wait_until_ready(timeout=0.1) is False  # Timeout
    
    def test_is_ready_reflects_state(self):
        """Verify is_ready() reflects current state."""
        subscription = StreamSubscription(mode="data-driven", stream_id="test")
        
        # Initially not ready
        assert not subscription.is_ready()
        
        # After signal, ready
        subscription.signal_ready()
        assert subscription.is_ready()
        
        # After reset, not ready again
        subscription.reset()
        assert not subscription.is_ready()
    
    def test_multiple_cycles(self):
        """Verify multiple signal→wait→reset cycles work correctly."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        for i in range(10):
            # Signal
            subscription.signal_ready()
            
            # Wait (should succeed)
            result = subscription.wait_until_ready(timeout=0.1)
            assert result is True, f"Cycle {i} failed to signal"
            
            # Reset for next cycle
            subscription.reset()
            
            # Should block now
            assert not subscription.is_ready(), f"Cycle {i} failed to reset"


class TestThreadSafety:
    """Test thread safety of StreamSubscription."""
    
    def test_concurrent_signal_and_wait(self):
        """Verify concurrent signal and wait operations are thread-safe."""
        subscription = StreamSubscription(mode="data-driven", stream_id="test")
        
        results = []
        
        def waiter(idx):
            subscription.wait_until_ready()
            results.append(idx)
        
        # Start multiple waiters
        threads = []
        for i in range(5):
            thread = threading.Thread(target=waiter, args=(i,), daemon=True)
            thread.start()
            threads.append(thread)
        
        # Let them start waiting
        time.sleep(0.5)
        
        # Signal once - should unblock all
        subscription.signal_ready()
        
        # Wait for all to complete
        for thread in threads:
            thread.join(timeout=1.0)
        
        # All should have completed
        assert len(results) == 5, "All waiters should have completed"
    
    def test_concurrent_signals(self):
        """Verify concurrent signal calls are thread-safe."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        
        def signaler():
            for _ in range(100):
                subscription.signal_ready()
        
        # Signal from multiple threads
        threads = [threading.Thread(target=signaler, daemon=True) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Should have overruns, but no crashes
        assert subscription.get_overrun_count() > 0


class TestModeValidation:
    """Test mode validation and properties."""
    
    def test_invalid_mode_raises_error(self):
        """Verify invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            StreamSubscription(mode="invalid", stream_id="test")
    
    def test_get_mode(self):
        """Verify get_mode() returns correct mode."""
        sub1 = StreamSubscription(mode="data-driven", stream_id="test1")
        assert sub1.get_mode() == "data-driven"
        
        sub2 = StreamSubscription(mode="clock-driven", stream_id="test2")
        assert sub2.get_mode() == "clock-driven"
        
        sub3 = StreamSubscription(mode="live", stream_id="test3")
        assert sub3.get_mode() == "live"
    
    def test_get_stream_id(self):
        """Verify get_stream_id() returns correct identifier."""
        subscription = StreamSubscription(mode="data-driven", stream_id="my_stream")
        assert subscription.get_stream_id() == "my_stream"
    
    def test_repr(self):
        """Verify __repr__ provides useful debug info."""
        subscription = StreamSubscription(mode="clock-driven", stream_id="test")
        subscription.signal_ready()
        
        repr_str = repr(subscription)
        
        assert "test" in repr_str
        assert "clock-driven" in repr_str
        assert "ready=" in repr_str or "True" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
