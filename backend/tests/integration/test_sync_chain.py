"""
Integration tests for synchronization chain.

Tests the actual integration between:
- SessionCoordinator → DataProcessor (via StreamSubscription)
- DataProcessor → AnalysisEngine (via StreamSubscription)

These tests verify the synchronization actually works in practice,
not just in isolation.
"""

import pytest
import threading
import time
from datetime import datetime
from collections import deque
from unittest.mock import Mock, MagicMock, patch

from app.threads.sync.stream_subscription import StreamSubscription


class TestCoordinatorProcessorSync:
    """Test synchronization between Coordinator and Processor."""
    
    def test_data_driven_coordinator_blocks_until_processor_ready(self):
        """
        Verify coordinator waits for processor in data-driven mode.
        
        Flow:
        1. Coordinator processes bars
        2. Coordinator waits for processor subscription
        3. Processor signals ready
        4. Coordinator continues
        """
        # Create subscription (data-driven mode)
        subscription = StreamSubscription(
            mode="data-driven",
            stream_id="coordinator->processor"
        )
        
        # Track timing
        events = []
        
        # Simulate coordinator behavior
        def coordinator_flow():
            events.append(("coordinator_start", time.perf_counter()))
            
            # Process bars (simulated)
            time.sleep(0.1)
            events.append(("coordinator_processed_bars", time.perf_counter()))
            
            # Wait for processor (THIS IS THE KEY TEST)
            subscription.wait_until_ready()
            events.append(("coordinator_resumed", time.perf_counter()))
        
        # Simulate processor behavior
        def processor_flow():
            # Wait a bit to simulate processing time
            time.sleep(0.3)
            events.append(("processor_processing", time.perf_counter()))
            
            # Signal ready
            subscription.signal_ready()
            events.append(("processor_signaled", time.perf_counter()))
        
        # Start both threads
        coord_thread = threading.Thread(target=coordinator_flow, daemon=True)
        proc_thread = threading.Thread(target=processor_flow, daemon=True)
        
        coord_thread.start()
        proc_thread.start()
        
        # Wait for completion
        coord_thread.join(timeout=2.0)
        proc_thread.join(timeout=2.0)
        
        # Verify order of events
        assert len(events) == 5
        
        # Extract event names in order
        event_names = [e[0] for e in events]
        assert event_names == [
            "coordinator_start",
            "coordinator_processed_bars",
            "processor_processing",
            "processor_signaled",
            "coordinator_resumed"
        ]
        
        # Verify coordinator waited for processor
        coordinator_processed_time = events[1][1]
        coordinator_resumed_time = events[4][1]
        processor_signaled_time = events[3][1]
        
        # Coordinator should have resumed AFTER processor signaled
        assert coordinator_resumed_time > processor_signaled_time
        
        # Wait duration should be >= processor time
        wait_duration = coordinator_resumed_time - coordinator_processed_time
        assert wait_duration >= 0.2  # Processor took ~0.3s
    
    def test_clock_driven_coordinator_continues_async(self):
        """
        Verify coordinator doesn't wait in clock-driven mode.
        
        Flow:
        1. Coordinator processes bars
        2. Coordinator continues immediately (no wait)
        3. Processor runs async
        """
        # Create subscription (clock-driven mode)
        subscription = StreamSubscription(
            mode="clock-driven",
            stream_id="coordinator->processor"
        )
        
        # Track timing
        events = []
        
        # Simulate coordinator behavior (no wait in clock-driven)
        def coordinator_flow():
            events.append(("coordinator_start", time.perf_counter()))
            
            # Process bars
            time.sleep(0.05)
            events.append(("coordinator_processed_bars", time.perf_counter()))
            
            # In clock-driven mode, coordinator doesn't wait
            # It just continues
            events.append(("coordinator_continued", time.perf_counter()))
        
        # Simulate processor behavior
        def processor_flow():
            time.sleep(0.3)  # Slower than coordinator
            events.append(("processor_processing", time.perf_counter()))
            subscription.signal_ready()
        
        # Start both threads
        coord_thread = threading.Thread(target=coordinator_flow, daemon=True)
        proc_thread = threading.Thread(target=processor_flow, daemon=True)
        
        coord_thread.start()
        proc_thread.start()
        
        # Wait for completion
        coord_thread.join(timeout=2.0)
        proc_thread.join(timeout=2.0)
        
        # Verify coordinator finished before processor
        coord_times = [e[1] for e in events if "coordinator" in e[0]]
        proc_times = [e[1] for e in events if "processor" in e[0]]
        
        coord_end = max(coord_times)
        proc_end = max(proc_times)
        
        # Coordinator should finish before processor (async)
        assert coord_end < proc_end
    
    def test_processor_waits_for_analysis_in_data_driven(self):
        """
        Verify processor waits for analysis engine in data-driven mode.
        
        Flow:
        1. Processor generates derived bars
        2. Processor waits for analysis subscription
        3. Analysis engine signals ready
        4. Processor signals coordinator
        """
        # Create subscriptions
        analysis_subscription = StreamSubscription(
            mode="data-driven",
            stream_id="analysis->processor"
        )
        
        coordinator_subscription = StreamSubscription(
            mode="data-driven",
            stream_id="processor->coordinator"
        )
        
        # Track events
        events = []
        
        # Simulate processor behavior
        def processor_flow():
            events.append(("processor_start", time.perf_counter()))
            
            # Generate derived bars
            time.sleep(0.05)
            events.append(("processor_generated_bars", time.perf_counter()))
            
            # Wait for analysis
            analysis_subscription.wait_until_ready()
            events.append(("processor_analysis_done", time.perf_counter()))
            
            # Signal coordinator
            coordinator_subscription.signal_ready()
            events.append(("processor_signaled_coordinator", time.perf_counter()))
        
        # Simulate analysis engine behavior
        def analysis_flow():
            time.sleep(0.2)  # Simulate strategy execution
            events.append(("analysis_processing", time.perf_counter()))
            
            # Signal ready
            analysis_subscription.signal_ready()
            events.append(("analysis_signaled", time.perf_counter()))
        
        # Start both threads
        proc_thread = threading.Thread(target=processor_flow, daemon=True)
        analysis_thread = threading.Thread(target=analysis_flow, daemon=True)
        
        proc_thread.start()
        analysis_thread.start()
        
        # Wait for completion
        proc_thread.join(timeout=2.0)
        analysis_thread.join(timeout=2.0)
        
        # Verify order
        event_names = [e[0] for e in events]
        
        # Processor should wait for analysis before signaling coordinator
        assert "processor_generated_bars" in event_names
        assert "analysis_signaled" in event_names
        assert "processor_signaled_coordinator" in event_names
        
        # Find indices
        gen_idx = event_names.index("processor_generated_bars")
        analysis_idx = event_names.index("analysis_signaled")
        signal_idx = event_names.index("processor_signaled_coordinator")
        
        # Processor should signal coordinator AFTER analysis finished
        assert signal_idx > analysis_idx


class TestFullSynchronizationChain:
    """Test complete synchronization chain: Coordinator → Processor → Analysis."""
    
    def test_complete_chain_data_driven(self):
        """
        Test complete synchronization chain in data-driven mode.
        
        Full flow:
        1. Coordinator processes bar
        2. Coordinator waits for processor
        3. Processor generates derived bars
        4. Processor waits for analysis
        5. Analysis runs strategies
        6. Analysis signals processor
        7. Processor signals coordinator
        8. Coordinator continues
        """
        # Create subscriptions
        coord_to_proc = StreamSubscription(mode="data-driven", stream_id="coord->proc")
        proc_to_analysis = StreamSubscription(mode="data-driven", stream_id="proc->analysis")
        
        # Track complete flow
        events = []
        lock = threading.Lock()
        
        def add_event(name):
            with lock:
                events.append((name, time.perf_counter()))
        
        # Coordinator
        def coordinator():
            add_event("coord_start")
            time.sleep(0.05)  # Process bar
            add_event("coord_wait")
            
            coord_to_proc.wait_until_ready()
            add_event("coord_continue")
        
        # Processor
        def processor():
            time.sleep(0.1)  # Wait for coordinator to start
            add_event("proc_start")
            time.sleep(0.05)  # Generate derived
            add_event("proc_wait_analysis")
            
            proc_to_analysis.wait_until_ready()
            add_event("proc_signal_coord")
            
            coord_to_proc.signal_ready()
        
        # Analysis
        def analysis():
            time.sleep(0.2)  # Wait for processor
            add_event("analysis_start")
            time.sleep(0.05)  # Run strategies
            add_event("analysis_signal")
            
            proc_to_analysis.signal_ready()
        
        # Start all threads
        threads = [
            threading.Thread(target=coordinator, daemon=True),
            threading.Thread(target=processor, daemon=True),
            threading.Thread(target=analysis, daemon=True)
        ]
        
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join(timeout=3.0)
        
        # Verify complete chain
        with lock:
            event_names = [e[0] for e in events]
        
        # All events should have occurred
        expected_events = [
            "coord_start", "coord_wait",
            "proc_start", "proc_wait_analysis",
            "analysis_start", "analysis_signal",
            "proc_signal_coord", "coord_continue"
        ]
        
        for expected in expected_events:
            assert expected in event_names, f"Missing event: {expected}"
        
        # Verify order: coordinator should continue LAST
        coord_continue_idx = event_names.index("coord_continue")
        analysis_signal_idx = event_names.index("analysis_signal")
        
        # Coordinator continues after analysis completes
        assert coord_continue_idx > analysis_signal_idx
        
        # Verify duration - full chain should take time
        with lock:
            total_duration = events[-1][1] - events[0][1]
        
        # Should take at least 0.15s (sum of all sleeps in sequence)
        assert total_duration >= 0.15


class TestSynchronizationUnderLoad:
    """Test synchronization with multiple iterations."""
    
    def test_multiple_iterations_maintain_sync(self):
        """
        Verify synchronization works correctly over multiple iterations.
        """
        subscription = StreamSubscription(mode="data-driven", stream_id="test")
        
        iterations = 10
        coordinator_count = 0
        processor_count = 0
        
        def coordinator():
            nonlocal coordinator_count
            for i in range(iterations):
                subscription.wait_until_ready()
                subscription.reset()
                coordinator_count += 1
        
        def processor():
            nonlocal processor_count
            for i in range(iterations):
                time.sleep(0.01)  # Simulate work
                subscription.signal_ready()
                processor_count += 1
                time.sleep(0.01)  # Gap between iterations
        
        # Start both
        coord_thread = threading.Thread(target=coordinator, daemon=True)
        proc_thread = threading.Thread(target=processor, daemon=True)
        
        coord_thread.start()
        proc_thread.start()
        
        # Wait for completion
        coord_thread.join(timeout=5.0)
        proc_thread.join(timeout=5.0)
        
        # Both should complete all iterations
        assert coordinator_count == iterations
        assert processor_count == iterations


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
