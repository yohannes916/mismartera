"""
Prefetch Worker - Background thread for loading market data into coordinator queues

This worker runs in a thread pool and loads historical bar data for trading days.
It's used by the upkeep thread to:
1. Load full day data on EOD transitions (open to close)
2. Load historical data on mid-session starts (open to current time)
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import date, datetime, timezone
from typing import List, Optional

from app.logger import logger
from app.models.session_config import StreamType


class PrefetchWorker:
    """Background worker for prefetching market data into coordinator queues"""
    
    def __init__(self, data_manager, system_manager):
        """
        Initialize prefetch worker
        
        Args:
            data_manager: DataManager instance
            system_manager: SystemManager instance
        """
        self._data_manager = data_manager
        self._system_manager = system_manager
        self._executor = ThreadPoolExecutor(
            max_workers=1, 
            thread_name_prefix="prefetch"
        )
        self._current_future: Optional[Future] = None
        self._lock = threading.Lock()
        
        logger.info("PrefetchWorker initialized")
    
    def start_prefetch(
        self, 
        target_date: date, 
        symbols: List[str], 
        interval: str, 
        start_time: Optional[datetime] = None
    ) -> Future:
        """
        Launch prefetch for target date
        
        Args:
            target_date: Date to prefetch data for
            symbols: List of symbols to prefetch
            interval: Bar interval (1m, 1s)
            start_time: Optional - load data from market open to this time (for mid-session start)
                       If None, loads full day from open to close
        
        Returns:
            Future that completes when prefetch is done
        """
        with self._lock:
            # Cancel previous prefetch if still running
            if self._current_future and not self._current_future.done():
                logger.warning("Previous prefetch still running, will be replaced")
            
            logger.info(
                f"Starting prefetch for {target_date} "
                f"({len(symbols)} symbols, interval={interval}, end_time={start_time})"
            )
            
            self._current_future = self._executor.submit(
                self._prefetch_worker,
                target_date,
                symbols,
                interval,
                start_time
            )
            
            return self._current_future
    
    def _prefetch_worker(
        self, 
        target_date: date, 
        symbols: List[str], 
        interval: str, 
        start_time: Optional[datetime]
    ) -> bool:
        """
        Worker function - runs in thread pool
        
        Returns:
            True if prefetch successful, False otherwise
        """
        try:
            # Run prefetch directly (no event loop needed)
            result = self._load_day_data(target_date, symbols, interval, start_time)
            
            logger.info(f"Prefetch completed for {target_date}: success={result}")
            return result
                
        except Exception as e:
            logger.error(f"Prefetch failed for {target_date}: {e}", exc_info=True)
            return False
    
    def _load_day_data(
        self, 
        target_date: date, 
        symbols: List[str],
        interval: str, 
        start_time: Optional[datetime]
    ) -> bool:
        """
        Load data and populate coordinator queues
        
        Args:
            target_date: Date to load data for
            symbols: Symbols to load
            interval: Bar interval
            start_time: If provided, load from open to this time. If None, load full day.
        
        Returns:
            True if successful
        """
        from app.models.database import SessionLocal
        
        try:
            with SessionLocal() as db_session:
                time_mgr = self._system_manager.get_time_manager()
                
                # Get trading session for target date
                trading_session = time_mgr.get_trading_session(db_session, target_date)
                
                if not trading_session:
                    logger.warning(f"No trading session found for {target_date}")
                    return False
                
                if trading_session.is_holiday:
                    logger.warning(f"{target_date} is a holiday, skipping prefetch")
                    return False
                
                # Determine time range using TradingSession helper methods
                from datetime import timedelta
                day_open = trading_session.get_regular_open_datetime()
                day_close = trading_session.get_regular_close_datetime()
                # Add 1-minute buffer to capture close-of-day data (e.g., 16:00 bar)
                day_close_with_buffer = day_close + timedelta(minutes=1)
                
                # For mid-session start: load from open to start_time
                # For normal EOD transition: load full day (open to close + buffer)
                end_time = start_time if start_time else day_close_with_buffer
                
                logger.info(
                    f"Loading {interval} bars for {target_date}: "
                    f"{day_open.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')}"
                )
                
                # Load bars for each symbol
                total_bars = 0
                for symbol in symbols:
                    bars = self._data_manager.get_bars(
                        db_session,
                        symbol=symbol,
                        interval=interval,
                        start=day_open,
                        end=end_time
                    )
                    
                    if bars:
                        # Prefetch is disabled for now - coordinator uses feed_stream which expects iterators
                        # Bars are loaded on-demand via start_bar_streams instead
                        total_bars += len(bars)
                        logger.debug(f"Loaded {len(bars)} {interval} bars for {symbol} (prefetch disabled)")
                    else:
                        logger.warning(f"No bars found for {symbol} on {target_date}")
                
                logger.info(f"Prefetch complete: {total_bars} total bars loaded")
                return total_bars > 0
                
        except Exception as e:
            logger.error(f"Error loading day data for {target_date}: {e}", exc_info=True)
            return False
    
    def is_prefetch_running(self) -> bool:
        """Check if prefetch is currently running"""
        with self._lock:
            return self._current_future is not None and not self._current_future.done()
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """
        Wait for current prefetch to complete
        
        Args:
            timeout: Maximum seconds to wait
        
        Returns:
            True if prefetch completed successfully, False otherwise
        """
        with self._lock:
            future = self._current_future
        
        if not future:
            logger.debug("No prefetch to wait for")
            return True
        
        try:
            result = future.result(timeout=timeout)
            return result
        except TimeoutError:
            logger.error(f"Prefetch timed out after {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Prefetch wait failed: {e}")
            return False
    
    def shutdown(self):
        """Shutdown prefetch worker and wait for completion"""
        logger.info("Shutting down prefetch worker")
        
        # Wait for current task to complete
        with self._lock:
            if self._current_future and not self._current_future.done():
                logger.info("Waiting for current prefetch to complete...")
        
        # Shutdown executor (waits for tasks)
        self._executor.shutdown(wait=True)
        logger.info("Prefetch worker shutdown complete")
