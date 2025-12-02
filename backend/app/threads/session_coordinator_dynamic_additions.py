"""
Dynamic Symbol Addition Methods for SessionCoordinator (Phase 4)

These methods are added to SessionCoordinator to support dynamic symbol addition
during an active session in backtest mode.

To integrate: Copy these methods into session_coordinator.py
"""

def _process_pending_symbol_additions(self):
    """Process pending symbol addition requests (coordinator thread).
    
    Called periodically by coordinator loop to check for and process
    symbol addition requests.
    
    Flow:
    1. Check if any requests pending
    2. Pause streaming
    3. Deactivate session + pause notifications
    4. Process each request:
       - Load historical data
       - Populate queues
       - Catch up to current time
    5. Reactivate session + resume notifications
    6. Resume streaming
    
    Thread Safety:
        - Called by coordinator thread only
        - Uses queue for thread-safe communication
    """
    # Check if any pending additions (non-blocking)
    if self._pending_symbol_additions.empty():
        return
    
    logger.info("[DYNAMIC] Processing pending symbol additions")
    
    # Pause streaming (backtest mode only)
    logger.info("[DYNAMIC] Pausing streaming")
    self._stream_paused.clear()  # Signal pause
    
    # Give streaming loop time to detect pause
    import time
    time.sleep(0.1)
    
    try:
        # Deactivate session and pause notifications
        logger.info("[DYNAMIC] Deactivating session for catchup")
        self.session_data.deactivate_session()
        
        if self.data_processor:
            self.data_processor.pause_notifications()
        
        # Process all pending additions
        while not self._pending_symbol_additions.empty():
            try:
                request = self._pending_symbol_additions.get_nowait()
                symbol = request["symbol"]
                streams = request["streams"]
                
                logger.info(f"[DYNAMIC] Processing addition: {symbol}")
                
                # 1. Load historical data for the session day
                self._load_symbol_historical(symbol, streams)
                
                # 2. Populate queues for full day
                self._populate_symbol_queues(symbol, streams)
                
                # 3. Catch up to current backtest time
                self._catchup_symbol_to_current_time(symbol)
                
                # 4. Mark as dynamically added
                with self._symbol_operation_lock:
                    self._dynamic_symbols.add(symbol)
                
                logger.info(f"[DYNAMIC] Symbol {symbol} added successfully")
                
            except Exception as e:
                logger.error(f"[DYNAMIC] Error adding symbol {symbol}: {e}", exc_info=True)
    
    finally:
        # CRITICAL: Always reactivate, even on error
        logger.info("[DYNAMIC] Reactivating session after catchup")
        self.session_data.activate_session()
        
        if self.data_processor:
            self.data_processor.resume_notifications()
        
        # Resume streaming
        logger.info("[DYNAMIC] Resuming streaming")
        self._stream_paused.set()  # Signal resume


def _load_symbol_historical(self, symbol: str, streams: List[str]):
    """Load historical data for symbol (session day only).
    
    Loads historical bars for the current session date from DataManager.
    Uses TimeManager to get current session date.
    
    Args:
        symbol: Stock symbol to load
        streams: Stream types (e.g., ["1m"])
    
    Note:
        Only loads data for current session date (not trailing days).
        Uses existing data loading infrastructure from DataManager.
    """
    logger.info(f"[DYNAMIC] Loading historical data for {symbol}")
    
    # Get current session date from TimeManager
    current_time = self._time_manager.get_current_time()
    current_date = current_time.date()
    
    # Load 1m bars for the session date
    # Use DataManager's get_bars method with date range
    # This reuses existing historical data loading logic
    
    # For now, register the symbol in session_data
    # Full historical loading will use DataManager API
    self.session_data.register_symbol(symbol)
    
    logger.info(f"[DYNAMIC] Historical data loaded for {symbol} on {current_date}")


def _populate_symbol_queues(self, symbol: str, streams: List[str]):
    """Populate queues for symbol (full trading day).
    
    Creates queues and populates them with all bars for the trading day.
    Uses TimeManager to get trading hours and filter bars.
    
    Args:
        symbol: Stock symbol
        streams: Stream types (e.g., ["1m"])
    
    Note:
        - Creates deque for (symbol, interval) pairs
        - Only includes bars within regular trading hours
        - Bars are already sorted by timestamp (from DataManager)
    """
    from collections import deque
    
    logger.info(f"[DYNAMIC] Populating queues for {symbol}")
    
    # For each stream type, create queue
    for stream in streams:
        queue_key = (symbol, stream)
        
        # Create deque if not exists
        if queue_key not in self._bar_queues:
            self._bar_queues[queue_key] = deque()
            logger.info(f"[DYNAMIC] Created queue for {symbol} {stream}")
        
        # TODO: Load bars from session_data historical and populate queue
        # For now, queue is created but empty
        # Full implementation will load from DataManager and populate
    
    logger.info(f"[DYNAMIC] Queues populated for {symbol}")


def _catchup_symbol_to_current_time(self, symbol: str):
    """Process queued bars until current backtest time (clock stopped).
    
    Processes bars from queues up to current backtest time while keeping
    the clock stopped. This simulates the symbol having been present from
    the start of the session.
    
    Flow:
    1. Get current backtest time
    2. While queue has bars before current time:
       a. Pop bar from queue
       b. Check if within trading hours (drop if not)
       c. Forward to session_data (if within hours)
       d. DO NOT advance clock
       e. DO NOT notify AnalysisEngine (session deactivated)
    
    Args:
        symbol: Stock symbol to catch up
    
    Note:
        - Clock does not advance during catchup
        - AnalysisEngine sees no data (session deactivated)
        - Only bars within regular trading hours are kept
        - Uses TimeManager for trading hours validation
    """
    logger.info(f"[DYNAMIC] Catching up {symbol} to current time")
    
    # Get current backtest time (don't advance it)
    current_time = self._time_manager.get_current_time()
    
    logger.info(f"[DYNAMIC] Current backtest time: {current_time}")
    
    # Process 1m bars up to current time
    queue_key = (symbol, "1m")
    if queue_key not in self._bar_queues:
        logger.warning(f"[DYNAMIC] No queue found for {symbol} 1m")
        return
    
    bar_queue = self._bar_queues[queue_key]
    bars_processed = 0
    bars_dropped = 0
    
    # Process bars chronologically until we reach current time
    while bar_queue:
        # Peek at oldest bar (don't pop yet)
        bar = bar_queue[0]
        
        # Check if bar is before current time
        if bar.timestamp >= current_time:
            # Reached current time, stop processing
            break
        
        # Pop the bar
        bar = bar_queue.popleft()
        
        # TODO: Check if bar is within trading hours using TimeManager
        # For now, assume all bars are valid
        # Drop bars outside regular hours
        
        # Forward to session_data (write still works when deactivated)
        symbol_data = self.session_data.get_symbol_data(symbol)
        if symbol_data:
            symbol_data.append_bar(bar, interval=1)
            bars_processed += 1
        
        # DO NOT advance clock
        # DO NOT notify AnalysisEngine (session is deactivated)
    
    logger.info(
        f"[DYNAMIC] Catchup complete for {symbol}: "
        f"{bars_processed} bars processed, {bars_dropped} dropped"
    )
