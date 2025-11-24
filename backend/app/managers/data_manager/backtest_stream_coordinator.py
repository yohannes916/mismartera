"""Backtest Stream Coordinator for chronological multi-stream merging.

This module provides a central coordinator that merges multiple backtest
data streams (bars, ticks, quotes) across multiple symbols in chronological
order, ensuring that data is yielded oldest-first even when multiple streams
are active simultaneously.

ARCHITECTURE (2025-11):
- **SystemManager Integration**: Requires SystemManager reference for mode and state
- **Single Source of Truth**: Uses SystemManager.mode (no fallback to settings)
- **State-Aware Processing**: Checks SystemManager.is_running() before advancing time
- **Mode Management**: SystemManager.is_backtest_mode() determines behavior

IMPORTANT: This is the ONLY place where backtest time (_backtest_time in 
TimeProvider) is advanced forward. All other locations should only reset it 
to the backtest start time.

THREADING MODEL:
- Uses a dedicated worker thread for stream processing
- Thread runs independently of the CLI event loop for consistent timing
- Thread-safe queues for communication between CLI and worker
- Precise time.sleep() for accurate backtest speed control
"""
from __future__ import annotations

import asyncio
import heapq
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import AsyncIterator, Any, Dict, Tuple, Optional, List

from app.config import settings
from app.logger import logger


class StreamType(Enum):
    """Types of market data streams."""
    BAR = "bar"
    TICK = "tick"
    QUOTE = "quote"


@dataclass(order=True)
class StreamItem:
    """Wrapper for stream data with timestamp for priority queue ordering."""
    timestamp: datetime
    data: Any = field(compare=False)
    stream_key: Tuple[str, StreamType] = field(compare=False)


class BacktestStreamCoordinator:
    """Central coordinator for backtest data streams.
    
    Manages multiple concurrent backtest streams (bars, ticks, quotes) across
    different symbols and merges them in chronological order. Prevents duplicate
    streams and handles stream lifecycle.
    
    ARCHITECTURE:
    - Requires SystemManager reference for operation mode and state management
    - Uses SystemManager as single source of truth (no settings fallback)
    - Pauses time advancement when SystemManager.is_running() is False
    
    This coordinator is responsible for advancing backtest time as data flows
    through it. It is the ONLY component that should advance time forward in
    backtest mode.
    
    Thread-safe for concurrent registration/deregistration.
    """
    
    def __init__(self, system_manager=None, data_repository=None):
        """Initialize the coordinator.
        
        Args:
            system_manager: Reference to SystemManager (REQUIRED for production use)
                           Without SystemManager, coordinator cannot determine mode
                           or respect system state (paused/running/stopped)
            data_repository: Optional data repository for gap filling
        
        Uses the singleton TimeProvider instance to ensure time synchronization
        across all components (DataManager, streams, etc.).
        
        Uses a dedicated worker thread for processing that runs independently
        of the asyncio event loop.
        
        Phase 2: Also initializes DataUpkeepThread for background data maintenance.
        """
        # Reference to SystemManager for checking state
        self._system_manager = system_manager
        self._data_repository = data_repository
        
        if system_manager is None:
            logger.warning(
                "BacktestStreamCoordinator initialized without SystemManager - "
                "mode checks and state management will not work properly!"
            )
        
        # Active streams: (symbol, stream_type) -> queue.Queue (thread-safe)
        self._active_streams: Dict[Tuple[str, StreamType], queue.Queue] = {}
        
        # Track timestamps for queued items: (symbol, stream_type) -> {"oldest": datetime, "newest": datetime}
        self._queue_timestamps: Dict[Tuple[str, StreamType], Dict[str, Optional[datetime]]] = {}
        
        # Lock for thread-safe stream registration
        self._lock = threading.Lock()
        
        # Priority queue for merging streams: (timestamp, stream_key, data)
        self._merge_heap: List[StreamItem] = []
        
        # Worker thread for processing streams
        self._worker_thread: Optional[threading.Thread] = None
        
        # Pending items from merge worker (for accurate queue peeking)
        self._pending_items: Optional[Dict[Tuple[str, StreamType], Optional[StreamItem]]] = None
        
        # Output queue for merged stream (thread-safe)
        self._output_queue: queue.Queue = queue.Queue()
        
        # Shutdown flag (thread-safe)
        self._shutdown = threading.Event()
        
        # Time provider for advancing backtest time (singleton shared with DataManager)
        # Pass system_manager so TimeProvider uses it as single source of truth for mode
        from app.managers.data_manager.time_provider import get_time_provider
        self._time_provider = get_time_provider(system_manager=system_manager)
        
        # Session data for storing streamed data
        from app.managers.data_manager.session_data import get_session_data
        self._session_data = get_session_data()
        
        # Data-upkeep thread for background data maintenance (Phase 2)
        self._upkeep_thread: Optional = None
        if settings.DATA_UPKEEP_ENABLED:
            from app.managers.data_manager.data_upkeep_thread import DataUpkeepThread
            self._upkeep_thread = DataUpkeepThread(
                session_data=self._session_data,
                system_manager=self._system_manager,
                data_repository=self._data_repository
            )
            logger.info("DataUpkeepThread initialized (Phase 2)")
        
        # Track last timestamp for pacing
        self._last_timestamp: Optional[datetime] = None
        
        sys_mgr_status = "with SystemManager" if system_manager is not None else "WITHOUT SystemManager"
        logger.info(f"BacktestStreamCoordinator initialized with threading ({sys_mgr_status})")
    
    def register_stream(
        self,
        symbol: str,
        stream_type: StreamType,
    ) -> Tuple[bool, Optional[queue.Queue]]:
        """Register a new stream for a symbol and data type.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            stream_type: Type of data stream
            
        Returns:
            Tuple of (success: bool, queue: Optional[queue.Queue])
            If successful, returns (True, queue) where queue is the thread-safe
            input queue for this stream. If stream already exists, returns (False, None).
        """
        stream_key = (symbol.upper(), stream_type)
        
        with self._lock:
            if stream_key in self._active_streams:
                logger.warning(
                    f"Stream already active for {stream_key[0]} ({stream_key[1].value})"
                )
                return False, None
            
            # Create thread-safe input queue for this stream
            input_queue = queue.Queue()
            self._active_streams[stream_key] = input_queue
            
            # Initialize timestamp tracking
            self._queue_timestamps[stream_key] = {"oldest": None, "newest": None}
            
            logger.info(
                f"Registered stream for {stream_key[0]} ({stream_key[1].value})"
            )
            
            return True, input_queue
    
    def feed_data_list(
        self,
        symbol: str,
        stream_type: StreamType,
        data_list: list,
    ) -> bool:
        """Feed a pre-fetched list of data directly into the stream queue.
        
        This is faster than async iteration and can be called from any thread.
        Use this when you've already fetched all data from DB.
        
        Args:
            symbol: Stock symbol
            stream_type: Type of data stream
            data_list: List of data objects (BarData, TickData, etc.)
            
        Returns:
            True if successful, False if stream not registered
        """
        stream_key = (symbol.upper(), stream_type)
        
        with self._lock:
            input_queue = self._active_streams.get(stream_key)
        
        if input_queue is None:
            logger.error(f"Cannot feed data for {stream_key} - stream not registered")
            return False
        
        # Feed all data directly into queue (fast, thread-safe)
        # Track the newest timestamp in this batch
        batch_newest_ts = None
        
        for data in data_list:
            input_queue.put(data)
            
            # Track newest timestamp in this batch
            if hasattr(data, 'timestamp'):
                ts = data.timestamp
                if batch_newest_ts is None or ts > batch_newest_ts:
                    batch_newest_ts = ts
        
        # Update newest timestamp tracking (keep the maximum across all batches)
        with self._lock:
            if stream_key in self._queue_timestamps:
                existing = self._queue_timestamps[stream_key]
                current_newest = existing.get("newest")
                
                # Keep the maximum (newest) timestamp seen across all batches
                if batch_newest_ts:
                    if current_newest is None or batch_newest_ts > current_newest:
                        self._queue_timestamps[stream_key]["newest"] = batch_newest_ts
        
        # Signal end of stream
        input_queue.put(None)
        
        logger.info(f"Fed {len(data_list)} items to stream {stream_key}")
        return True
    
    def deregister_stream(
        self,
        symbol: str,
        stream_type: StreamType,
    ) -> bool:
        """Deregister a stream (called when stream is exhausted).
        
        Args:
            symbol: Stock symbol
            stream_type: Type of data stream
            
        Returns:
            True if stream was found and removed, False otherwise
        """
        stream_key = (symbol.upper(), stream_type)
        
        with self._lock:
            if stream_key in self._active_streams:
                del self._active_streams[stream_key]
                # Also remove timestamp tracking
                if stream_key in self._queue_timestamps:
                    del self._queue_timestamps[stream_key]
                logger.info(
                    f"Deregistered stream for {stream_key[0]} ({stream_key[1].value})"
                )
                return True
            
            return False
    
    def is_stream_active(
        self,
        symbol: str,
        stream_type: StreamType,
    ) -> bool:
        """Check if a stream is currently active.
        
        Args:
            symbol: Stock symbol
            stream_type: Type of data stream
            
        Returns:
            True if stream is active, False otherwise
        """
        stream_key = (symbol.upper(), stream_type)
        with self._lock:
            return stream_key in self._active_streams
    
    def get_queue_stats(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get queue statistics for all active streams, grouped by interval.
        
        Returns:
            Dictionary mapping symbol to interval to stats dict
            Stats dict contains: {"size": int, "oldest": datetime, "newest": datetime}
            Example: {"AAPL": {"BAR": {"size": 150, "oldest": datetime(...), "newest": datetime(...)}}}
            
            For BAR streams, interval is shown as "BAR"
            For other streams (TICK, QUOTE), interval is the stream type name
            
            Note: 
            - oldest is from pending_items (accurate: next item to be consumed)
            - newest is from initial batch timestamps (last item in original batch)
            - size is current queue size
        """
        stats = {}
        with self._lock:
            for (symbol, stream_type), input_queue in self._active_streams.items():
                if symbol not in stats:
                    stats[symbol] = {}
                
                queue_size = input_queue.qsize()
                interval_key = "BAR"  # Default for bar type
                
                if stream_type != StreamType.BAR:
                    interval_key = stream_type.value.upper()
                
                # Get ACTUAL oldest timestamp from pending_items (worker's staging area)
                oldest_ts = None
                if self._pending_items:
                    stream_key = (symbol, stream_type)
                    pending_item = self._pending_items.get(stream_key)
                    if pending_item and hasattr(pending_item, 'timestamp'):
                        oldest_ts = pending_item.timestamp
                
                # Get newest timestamp from initial batch tracking
                timestamps = self._queue_timestamps.get((symbol, stream_type), {})
                newest_ts = timestamps.get("newest")
                
                # Use interval as key (e.g., "BAR", "TICK", "QUOTE")
                if interval_key not in stats[symbol]:
                    stats[symbol][interval_key] = {
                        "size": 0,
                        "oldest": None,
                        "newest": None
                    }
                
                # Add queue size (items still in queue + 1 in pending)
                total_items = queue_size + (1 if oldest_ts else 0)
                stats[symbol][interval_key]["size"] += total_items
                
                # Update timestamps if available
                if oldest_ts:
                    if stats[symbol][interval_key]["oldest"] is None or oldest_ts < stats[symbol][interval_key]["oldest"]:
                        stats[symbol][interval_key]["oldest"] = oldest_ts
                if newest_ts:
                    if stats[symbol][interval_key]["newest"] is None or newest_ts > stats[symbol][interval_key]["newest"]:
                        stats[symbol][interval_key]["newest"] = newest_ts
        
        return stats
    
    def start_worker(self) -> None:
        """Start the background worker thread that merges streams chronologically.
        
        The thread runs independently of the CLI event loop, providing consistent
        timing for backtest streaming.
        
        Phase 2: Also starts the data-upkeep thread for background data maintenance.
        """
        if self._worker_thread is not None and self._worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return
        
        self._shutdown.clear()
        self._worker_thread = threading.Thread(
            target=self._merge_worker,
            name="BacktestStreamWorker",
            daemon=True  # Don't prevent program exit
        )
        self._worker_thread.start()
        logger.info("Started backtest stream merge worker thread")
        
        # Start data-upkeep thread if enabled (Phase 2)
        if self._upkeep_thread is not None:
            self._upkeep_thread.start()
            logger.info("Started data-upkeep thread (Phase 2)")
    
    def stop_worker(self) -> None:
        """Stop the background worker thread gracefully.
        
        Phase 2: Also stops the data-upkeep thread.
        """
        # Stop data-upkeep thread first (Phase 2)
        if self._upkeep_thread is not None:
            self._upkeep_thread.stop(timeout=5.0)
            logger.info("Stopped data-upkeep thread (Phase 2)")
        
        if self._worker_thread is None or not self._worker_thread.is_alive():
            return
        
        self._shutdown.set()
        
        # Signal all input queues to unblock worker
        with self._lock:
            for q in self._active_streams.values():
                # Put None as sentinel to unblock queue.get()
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass
        
        # Wait for thread to finish (up to 5 seconds)
        self._worker_thread.join(timeout=5.0)
        if self._worker_thread.is_alive():
            logger.warning("Worker thread did not stop gracefully")
        else:
            logger.info("Stopped backtest stream merge worker thread")
        
        self._worker_thread = None
    
    def _merge_worker(self) -> None:
        """Background worker thread that merges multiple streams chronologically.
        
        Uses a min-heap to efficiently select the oldest data point across
        all active streams and yields it to the output queue.
        
        This runs in a dedicated thread for precise timing control.
        """
        logger.info("Merge worker thread started")
        
        # Keep track of which streams have pending data
        # This serves as our "peek" mechanism - we pull one item from each queue
        # and keep it here until it's the oldest across all streams
        pending_items: Dict[Tuple[str, StreamType], Optional[StreamItem]] = {}
        
        # Store reference so get_queue_stats can access it
        self._pending_items = pending_items
        
        try:
            while not self._shutdown.is_set() or self._active_streams:
                # Get snapshot of active streams
                with self._lock:
                    active_keys = list(self._active_streams.keys())
                
                if not active_keys:
                    # No active streams, wait a bit before checking again
                    time.sleep(0.1)
                    continue
                
                # Fetch next item from each stream that doesn't have pending data
                for stream_key in active_keys:
                    if stream_key in pending_items and pending_items[stream_key] is not None:
                        continue
                    
                    with self._lock:
                        q = self._active_streams.get(stream_key)
                    
                    if q is None:
                        continue
                    
                    try:
                        # Keep fetching from this stream until we get data >= current time
                        while True:
                            # Blocking get with timeout
                            data = q.get(timeout=0.1)
                            
                            # None is sentinel for stream exhaustion
                            if data is None:
                                pending_items[stream_key] = None
                                self.deregister_stream(stream_key[0], stream_key[1])
                                break
                            
                            # Extract timestamp (works for BarData, TickData, quotes)
                            if hasattr(data, 'timestamp'):
                                ts = data.timestamp
                            else:
                                logger.warning(f"Data missing timestamp attribute: {data}")
                                continue
                            
                            # Skip data older than current backtest time
                            # This handles cases where a new stream is registered mid-backtest
                            try:
                                current_time = self._time_provider.get_current_time()
                                if ts < current_time:
                                    logger.debug(
                                        f"Skipping stale data from {stream_key}: "
                                        f"{ts} < current time {current_time}"
                                    )
                                    continue  # Fetch next item from this stream
                            except ValueError:
                                # Backtest time not set yet (initial state), accept all data
                                pass
                            
                            # Data is current or future, accept it
                            pending_items[stream_key] = StreamItem(
                                timestamp=ts,
                                data=data,
                                stream_key=stream_key,
                            )
                            break  # Exit the while loop, move to next stream
                        
                    except queue.Empty:
                        # No data available yet, will try again next iteration
                        continue
                
                # Find oldest pending item across all streams
                oldest_item: Optional[StreamItem] = None
                oldest_key: Optional[Tuple[str, StreamType]] = None
                
                for stream_key, item in pending_items.items():
                    if item is None:
                        continue
                    if oldest_item is None or item.timestamp < oldest_item.timestamp:
                        oldest_item = item
                        oldest_key = stream_key
                
                # Yield oldest item to output queue
                if oldest_item is not None and oldest_key is not None:
                    # ADVANCE BACKTEST TIME to match the data being yielded
                    # This is the ONLY place where backtest time moves forward
                    
                    # SystemManager is REQUIRED for mode and state checks
                    if self._system_manager is None:
                        logger.error("SystemManager not available in BacktestStreamCoordinator - cannot determine mode")
                        # Without SystemManager, we cannot safely proceed
                        # Just yield data without time advancement or state checks
                        self._output_queue.put(oldest_item)
                        continue
                    
                    # Check if we're in backtest mode
                    mode_is_backtest = self._system_manager.is_backtest_mode()
                    
                    if mode_is_backtest:
                        # In backtest mode, check system state before advancing
                        # If system is not running, pause and wait
                        while not self._system_manager.is_running() and not self._shutdown.is_set():
                            # System is paused or stopped, wait for it to resume
                            time.sleep(0.1)
                            # Check if we should shutdown
                            if self._shutdown.is_set():
                                return
                        
                        # Determine the timestamp to set based on data type
                        # For BARS: timestamp represents the START of the interval (9:30 = 9:30:00-9:30:59)
                        #   so we set time to END of interval (9:31) to represent "bar is complete"
                        # For QUOTES/TICKS: timestamp is the exact event time, use as-is
                        stream_type = oldest_key[1]
                        if stream_type == StreamType.BAR:
                            # Add 1 minute to get end of bar interval
                            time_to_set = oldest_item.timestamp + timedelta(minutes=1)
                        else:
                            # Quote/tick: use exact timestamp
                            time_to_set = oldest_item.timestamp
                        
                        # Get current time before advancing
                        try:
                            prev_time = self._time_provider.get_current_time()
                            time_delta = (time_to_set - prev_time).total_seconds()
                        except ValueError:
                            # First item, no previous time
                            prev_time = None
                            time_delta = 0
                        
                        # Advance time
                        self._time_provider.set_backtest_time(time_to_set)
                        
                        # Apply realtime pacing if speed multiplier > 0
                        speed = settings.DATA_MANAGER_BACKTEST_SPEED
                        if speed > 0 and time_delta > 0:
                            # Calculate sleep time based on actual timestamp delta
                            # With high quality data (no gaps), this provides exact speed control
                            sleep_time = time_delta / speed
                            
                            # Enforce minimum sleep to prevent bursts and ensure consistent pacing
                            # Even if timestamps are very close, we always sleep a tiny bit
                            min_sleep = 0.001  # 1ms minimum
                            if sleep_time < min_sleep:
                                sleep_time = min_sleep
                            
                            time.sleep(sleep_time)
                        elif speed > 0:
                            # First item or zero delta: small delay to yield CPU
                            time.sleep(0.001)
                    
                    # Write data to session_data for AnalysisEngine and other consumers
                    symbol = oldest_key[0]
                    stream_type = oldest_key[1]
                    
                    if stream_type == StreamType.BAR:
                        # Write bar to session_data (async operation run in thread)
                        try:
                            import asyncio
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self._session_data.add_bar(symbol, oldest_item.data))
                            loop.close()
                        except Exception as e:
                            logger.error(f"Failed to write bar to session_data: {e}")
                    
                    self._output_queue.put(oldest_item.data)
                    # Mark this stream as needing new data
                    pending_items[oldest_key] = None
                else:
                    # No data available from any stream, wait a bit
                    time.sleep(0.01)
        
        except Exception as exc:
            logger.error(f"Merge worker error: {exc}", exc_info=True)
        finally:
            # Signal output queue is done
            self._output_queue.put(None)
            logger.info("Merge worker thread stopped")
    
    async def get_merged_stream(self) -> AsyncIterator[Any]:
        """Get the merged output stream in chronological order.
        
        Yields data from all active streams in timestamp order (oldest first).
        Continues until all streams are exhausted.
        
        Reads from the thread-safe output queue populated by the worker thread.
        
        Yields:
            Data objects (BarData, TickData, or quote objects) in chronological order
        """
        while True:
            # Read from thread-safe queue (runs in executor to not block event loop)
            data = await asyncio.to_thread(self._output_queue.get)
            if data is None:
                # Sentinel for end of stream
                break
            yield data
    
    async def feed_stream(
        self,
        symbol: str,
        stream_type: StreamType,
        data_iterator: AsyncIterator[Any],
    ) -> None:
        """Feed data from an iterator into a registered stream.
        
        This is typically called by DataManager.stream_bars/ticks/quotes
        to push their database query results into the coordinator.
        
        Args:
            symbol: Stock symbol
            stream_type: Type of data
            data_iterator: Async iterator yielding data objects
        """
        stream_key = (symbol.upper(), stream_type)
        
        with self._lock:
            input_queue = self._active_streams.get(stream_key)
        
        if input_queue is None:
            logger.error(
                f"Cannot feed stream for {stream_key} - stream not registered"
            )
            return
        
        # Track timestamps as data flows through
        first_ts = None
        last_ts = None
        item_count = 0
        
        try:
            async for data in data_iterator:
                # Put into thread-safe queue (runs in executor to not block event loop)
                await asyncio.to_thread(input_queue.put, data)
                
                # Track timestamps for queue statistics
                if hasattr(data, 'timestamp'):
                    ts = data.timestamp
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts  # Keep updating to get the newest
                    item_count += 1
            
            # Update timestamp tracking with data from this stream
            if first_ts and last_ts:
                with self._lock:
                    if stream_key in self._queue_timestamps:
                        # Initialize with first timestamp seen
                        if self._queue_timestamps[stream_key]["newest"] is None:
                            self._queue_timestamps[stream_key]["newest"] = first_ts
                        
                        # Update to keep the maximum (newest) timestamp
                        if last_ts > self._queue_timestamps[stream_key]["newest"]:
                            self._queue_timestamps[stream_key]["newest"] = last_ts
        
        finally:
            # Signal stream exhaustion
            await asyncio.to_thread(input_queue.put, None)
            logger.info(f"Stream feed completed for {stream_key}: {item_count} items streamed")


# Global singleton coordinator instance
_coordinator: Optional[BacktestStreamCoordinator] = None


def get_coordinator(system_manager=None) -> BacktestStreamCoordinator:
    """Get or create the global backtest stream coordinator instance.
    
    Args:
        system_manager: Reference to SystemManager (REQUIRED for production use)
                       The coordinator needs SystemManager to:
                       - Determine operation mode (live vs backtest)
                       - Check system state (running/paused/stopped)
                       - Pause time advancement when system is paused
    
    The coordinator will use the singleton TimeProvider instance, ensuring
    time is synchronized across all components.
    
    WARNING: If system_manager is None, the coordinator will log errors and
    cannot properly manage backtest time advancement or respect system state.
    """
    global _coordinator
    if _coordinator is None:
        _coordinator = BacktestStreamCoordinator(system_manager=system_manager)
    return _coordinator


async def reset_coordinator() -> None:
    """Reset the global coordinator (useful for testing or reinitialization)."""
    global _coordinator
    if _coordinator is not None:
        await _coordinator.stop_worker()
    _coordinator = None
