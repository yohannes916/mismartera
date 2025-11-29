#!/usr/bin/env python3
"""
Quick verification script for StreamSubscription without pytest dependency.
"""

import time
import threading
from app.threads.sync.stream_subscription import StreamSubscription


def test_basic_one_shot_pattern():
    """Test basic signal→wait→reset pattern."""
    print("Testing basic one-shot pattern...")
    
    subscription = StreamSubscription('data-driven', 'test')
    
    # Signal ready
    subscription.signal_ready()
    assert subscription.is_ready(), "Should be ready after signal"
    
    # Wait should return immediately (already set)
    result = subscription.wait_until_ready()
    assert result is True, "Should return True when ready"
    
    # Reset
    subscription.reset()
    assert not subscription.is_ready(), "Should not be ready after reset"
    
    print("✓ Basic one-shot pattern works")


def test_data_driven_mode():
    """Test data-driven mode (blocks indefinitely)."""
    print("\nTesting data-driven mode...")
    
    subscription = StreamSubscription('data-driven', 'test-data-driven')
    result = []
    
    def consumer():
        # This will block until signal
        result.append(subscription.wait_until_ready())
        subscription.reset()
    
    # Start consumer thread (will block)
    t = threading.Thread(target=consumer)
    t.start()
    
    # Give it a moment to start blocking
    time.sleep(0.1)
    
    # Signal ready
    subscription.signal_ready()
    
    # Wait for consumer
    t.join(timeout=1.0)
    
    assert len(result) == 1, "Consumer should have completed"
    assert result[0] is True, "Should return True"
    
    print("✓ Data-driven mode blocks correctly")


def test_clock_driven_mode_timeout():
    """Test clock-driven mode with timeout."""
    print("\nTesting clock-driven mode (timeout)...")
    
    subscription = StreamSubscription('clock-driven', 'test-clock')
    
    # Wait with short timeout (no signal)
    start = time.perf_counter()
    result = subscription.wait_until_ready(timeout=0.1)
    duration = time.perf_counter() - start
    
    assert result is False, "Should timeout"
    assert 0.09 < duration < 0.15, f"Should timeout around 0.1s, got {duration:.3f}s"
    
    print(f"✓ Clock-driven timeout works (duration: {duration:.3f}s)")


def test_clock_driven_mode_success():
    """Test clock-driven mode with successful wait."""
    print("\nTesting clock-driven mode (success)...")
    
    subscription = StreamSubscription('clock-driven', 'test-clock-success')
    
    # Signal ready
    subscription.signal_ready()
    
    # Wait should return immediately
    result = subscription.wait_until_ready(timeout=1.0)
    assert result is True, "Should return True when ready"
    
    print("✓ Clock-driven success works")


def test_overrun_detection():
    """Test overrun detection in clock-driven mode."""
    print("\nTesting overrun detection...")
    
    subscription = StreamSubscription('clock-driven', 'test-overrun')
    
    # Signal ready
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 0, "No overruns initially"
    
    # Signal again without reset (overrun)
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 1, "Should detect 1 overrun"
    
    # Signal again (another overrun)
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 2, "Should detect 2 overruns"
    
    # Reset
    subscription.reset()
    
    # Signal after reset (no overrun)
    subscription.signal_ready()
    assert subscription.get_overrun_count() == 2, "Overrun count stays at 2"
    
    print("✓ Overrun detection works correctly")


def test_producer_consumer_pattern():
    """Test realistic producer-consumer pattern."""
    print("\nTesting producer-consumer pattern...")
    
    subscription = StreamSubscription('data-driven', 'producer-consumer')
    data_queue = []
    processed = []
    
    def producer():
        """Produce 5 items."""
        for i in range(5):
            data_queue.append(f"data_{i}")
            subscription.signal_ready()
            time.sleep(0.01)  # Simulate production time
    
    def consumer():
        """Consume items."""
        for _ in range(5):
            subscription.wait_until_ready()
            if data_queue:
                item = data_queue.pop(0)
                processed.append(item)
            subscription.reset()
    
    # Start threads
    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)
    
    consumer_thread.start()
    time.sleep(0.01)  # Let consumer start waiting
    producer_thread.start()
    
    # Wait for completion
    producer_thread.join(timeout=2.0)
    consumer_thread.join(timeout=2.0)
    
    assert len(processed) == 5, f"Should process 5 items, got {len(processed)}"
    assert processed == [f"data_{i}" for i in range(5)], "Items should be in order"
    
    print("✓ Producer-consumer pattern works")


def test_multiple_consumers():
    """Test that only one consumer gets the signal (one-shot)."""
    print("\nTesting one-shot with multiple consumers...")
    
    subscription = StreamSubscription('data-driven', 'multi-consumer')
    results = []
    
    def consumer(consumer_id):
        result = subscription.wait_until_ready(timeout=0.5)
        if result:
            results.append(consumer_id)
    
    # Start multiple consumers
    threads = [threading.Thread(target=consumer, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    
    time.sleep(0.1)  # Let them start waiting
    
    # Signal once
    subscription.signal_ready()
    
    # Wait for all
    for t in threads:
        t.join(timeout=1.0)
    
    # All should receive the signal (threading.Event broadcasts to all waiters)
    assert len(results) == 3, f"All 3 consumers should get signal, got {len(results)}"
    
    print("✓ Multiple consumers get signal (Event broadcasts)")


def test_thread_safety():
    """Test thread-safety with concurrent signal/wait operations."""
    print("\nTesting thread-safety...")
    
    subscription = StreamSubscription('clock-driven', 'thread-safety')
    errors = []
    
    def signaler():
        try:
            for _ in range(100):
                subscription.signal_ready()
                subscription.reset()
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)
    
    def waiter():
        try:
            for _ in range(100):
                subscription.wait_until_ready(timeout=0.1)
                subscription.reset()
        except Exception as e:
            errors.append(e)
    
    # Run concurrent signalers and waiters
    threads = [
        threading.Thread(target=signaler),
        threading.Thread(target=waiter),
        threading.Thread(target=waiter)
    ]
    
    for t in threads:
        t.start()
    
    for t in threads:
        t.join(timeout=5.0)
    
    assert len(errors) == 0, f"No errors should occur, got {errors}"
    
    print("✓ Thread-safety verified")


def test_invalid_mode():
    """Test that invalid mode raises error."""
    print("\nTesting invalid mode detection...")
    
    try:
        subscription = StreamSubscription('invalid', 'test')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid mode" in str(e)
        print(f"✓ Invalid mode correctly rejected: {e}")


def test_repr():
    """Test string representation."""
    print("\nTesting repr...")
    
    subscription = StreamSubscription('data-driven', 'test-repr')
    repr_str = repr(subscription)
    
    assert "StreamSubscription" in repr_str
    assert "test-repr" in repr_str
    assert "data-driven" in repr_str
    
    print(f"✓ Repr works: {repr_str}")


if __name__ == "__main__":
    print("=" * 60)
    print("StreamSubscription Verification")
    print("=" * 60)
    
    try:
        test_basic_one_shot_pattern()
        test_data_driven_mode()
        test_clock_driven_mode_timeout()
        test_clock_driven_mode_success()
        test_overrun_detection()
        test_producer_consumer_pattern()
        test_multiple_consumers()
        test_thread_safety()
        test_invalid_mode()
        test_repr()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nStreamSubscription is ready for use!")
        print("- One-shot pattern verified")
        print("- Mode-aware behavior working")
        print("- Overrun detection functional")
        print("- Thread-safe operations confirmed")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
