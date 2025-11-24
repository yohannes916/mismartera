"""Prefetch Manager for Zero-Delay Session Transitions

Manages intelligent prefetching of market data to eliminate session startup delays.

Architecture:
- Background thread monitors for next session
- Prefetches historical data before session starts
- Swaps cache into session_data on session start
- Result: 1-2 second startup → <50ms
"""
import threading
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from app.config import settings
from app.logger import logger
from app.managers.data_manager.session_detector import SessionDetector
from app.models.trading import BarData


@dataclass
class SymbolPrefetchData:
    """Prefetched data for a single symbol."""
    symbol: str
    session_date: date
    historical_bars: Dict[int, Dict[date, List[BarData]]]  # {interval: {date: [bars]}}
    prefetch_time: datetime
    bar_count: int = 0
    
    def __post_init__(self):
        """Calculate total bar count."""
        self.bar_count = sum(
            sum(len(bars) for bars in date_bars.values())
            for date_bars in self.historical_bars.values()
        )


class PrefetchManager:
    """Manage prefetching of market data for next session.
    
    Responsibilities:
    - Monitor for next trading session
    - Prefetch historical data before session starts
    - Cache prefetched data
    - Activate cache on session start
    - Background thread coordination
    """
    
    def __init__(
        self,
        session_data,
        data_repository,
        session_detector: Optional[SessionDetector] = None
    ):
        """Initialize prefetch manager.
        
        Args:
            session_data: SessionData singleton
            data_repository: Database access for loading data
            session_detector: SessionDetector instance (default: new instance)
        """
        self._session_data = session_data
        self._data_repository = data_repository
        self._detector = session_detector or SessionDetector()
        
        # Prefetch cache
        self._prefetch_cache: Dict[str, SymbolPrefetchData] = {}
        self._prefetch_session_date: Optional[date] = None
        self._prefetch_complete = False
        self._prefetch_in_progress = False
        
        # Background thread
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._running = False
        
        # Configuration
        self._check_interval = settings.PREFETCH_CHECK_INTERVAL_MINUTES * 60
        self._auto_activate = settings.PREFETCH_AUTO_ACTIVATE
        
        logger.info(
            f"PrefetchManager initialized: "
            f"check_interval={self._check_interval}s, "
            f"auto_activate={self._auto_activate}"
        )
    
    def start(self) -> None:
        """Start prefetch monitoring thread."""
        if self._running:
            logger.warning("PrefetchManager already running")
            return
        
        self._shutdown.clear()
        self._running = True
        
        self._thread = threading.Thread(
            target=self._prefetch_worker,
            name="PrefetchThread",
            daemon=True
        )
        self._thread.start()
        
        logger.info("PrefetchManager started")
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop prefetch thread.
        
        Args:
            timeout: Maximum seconds to wait for thread to stop
        """
        if not self._running:
            return
        
        logger.info("Stopping PrefetchManager...")
        
        self._shutdown.set()
        
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("PrefetchManager did not stop within timeout")
            else:
                logger.info("PrefetchManager stopped")
        
        self._running = False
    
    def _prefetch_worker(self) -> None:
        """Background worker that monitors and prefetches."""
        logger.info("PrefetchManager worker started")
        
        try:
            while not self._shutdown.is_set():
                try:
                    # Check if prefetch needed
                    self._check_and_prefetch_sync()
                    
                    # Sleep until next check
                    self._shutdown.wait(self._check_interval)
                
                except Exception as e:
                    logger.error(f"Error in prefetch worker: {e}", exc_info=True)
                    self._shutdown.wait(60)  # Brief delay before retry
        
        except Exception as e:
            logger.critical(f"PrefetchManager worker crashed: {e}", exc_info=True)
        
        finally:
            logger.info("PrefetchManager worker exiting")
    
    def _check_and_prefetch_sync(self) -> None:
        """Check if prefetch needed and execute (synchronous wrapper)."""
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._check_and_prefetch())
        finally:
            loop.close()
    
    async def _check_and_prefetch(self) -> None:
        """Check if prefetch needed and execute."""
        # Don't prefetch if already in progress
        if self._prefetch_in_progress:
            logger.debug("Prefetch already in progress, skipping check")
            return
        
        # Get current session
        current_session = self._session_data.current_session_date
        if current_session is None:
            logger.debug("No current session, skipping prefetch check")
            return
        
        # Get next session
        next_session = self._detector.get_next_session(current_session, skip_today=True)
        if next_session is None:
            logger.debug("No next session found, skipping prefetch")
            return
        
        # Already prefetched for this session?
        if (self._prefetch_complete and 
            self._prefetch_session_date == next_session):
            logger.debug(f"Already prefetched for {next_session}")
            return
        
        # Should prefetch now? Use TimeProvider as single source of truth
        from app.managers.data_manager.time_provider import get_time_provider
        now = get_time_provider().get_current_time()
        if not self._detector.should_prefetch(now, next_session):
            # Not time yet
            time_until = self._detector.get_time_until_next_session(now, current_session)
            if time_until:
                logger.debug(
                    f"Not time to prefetch yet: {time_until.total_seconds()/3600:.1f} "
                    f"hours until next session"
                )
            return
        
        # Execute prefetch
        logger.info(f"Starting prefetch for session: {next_session}")
        await self._execute_prefetch(next_session)
    
    async def _execute_prefetch(self, session_date: date) -> None:
        """Execute prefetch for given session.
        
        Args:
            session_date: Session date to prefetch for
        """
        self._prefetch_in_progress = True
        
        try:
            # Get active symbols
            symbols = self._session_data.get_active_symbols()
            if not symbols:
                logger.warning("No active symbols to prefetch")
                return
            
            # Clear old cache
            self._prefetch_cache.clear()
            self._prefetch_session_date = session_date
            self._prefetch_complete = False
            
            logger.info(f"Prefetching for {len(symbols)} symbols")
            
            # Load for each symbol
            success_count = 0
            for symbol in symbols:
                try:
                    await self._prefetch_symbol(symbol, session_date)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error prefetching {symbol}: {e}", exc_info=True)
            
            self._prefetch_complete = True
            
            total_bars = sum(data.bar_count for data in self._prefetch_cache.values())
            logger.info(
                f"Prefetch complete: {success_count}/{len(symbols)} symbols, "
                f"{total_bars} total bars"
            )
        
        except Exception as e:
            logger.error(f"Error in prefetch execution: {e}", exc_info=True)
            self._prefetch_complete = False
        
        finally:
            self._prefetch_in_progress = False
    
    async def _prefetch_symbol(
        self,
        symbol: str,
        session_date: date
    ) -> None:
        """Prefetch historical data for single symbol.
        
        Args:
            symbol: Stock symbol
            session_date: Session date to prefetch for
        """
        if self._data_repository is None:
            logger.warning(f"No data_repository available for prefetch")
            return
        
        # Use session_data's query method for consistency
        trailing_days = settings.HISTORICAL_BARS_TRAILING_DAYS
        intervals = settings.HISTORICAL_BARS_INTERVALS
        
        # Calculate date range (before session_date)
        end_date = session_date - timedelta(days=1)  # Day before session
        start_date = end_date - timedelta(days=trailing_days)
        
        historical_bars = {}
        
        for interval in intervals:
            try:
                # Query database
                bars_db = await self._session_data._query_historical_bars(
                    self._data_repository,
                    symbol,
                    start_date,
                    end_date,
                    interval
                )
                
                if not bars_db:
                    continue
                
                # Group by date
                from collections import defaultdict
                bars_by_date = defaultdict(list)
                for bar in bars_db:
                    bar_date = bar.timestamp.date()
                    # Convert to BarData if needed
                    if not isinstance(bar, BarData):
                        bar_data = BarData(
                            symbol=symbol,
                            timestamp=bar.timestamp,
                            open=float(bar.open),
                            high=float(bar.high),
                            low=float(bar.low),
                            close=float(bar.close),
                            volume=int(bar.volume) if bar.volume else 0
                        )
                        bars_by_date[bar_date].append(bar_data)
                    else:
                        bars_by_date[bar_date].append(bar)
                
                historical_bars[interval] = dict(bars_by_date)
                
                logger.debug(
                    f"Prefetched {len(bars_db)} {interval}m bars for {symbol}"
                )
            
            except Exception as e:
                logger.error(f"Error prefetching interval {interval} for {symbol}: {e}")
                continue
        
        # Store in cache
        if historical_bars:
            from app.managers.data_manager.time_provider import get_time_provider
            self._prefetch_cache[symbol] = SymbolPrefetchData(
                symbol=symbol,
                session_date=session_date,
                historical_bars=historical_bars,
                prefetch_time=get_time_provider().get_current_time()
            )
    
    async def activate_prefetch(self, target_session: Optional[date] = None) -> bool:
        """Activate prefetched data for current session.
        
        Swaps prefetch cache into session_data for instant access.
        
        Args:
            target_session: Session date to activate (default: current session)
            
        Returns:
            True if prefetch was activated successfully
        """
        if not self._prefetch_complete:
            logger.warning("No prefetch available to activate")
            return False
        
        # Validate session match
        if target_session is None:
            target_session = self._session_data.current_session_date
        
        if target_session != self._prefetch_session_date:
            logger.warning(
                f"Prefetch mismatch: target={target_session}, "
                f"prefetched={self._prefetch_session_date}"
            )
            return False
        
        logger.info(f"Activating prefetch for session {target_session}")
        
        # Swap cache into session_data
        activated_count = 0
        async with self._session_data._lock:
            for symbol, prefetch_data in self._prefetch_cache.items():
                try:
                    # Get or create symbol data
                    if symbol not in self._session_data._active_symbols:
                        await self._session_data.register_symbol(symbol)
                    
                    symbol_data = self._session_data._symbols[symbol]
                    
                    # Copy historical bars
                    symbol_data.historical_bars = prefetch_data.historical_bars.copy()
                    
                    activated_count += 1
                    logger.debug(
                        f"Activated prefetch for {symbol}: "
                        f"{prefetch_data.bar_count} bars"
                    )
                
                except Exception as e:
                    logger.error(f"Error activating prefetch for {symbol}: {e}")
        
        logger.info(
            f"Activated prefetch for {activated_count} symbols "
            f"(instant session startup!)"
        )
        
        # Clear cache
        self._prefetch_cache.clear()
        self._prefetch_complete = False
        self._prefetch_session_date = None
        
        return True
    
    def get_status(self) -> Dict[str, any]:
        """Get current prefetch status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "running": self._running,
            "prefetch_in_progress": self._prefetch_in_progress,
            "prefetch_complete": self._prefetch_complete,
            "prefetch_session_date": self._prefetch_session_date,
            "cached_symbols": list(self._prefetch_cache.keys()),
            "cached_bar_count": sum(
                data.bar_count for data in self._prefetch_cache.values()
            ),
            "check_interval_seconds": self._check_interval,
            "auto_activate": self._auto_activate
        }
    
    def clear_cache(self) -> None:
        """Clear prefetch cache (for testing or manual control)."""
        self._prefetch_cache.clear()
        self._prefetch_complete = False
        self._prefetch_session_date = None
        logger.info("Prefetch cache cleared")


# Singleton instance management
_prefetch_manager_instance: Optional[PrefetchManager] = None


def get_prefetch_manager(
    session_data,
    data_repository,
    session_detector: Optional[SessionDetector] = None
) -> PrefetchManager:
    """Get or create the global PrefetchManager instance.
    
    Args:
        session_data: SessionData singleton
        data_repository: Database access
        session_detector: Optional SessionDetector instance
        
    Returns:
        PrefetchManager instance
    """
    global _prefetch_manager_instance
    if _prefetch_manager_instance is None:
        _prefetch_manager_instance = PrefetchManager(
            session_data,
            data_repository,
            session_detector
        )
    return _prefetch_manager_instance


def reset_prefetch_manager() -> None:
    """Reset the global prefetch manager instance (for testing)."""
    global _prefetch_manager_instance
    if _prefetch_manager_instance and _prefetch_manager_instance._running:
        _prefetch_manager_instance.stop()
    _prefetch_manager_instance = None
