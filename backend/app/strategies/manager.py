"""Strategy manager - orchestrates all strategies.

Similar to ScannerManager but for continuous event-driven strategies.
"""
import importlib
import logging
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path

from app.strategies.base import BaseStrategy, StrategyContext
from app.strategies.thread import StrategyThread
from app.models.strategy_config import StrategyConfig
from app.managers.data_manager.session_data import get_session_data

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages all strategy threads.
    
    Responsibilities:
    - Load strategies from config
    - Create strategy threads
    - Manage subscriptions
    - Track performance
    - Coordinate lifecycle
    
    Similar to ScannerManager but for continuous event-driven strategies.
    """
    
    def __init__(self, system_manager):
        """Initialize strategy manager.
        
        Args:
            system_manager: SystemManager instance
        """
        self._system_manager = system_manager
        
        # Strategy threads
        self._strategy_threads: List[StrategyThread] = []
        
        # Subscription tracking: (symbol, interval) -> [StrategyThread, ...]
        self._subscriptions: Dict[Tuple[str, str], List[StrategyThread]] = {}
        
        # State
        self._initialized = False
        self._running = False
        
        logger.info("StrategyManager created")
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def initialize(self) -> bool:
        """Initialize strategy manager.
        
        Loads strategies from session_config and creates threads.
        
        Returns:
            True if initialization successful
        """
        if self._initialized:
            logger.warning("StrategyManager already initialized")
            return True
        
        logger.info("Initializing StrategyManager...")
        
        try:
            # Get strategies from config
            session_config = self._system_manager.session_config
            strategies_config = session_config.session_data_config.strategies
            
            if not strategies_config:
                logger.info("No strategies configured")
                self._initialized = True
                return True
            
            # Load each strategy
            for strategy_config in strategies_config:
                if not strategy_config.enabled:
                    logger.info(f"Strategy '{strategy_config.module}' disabled - skipping")
                    continue
                
                # Load strategy
                success = self._load_strategy(strategy_config)
                if not success:
                    logger.error(f"Failed to load strategy: {strategy_config.module}")
                    return False
            
            # Build subscription map
            self._build_subscription_map()
            
            logger.info(
                f"StrategyManager initialized with {len(self._strategy_threads)} strategies"
            )
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize StrategyManager: {e}", exc_info=True)
            return False
    
    def start_strategies(self) -> bool:
        """Start all strategy threads.
        
        Returns:
            True if all strategies started successfully
        """
        if not self._initialized:
            logger.error("Cannot start - not initialized")
            return False
        
        if self._running:
            logger.warning("Strategies already running")
            return True
        
        logger.info("Starting all strategies...")
        
        try:
            for thread in self._strategy_threads:
                # Call strategy setup
                success = thread.strategy.setup(thread.context)
                if not success:
                    logger.error(f"Strategy {thread.strategy.name} setup failed")
                    return False
                
                # Start thread
                thread.start()
                logger.info(f"Started strategy: {thread.strategy.name}")
            
            self._running = True
            logger.info(f"All {len(self._strategy_threads)} strategies running")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start strategies: {e}", exc_info=True)
            return False
    
    def stop_strategies(self):
        """Stop all strategy threads."""
        if not self._running:
            logger.info("Strategies not running")
            return
        
        logger.info("Stopping all strategies...")
        
        # Signal all threads to stop
        for thread in self._strategy_threads:
            thread.stop()
        
        # Wait for all to finish
        for thread in self._strategy_threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning(f"Strategy {thread.strategy.name} did not stop cleanly")
        
        # Call teardown
        for thread in self._strategy_threads:
            try:
                thread.strategy.teardown(thread.context)
            except Exception as e:
                logger.error(
                    f"Error in {thread.strategy.name} teardown: {e}",
                    exc_info=True
                )
        
        self._running = False
        logger.info("All strategies stopped")
    
    def shutdown(self):
        """Shutdown strategy manager."""
        logger.info("Shutting down StrategyManager...")
        
        if self._running:
            self.stop_strategies()
        
        # Clear data structures
        self._strategy_threads.clear()
        self._subscriptions.clear()
        self._initialized = False
        
        logger.info("StrategyManager shutdown complete")
    
    # =========================================================================
    # Strategy Loading
    # =========================================================================
    
    def _load_strategy(self, config: StrategyConfig) -> bool:
        """Load a single strategy.
        
        Args:
            config: Strategy configuration
            
        Returns:
            True if loaded successfully
        """
        try:
            # Import module
            module = importlib.import_module(config.module)
            
            # Find strategy class
            strategy_class = self._find_strategy_class(module, config.module)
            if not strategy_class:
                logger.error(f"No strategy class found in {config.module}")
                return False
            
            # Extract name from module
            name = config.module.split('.')[-1]
            
            # Create strategy instance
            strategy = strategy_class(name=name, config=config.config)
            
            # Create context
            context = self._create_context()
            
            # Determine mode
            mode = self._determine_mode()
            
            # Create thread
            thread = StrategyThread(
                strategy=strategy,
                context=context,
                mode=mode
            )
            
            self._strategy_threads.append(thread)
            logger.info(f"Loaded strategy: {name} ({strategy_class.__name__})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load strategy {config.module}: {e}", exc_info=True)
            return False
    
    def _find_strategy_class(self, module, module_path: str):
        """Find strategy class in module.
        
        Looks for class that:
        1. Inherits from BaseStrategy
        2. Name matches module name (e.g., simple_ma_cross -> SimpleMaCrossStrategy)
        
        Args:
            module: Python module
            module_path: Module path string
            
        Returns:
            Strategy class or None
        """
        from app.strategies.base import BaseStrategy as NewBaseStrategy
        
        # Convert module name to class name
        # simple_ma_cross -> SimpleMaCrossStrategy
        module_name = module_path.split('.')[-1]
        expected_class_name = ''.join(
            word.capitalize() for word in module_name.split('_')
        ) + 'Strategy'
        
        # Look for class
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type) and
                issubclass(attr, NewBaseStrategy) and
                attr is not NewBaseStrategy
            ):
                # Check if name matches
                if attr.__name__ == expected_class_name:
                    return attr
                
                # Fallback: any BaseStrategy subclass
                logger.warning(
                    f"Found {attr.__name__} but expected {expected_class_name}"
                )
                return attr
        
        return None
    
    def _create_context(self) -> StrategyContext:
        """Create strategy context.
        
        Returns:
            StrategyContext instance
        """
        return StrategyContext(
            session_data=get_session_data(),  # SessionData is a singleton
            time_manager=self._system_manager.get_time_manager(),
            system_manager=self._system_manager,
            mode=self._system_manager.mode.value
        )
    
    def _determine_mode(self) -> str:
        """Determine execution mode for StreamSubscription.
        
        Returns:
            "data-driven", "clock-driven", or "live"
        """
        if self._system_manager.mode.value == "live":
            return "live"
        
        # Backtest mode
        speed = self._system_manager.session_config.backtest_config.speed_multiplier
        return "data-driven" if speed == 0 else "clock-driven"
    
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    def _build_subscription_map(self):
        """Build map of subscriptions.
        
        Creates mapping: (symbol, interval) -> [StrategyThread, ...]
        """
        self._subscriptions.clear()
        
        for thread in self._strategy_threads:
            subscriptions = thread.strategy.get_subscriptions()
            
            for symbol, interval in subscriptions:
                key = (symbol, interval)
                if key not in self._subscriptions:
                    self._subscriptions[key] = []
                self._subscriptions[key].append(thread)
        
        logger.info(
            f"Built subscription map: {len(self._subscriptions)} unique subscriptions"
        )
    
    def get_subscribed_threads(
        self,
        symbol: str,
        interval: str
    ) -> List[StrategyThread]:
        """Get threads subscribed to (symbol, interval).
        
        Args:
            symbol: Symbol
            interval: Interval
            
        Returns:
            List of subscribed StrategyThread instances
        """
        return self._subscriptions.get((symbol, interval), [])
    
    def get_all_subscriptions(self) -> Set[Tuple[str, str]]:
        """Get all (symbol, interval) subscriptions.
        
        Returns:
            Set of (symbol, interval) tuples
        """
        return set(self._subscriptions.keys())
    
    # =========================================================================
    # Notification Routing
    # =========================================================================
    
    def notify_strategies(self, symbol: str, interval: str, data_type: str = "bars"):
        """Notify subscribed strategies of new data.
        
        Called by DataProcessor when new data arrives.
        Routes notification only to subscribed strategies.
        
        Args:
            symbol: Symbol with new data
            interval: Interval with new data
            data_type: Type of data
        """
        threads = self.get_subscribed_threads(symbol, interval)
        
        for thread in threads:
            thread.notify(symbol, interval, data_type)
    
    def wait_for_strategies(self, timeout: Optional[float] = None) -> bool:
        """Wait for all strategies to signal ready.
        
        Called by DataProcessor after notifying strategies.
        Blocks in data-driven mode, times out in clock-driven/live.
        
        Args:
            timeout: Timeout in seconds (None = infinite for data-driven)
            
        Returns:
            True if all ready, False if timeout
        """
        mode = self._determine_mode()
        
        # Determine timeout
        if mode == "data-driven":
            actual_timeout = None  # Block indefinitely
        else:
            actual_timeout = timeout if timeout is not None else 0.1
        
        all_ready = True
        
        for thread in self._strategy_threads:
            subscription = thread.get_subscription()
            ready = subscription.wait_until_ready(timeout=actual_timeout)
            
            if not ready:
                all_ready = False
                overruns = (
                    subscription._overrun_count 
                    if hasattr(subscription, '_overrun_count')
                    else 0
                )
                logger.warning(
                    f"Strategy {thread.strategy.name} timeout (overruns={overruns})"
                )
            
            subscription.reset()
        
        return all_ready
    
    # =========================================================================
    # Performance Metrics
    # =========================================================================
    
    def get_metrics(self) -> dict:
        """Get aggregate metrics.
        
        Returns:
            Dictionary of system-wide metrics
        """
        strategy_metrics = [thread.get_metrics() for thread in self._strategy_threads]
        
        if not strategy_metrics:
            return {
                'total_strategies': 0,
                'active_strategies': 0,
                'total_subscriptions': 0,
                'total_notifications_processed': 0,
                'total_signals_generated': 0,
                'total_errors': 0,
                'slowest_strategy': None,
                'slowest_avg_time_ms': 0,
                'strategies': [],
            }
        
        total_notifications = sum(m['notifications_processed'] for m in strategy_metrics)
        total_signals = sum(m['signals_generated'] for m in strategy_metrics)
        total_errors = sum(m['errors'] for m in strategy_metrics)
        
        # Find bottleneck
        slowest = max(
            strategy_metrics,
            key=lambda m: m['avg_processing_time_ms']
        )
        
        return {
            'total_strategies': len(self._strategy_threads),
            'active_strategies': sum(1 for m in strategy_metrics if m['running']),
            'total_subscriptions': len(self._subscriptions),
            'total_notifications_processed': total_notifications,
            'total_signals_generated': total_signals,
            'total_errors': total_errors,
            'slowest_strategy': slowest['strategy_name'],
            'slowest_avg_time_ms': slowest['avg_processing_time_ms'],
            'strategies': strategy_metrics,
        }
    
    # =========================================================================
    # Mid-Session Symbol Addition
    # =========================================================================
    
    def notify_symbol_added(self, symbol: str):
        """Notify strategies of new symbol.
        
        Called when scanner adds symbol mid-session.
        
        Args:
            symbol: Symbol that was added
        """
        logger.info(f"Notifying strategies of new symbol: {symbol}")
        
        for thread in self._strategy_threads:
            try:
                thread.strategy.on_symbol_added(symbol)
            except Exception as e:
                logger.error(
                    f"Error notifying {thread.strategy.name}: {e}",
                    exc_info=True
                )
        
        # Rebuild subscription map (strategies may have updated subscriptions)
        self._build_subscription_map()


# Export public API
__all__ = ['StrategyManager']
