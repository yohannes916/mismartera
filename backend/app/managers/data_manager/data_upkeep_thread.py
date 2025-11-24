"""Data-Upkeep Thread for Session Data Quality Management

This module implements a background thread that maintains data quality by:
1. Detecting gaps in bar data
2. Automatically filling missing bars from database
3. Computing derived bars (5m, 15m, etc.)
4. Updating bar quality metrics

The upkeep thread runs independently of the main coordinator thread,
coordinating access to session_data via thread-safe locks.
"""
import threading
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from collections import defaultdict

from app.config import settings
from app.logger import logger
from app.managers.data_manager.session_data import SessionData
from app.managers.data_manager.gap_detection import (
    detect_gaps,
    GapInfo,
    merge_overlapping_gaps
)
from app.managers.data_manager.quality_checker import calculate_session_quality
from app.managers.data_manager.derived_bars import compute_all_derived_intervals


class DataUpkeepThread:
    """Background thread for data quality maintenance.
    
    Responsibilities:
    - Detect gaps in 1-minute bar data
    - Fill missing bars from database
    - Compute derived bars (5m, 15m, etc.)
    - Update bar_quality metrics
    - Retry failed operations
    
    Thread-safe coordination with main coordinator thread via session_data locks.
    """
    
    def __init__(
        self,
        session_data: SessionData,
        system_manager,
        data_repository=None
    ):
        """Initialize data-upkeep thread.
        
        Args:
            session_data: Reference to session_data singleton
            system_manager: Reference to SystemManager for mode/state checks
            data_repository: Data repository for fetching missing bars
        """
        self._session_data = session_data
        self._system_manager = system_manager
        self._data_repository = data_repository
        
        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._running = False
        
        # Configuration
        self._check_interval = settings.DATA_UPKEEP_CHECK_INTERVAL_SECONDS
        self._retry_enabled = settings.DATA_UPKEEP_RETRY_MISSING_BARS
        self._max_retries = settings.DATA_UPKEEP_MAX_RETRIES
        self._derived_intervals = settings.DATA_UPKEEP_DERIVED_INTERVALS
        self._auto_compute_derived = settings.DATA_UPKEEP_AUTO_COMPUTE_DERIVED
        
        # Gap tracking for retry
        self._failed_gaps: Dict[str, List[GapInfo]] = defaultdict(list)
        self._last_check_time: Dict[str, datetime] = {}
        
        logger.info(
            f"DataUpkeepThread initialized: "
            f"check_interval={self._check_interval}s, "
            f"derived_intervals={self._derived_intervals}"
        )
    
    def start(self) -> None:
        """Start the upkeep thread."""
        if self._running:
            logger.warning("DataUpkeepThread already running")
            return
        
        self._shutdown.clear()
        self._running = True
        
        self._thread = threading.Thread(
            target=self._upkeep_worker,
            name="DataUpkeepThread",
            daemon=True
        )
        self._thread.start()
        
        logger.info("DataUpkeepThread started")
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop the upkeep thread.
        
        Args:
            timeout: Maximum seconds to wait for thread to stop
        """
        if not self._running:
            return
        
        logger.info("Stopping DataUpkeepThread...")
        
        self._shutdown.set()
        
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("DataUpkeepThread did not stop within timeout")
            else:
                logger.info("DataUpkeepThread stopped")
        
        self._running = False
    
    def _upkeep_worker(self) -> None:
        """Main worker loop for upkeep thread.
        
        Runs continuously, checking data quality and performing maintenance.
        """
        logger.info("DataUpkeepThread worker started")
        
        try:
            while not self._shutdown.is_set():
                try:
                    # Check if system is in appropriate state
                    if not self._should_run_upkeep():
                        time.sleep(1.0)
                        continue
                    
                    # Perform upkeep tasks
                    self._run_upkeep_cycle()
                    
                    # Sleep until next check
                    self._shutdown.wait(self._check_interval)
                    
                except Exception as e:
                    logger.error(f"Error in upkeep cycle: {e}", exc_info=True)
                    time.sleep(5.0)  # Brief delay before retry
        
        except Exception as e:
            logger.critical(f"DataUpkeepThread crashed: {e}", exc_info=True)
        
        finally:
            logger.info("DataUpkeepThread worker exiting")
    
    def _should_run_upkeep(self) -> bool:
        """Check if upkeep should run based on system state.
        
        Returns:
            True if upkeep should run
        """
        if self._system_manager is None:
            return False
        
        # Only run in backtest mode when system is running
        if self._system_manager.is_backtest_mode():
            return self._system_manager.is_running()
        
        # In live mode, always run
        return True
    
    def _run_upkeep_cycle(self) -> None:
        """Run one cycle of upkeep tasks."""
        # Get active symbols
        active_symbols = self._session_data.get_active_symbols()
        
        if not active_symbols:
            logger.debug("No active symbols, skipping upkeep")
            return
        
        logger.debug(f"Running upkeep cycle for {len(active_symbols)} symbols")
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for symbol in active_symbols:
                try:
                    # Run upkeep for this symbol
                    loop.run_until_complete(self._upkeep_symbol(symbol))
                except Exception as e:
                    logger.error(f"Error in upkeep for {symbol}: {e}", exc_info=True)
        
        finally:
            loop.close()
    
    async def _upkeep_symbol(self, symbol: str) -> None:
        """Perform upkeep for a single symbol.
        
        Args:
            symbol: Stock symbol
        """
        # Get symbol data
        symbol_data = await self._session_data.get_symbol_data(symbol)
        if symbol_data is None:
            return
        
        # Skip if no data yet
        if len(symbol_data.bars_1m) == 0:
            return
        
        # 1. Check and update bar quality
        await self._update_bar_quality(symbol)
        
        # 2. Detect and fill gaps
        if self._retry_enabled:
            await self._check_and_fill_gaps(symbol)
        
        # 3. Compute derived bars if needed
        if self._auto_compute_derived and symbol_data.bars_updated:
            await self._update_derived_bars(symbol)
    
    async def _update_bar_quality(self, symbol: str) -> None:
        """Update bar quality metric for a symbol.
        
        Args:
            symbol: Stock symbol
        """
        symbol_data = await self._session_data.get_symbol_data(symbol)
        if symbol_data is None:
            return
        
        # Get time provider for current time (single source of truth)
        from app.managers.data_manager.time_provider import get_time_provider
        time_provider = get_time_provider(self._system_manager)
        
        try:
            current_time = time_provider.get_current_time()
        except ValueError:
            # Backtest time not set yet
            return
        
        # Get trading hours from data_manager (single source of truth)
        # This accounts for holidays, early closes, etc.
        current_date = current_time.date()
        
        from app.models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            data_manager = self._system_manager.get_data_manager()
            trading_hours = await data_manager.get_trading_hours(session, current_date)
            
            if trading_hours is None:
                # Market closed today (holiday)
                return
            
            session_start_time = datetime.combine(current_date, trading_hours.open_time)
        
        # Calculate quality using centralized checker
        quality = calculate_session_quality(
            session_start=session_start_time,
            current_time=current_time,
            actual_bar_count=len(symbol_data.bars_1m)
        )
        
        # Update in session_data
        async with self._session_data._lock:
            symbol_data.bar_quality = quality
        
        if quality < 100.0:
            logger.debug(f"{symbol} bar quality: {quality:.1f}%")
    
    async def _check_and_fill_gaps(self, symbol: str) -> None:
        """Detect gaps and attempt to fill them.
        
        Args:
            symbol: Stock symbol
        """
        symbol_data = await self._session_data.get_symbol_data(symbol)
        if symbol_data is None:
            return
        
        # Get current time (TimeProvider is single source of truth)
        from app.managers.data_manager.time_provider import get_time_provider
        time_provider = get_time_provider(self._system_manager)
        
        try:
            current_time = time_provider.get_current_time()
        except ValueError:
            return
        
        # Get trading hours from data_manager (single source of truth)
        # This accounts for holidays, early closes, etc.
        current_date = current_time.date()
        
        from app.models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            data_manager = self._system_manager.get_data_manager()
            trading_hours = await data_manager.get_trading_hours(session, current_date)
            
            if trading_hours is None:
                # Market closed today (holiday)
                return
            
            session_start_time = datetime.combine(current_date, trading_hours.open_time)
        
        # Detect gaps
        bars_1m = list(symbol_data.bars_1m)
        gaps = detect_gaps(
            symbol=symbol,
            session_start=session_start_time,
            current_time=current_time,
            existing_bars=bars_1m
        )
        
        # Add previously failed gaps for retry
        if symbol in self._failed_gaps:
            gaps.extend(self._failed_gaps[symbol])
            gaps = merge_overlapping_gaps(gaps)
        
        if not gaps:
            return
        
        # Attempt to fill gaps
        filled_count = 0
        remaining_gaps = []
        
        for gap in gaps:
            if gap.retry_count >= self._max_retries:
                logger.warning(f"Max retries reached for gap: {gap}")
                continue
            
            # Try to fill this gap
            try:
                count = await self._fill_gap(symbol, gap)
                filled_count += count
                
                if count < gap.bar_count:
                    # Partial fill or failure
                    gap.retry_count += 1
                    gap.last_retry = time_provider.get_current_time()
                    remaining_gaps.append(gap)
            
            except Exception as e:
                logger.error(f"Error filling gap: {e}")
                gap.retry_count += 1
                remaining_gaps.append(gap)
        
        # Update failed gaps
        self._failed_gaps[symbol] = remaining_gaps
        
        if filled_count > 0:
            logger.info(f"Filled {filled_count} bars for {symbol}")
    
    async def _fill_gap(self, symbol: str, gap: GapInfo) -> int:
        """Fill a single gap by fetching from database.
        
        Args:
            symbol: Stock symbol
            gap: Gap to fill
            
        Returns:
            Number of bars filled
        """
        if self._data_repository is None:
            logger.debug(f"No data_repository available, skipping gap fill for {symbol}")
            return 0
        
        logger.debug(f"Attempting to fill gap: {gap}")
        
        try:
            # Fetch bars from database
            # The data_repository should have a method like get_bars_by_symbol
            # which queries the market data database
            
            # Try different possible repository interfaces
            bars_db = None
            
            # Method 1: If data_repository is a database session
            if hasattr(self._data_repository, 'execute'):
                from app.repositories.market_data_repository import MarketDataRepository
                bars_db = await MarketDataRepository.get_bars_by_symbol(
                    session=self._data_repository,
                    symbol=symbol,
                    start_date=gap.start_time,
                    end_date=gap.end_time,
                    interval="1m"
                )
            
            # Method 2: If data_repository has a direct get_bars method
            elif hasattr(self._data_repository, 'get_bars_by_symbol'):
                bars_db = await self._data_repository.get_bars_by_symbol(
                    symbol=symbol,
                    start_date=gap.start_time,
                    end_date=gap.end_time,
                    interval="1m"
                )
            
            # Method 3: Generic get_bars interface
            elif hasattr(self._data_repository, 'get_bars'):
                bars_db = await self._data_repository.get_bars(
                    symbol=symbol,
                    start=gap.start_time,
                    end=gap.end_time,
                    interval=1
                )
            else:
                logger.warning(
                    f"data_repository has no recognized interface for fetching bars. "
                    f"Available methods: {dir(self._data_repository)}"
                )
                return 0
            
            if not bars_db:
                logger.debug(f"No bars found in database for gap: {gap}")
                return 0
            
            # Convert database bars to BarData format
            from app.models.trading import BarData
            bars_to_insert = []
            
            for db_bar in bars_db:
                # Handle different possible database schemas
                try:
                    bar = BarData(
                        symbol=symbol,
                        timestamp=db_bar.timestamp,
                        open=float(db_bar.open),
                        high=float(db_bar.high),
                        low=float(db_bar.low),
                        close=float(db_bar.close),
                        volume=int(db_bar.volume) if db_bar.volume else 0
                    )
                    bars_to_insert.append(bar)
                except (AttributeError, TypeError, ValueError) as e:
                    logger.error(f"Failed to convert database bar to BarData: {e}")
                    continue
            
            if not bars_to_insert:
                logger.warning(f"No valid bars to insert for gap: {gap}")
                return 0
            
            # Insert bars into session_data using gap_fill mode to maintain chronological order
            await self._session_data.add_bars_batch(symbol, bars_to_insert, insert_mode="gap_fill")
            
            logger.info(
                f"Successfully filled {len(bars_to_insert)} bars for {symbol} "
                f"from {gap.start_time} to {gap.end_time}"
            )
            
            return len(bars_to_insert)
        
        except Exception as e:
            logger.error(
                f"Error filling gap for {symbol} ({gap.start_time} to {gap.end_time}): {e}",
                exc_info=True
            )
            return 0
    
    async def _update_derived_bars(self, symbol: str) -> None:
        """Recompute derived bars when 1m bars are updated.
        
        Priority: Compute each interval as soon as enough 1m bars are available.
        This allows 5m bars to be computed before 15m bars, providing faster feedback.
        
        Args:
            symbol: Stock symbol
        """
        symbol_data = await self._session_data.get_symbol_data(symbol)
        if symbol_data is None or not symbol_data.bars_updated:
            return
        
        # Get 1m bars
        bars_1m = list(symbol_data.bars_1m)
        total_bars = len(bars_1m)
        
        if total_bars == 0:
            return
        
        # Compute derived bars for each interval independently
        # PRIORITY: Compute as soon as we have enough bars for that specific interval
        derived_bars = {}
        intervals_computed = []
        
        for interval in sorted(self._derived_intervals):  # Process in ascending order
            if total_bars >= interval:
                # We have enough bars for this interval
                bars_for_interval = compute_all_derived_intervals(bars_1m, [interval])
                if interval in bars_for_interval:
                    derived_bars[interval] = bars_for_interval[interval]
                    intervals_computed.append(interval)
        
        if not derived_bars:
            # Not enough bars for even the smallest interval
            return
        
        # Update in session_data
        async with self._session_data._lock:
            for interval, bars in derived_bars.items():
                symbol_data.bars_derived[interval] = bars
            
            # Reset update flag
            symbol_data.bars_updated = False
        
        logger.debug(
            f"Updated derived bars for {symbol} ({total_bars} 1m bars): "
            f"{', '.join(f'{k}m={len(v)} bars' for k, v in derived_bars.items())}"
        )
    
    def get_status(self) -> Dict[str, any]:
        """Get current status of upkeep thread.
        
        Returns:
            Dictionary with status information
        """
        return {
            "running": self._running,
            "check_interval": self._check_interval,
            "derived_intervals": self._derived_intervals,
            "failed_gaps_count": sum(len(gaps) for gaps in self._failed_gaps.values()),
            "symbols_with_failed_gaps": list(self._failed_gaps.keys())
        }


# Singleton instance management
_upkeep_thread_instance: Optional[DataUpkeepThread] = None


def get_upkeep_thread(
    session_data: SessionData,
    system_manager,
    data_repository=None
) -> DataUpkeepThread:
    """Get or create the global DataUpkeepThread instance.
    
    Args:
        session_data: SessionData singleton
        system_manager: SystemManager reference
        data_repository: Optional data repository
        
    Returns:
        DataUpkeepThread instance
    """
    global _upkeep_thread_instance
    if _upkeep_thread_instance is None:
        _upkeep_thread_instance = DataUpkeepThread(
            session_data,
            system_manager,
            data_repository
        )
    return _upkeep_thread_instance


def reset_upkeep_thread() -> None:
    """Reset the global upkeep thread instance (for testing)."""
    global _upkeep_thread_instance
    if _upkeep_thread_instance and _upkeep_thread_instance._running:
        _upkeep_thread_instance.stop()
    _upkeep_thread_instance = None
