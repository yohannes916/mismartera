"""Scanner Manager

Manages the scanner framework lifecycle and execution.

Responsibilities:
- Load scanners from session config
- Execute setup/scan/teardown lifecycle
- Handle blocking (backtest) vs async (live) execution
- Track scanner state machine
- Schedule regular session scans
- Ensure teardown after last scan

State Machine (per scanner):
  INITIALIZED → SETUP_PENDING → SETUP_COMPLETE → 
  SCAN_PENDING → SCANNING → SCAN_COMPLETE → 
  TEARDOWN_PENDING → TEARDOWN_COMPLETE

Execution Model:
- Backtest: Blocking calls, clock stopped
- Live: Async calls, clock running
- Sequential: One operation per scanner at a time
"""

import asyncio
import importlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict

from app.logger import logger
from app.managers.data_manager.session_data import get_session_data
from scanners.base import BaseScanner, ScanContext, ScanResult


class ScannerState(Enum):
    """Scanner state machine states."""
    INITIALIZED = "initialized"
    SETUP_PENDING = "setup_pending"
    SETUP_COMPLETE = "setup_complete"
    SCAN_PENDING = "scan_pending"
    SCANNING = "scanning"
    SCAN_COMPLETE = "scan_complete"
    TEARDOWN_PENDING = "teardown_pending"
    TEARDOWN_COMPLETE = "teardown_complete"
    ERROR = "error"


@dataclass
class ScannerInstance:
    """Tracks a scanner instance and its state.
    
    Attributes:
        module: Module path (e.g., "scanners.gap_scanner")
        scanner: Loaded scanner instance
        config: Scanner configuration from session config
        state: Current state in lifecycle
        pre_session: Whether to run pre-session scan
        regular_schedules: List of regular session schedules
        next_scan_time: Next scheduled scan time
        last_scan_time: Last completed scan time
        scan_count: Number of scans completed
        error: Error message if state is ERROR
        qualifying_symbols: Set of symbols found by this scanner
    """
    module: str
    scanner: BaseScanner
    config: Dict[str, Any]
    state: ScannerState = ScannerState.INITIALIZED
    pre_session: bool = False
    regular_schedules: List[Dict[str, Any]] = field(default_factory=list)
    next_scan_time: Optional[datetime] = None
    last_scan_time: Optional[datetime] = None
    scan_count: int = 0
    error: Optional[str] = None
    qualifying_symbols: Set[str] = field(default_factory=set)


class ScannerManager:
    """Manages scanner lifecycle and execution.
    
    Coordinates scanner setup, scanning, and teardown based on
    session configuration and time schedules.
    """
    
    def __init__(self, system_manager):
        """Initialize scanner manager.
        
        Args:
            system_manager: SystemManager instance
        """
        self._system_manager = system_manager
        self._session_data = None
        self._time_manager = None
        
        # Scanner tracking
        self._scanners: Dict[str, ScannerInstance] = {}
        self._lock = threading.RLock()
        
        # State flags
        self._initialized = False
        self._session_started = False
        self._session_ended = False
        
        logger.info("[SCANNER_MANAGER] Initialized")
    
    def initialize(self) -> bool:
        """Initialize scanner manager and load scanners.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get references
            self._session_data = get_session_data()  # SessionData is a singleton
            self._time_manager = self._system_manager.get_time_manager()
            
            # Load scanners from config
            session_config = self._system_manager.session_config
            scanner_configs = session_config.session_data_config.scanners
            
            if not scanner_configs:
                logger.info("[SCANNER_MANAGER] No scanners configured")
                self._initialized = True
                return True
            
            logger.info(f"[SCANNER_MANAGER] Loading {len(scanner_configs)} scanners")
            
            for scanner_config in scanner_configs:
                if not scanner_config.enabled:
                    logger.info(f"[SCANNER_MANAGER] Skipping disabled scanner: {scanner_config.module}")
                    continue
                
                # Load scanner
                success = self._load_scanner(scanner_config)
                if not success:
                    logger.error(f"[SCANNER_MANAGER] Failed to load scanner: {scanner_config.module}")
                    return False
            
            self._initialized = True
            logger.info(f"[SCANNER_MANAGER] Loaded {len(self._scanners)} scanners")
            return True
            
        except Exception as e:
            logger.error(f"[SCANNER_MANAGER] Initialization failed: {e}", exc_info=True)
            return False
    
    def _load_scanner(self, scanner_config) -> bool:
        """Load a scanner from module path.
        
        Args:
            scanner_config: ScannerConfig from session config
        
        Returns:
            True if successful, False otherwise
        """
        try:
            module_path = scanner_config.module
            
            # Import module
            logger.info(f"[SCANNER_MANAGER] Loading scanner: {module_path}")
            
            # Split module path to get class name
            # e.g., "scanners.gap_scanner" or "scanners.examples.gap_scanner_complete"
            parts = module_path.split('.')
            module_name = '.'.join(parts)
            
            # Import module
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                logger.error(f"[SCANNER_MANAGER] Failed to import module {module_name}: {e}")
                return False
            
            # Find scanner class (look for BaseScanner subclasses)
            scanner_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseScanner) and 
                    attr is not BaseScanner):
                    scanner_class = attr
                    break
            
            if scanner_class is None:
                logger.error(f"[SCANNER_MANAGER] No BaseScanner subclass found in {module_name}")
                return False
            
            # Instantiate scanner
            scanner = scanner_class(config=scanner_config.config)
            logger.info(f"[SCANNER_MANAGER] Instantiated {scanner_class.__name__}")
            
            # Create scanner instance tracker
            instance = ScannerInstance(
                module=module_path,
                scanner=scanner,
                config=scanner_config.config,
                pre_session=scanner_config.pre_session,
                regular_schedules=scanner_config.regular_session or []
            )
            
            self._scanners[module_path] = instance
            logger.info(f"[SCANNER_MANAGER] Loaded scanner: {module_path}")
            return True
            
        except Exception as e:
            logger.error(f"[SCANNER_MANAGER] Failed to load scanner {scanner_config.module}: {e}", exc_info=True)
            return False
    
    def setup_pre_session_scanners(self) -> bool:
        """Setup and run pre-session scanners.
        
        Called before session starts. Executes:
        1. setup() for all scanners
        2. scan() for pre-session scanners
        3. teardown() for pre-session-only scanners
        
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            logger.error("[SCANNER_MANAGER] Not initialized")
            return False
        
        logger.info("[SCANNER_MANAGER] === PRE-SESSION SCANNER SETUP ===")
        
        try:
            # Setup all scanners
            for module_path, instance in self._scanners.items():
                success = self._execute_setup(instance)
                if not success:
                    logger.error(f"[SCANNER_MANAGER] Setup failed for {module_path}")
                    instance.state = ScannerState.ERROR
                    return False
            
            # Run pre-session scans
            for module_path, instance in self._scanners.items():
                if instance.pre_session:
                    logger.info(f"[SCANNER_MANAGER] Running pre-session scan: {module_path}")
                    success = self._execute_scan(instance, "pre-session")
                    if not success:
                        logger.error(f"[SCANNER_MANAGER] Pre-session scan failed for {module_path}")
                        instance.state = ScannerState.ERROR
                        return False
            
            # Teardown pre-session-only scanners
            for module_path, instance in self._scanners.items():
                if instance.pre_session and not instance.regular_schedules:
                    logger.info(f"[SCANNER_MANAGER] Tearing down pre-session-only scanner: {module_path}")
                    self._execute_teardown(instance)
            
            logger.info("[SCANNER_MANAGER] Pre-session scanner setup complete")
            return True
            
        except Exception as e:
            logger.error(f"[SCANNER_MANAGER] Pre-session setup failed: {e}", exc_info=True)
            return False
    
    def _execute_setup(self, instance: ScannerInstance) -> bool:
        """Execute scanner setup.
        
        Args:
            instance: Scanner instance
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"[SCANNER_MANAGER] Setting up scanner: {instance.module}")
            
            instance.state = ScannerState.SETUP_PENDING
            
            # Create context
            context = self._create_context(instance)
            
            # Execute setup (blocking in both modes)
            start_time = time.time()
            success = instance.scanner.setup(context)
            elapsed_ms = (time.time() - start_time) * 1000
            
            if success:
                instance.state = ScannerState.SETUP_COMPLETE
                logger.info(
                    f"[SCANNER_MANAGER] Setup complete for {instance.module} "
                    f"({elapsed_ms:.2f}ms)"
                )
                return True
            else:
                instance.state = ScannerState.ERROR
                instance.error = "Setup returned False"
                logger.error(f"[SCANNER_MANAGER] Setup failed for {instance.module}")
                return False
                
        except Exception as e:
            instance.state = ScannerState.ERROR
            instance.error = str(e)
            logger.error(f"[SCANNER_MANAGER] Setup exception for {instance.module}: {e}", exc_info=True)
            return False
    
    def _execute_scan(self, instance: ScannerInstance, scan_type: str = "regular") -> bool:
        """Execute scanner scan.
        
        Args:
            instance: Scanner instance
            scan_type: "pre-session" or "regular"
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"[SCANNER_MANAGER] Scanning ({scan_type}): {instance.module}")
            
            # Check if already scanning
            if instance.state == ScannerState.SCANNING:
                logger.warning(f"[SCANNER_MANAGER] Scanner already running, skipping: {instance.module}")
                return True
            
            instance.state = ScannerState.SCANNING
            
            # Create context
            context = self._create_context(instance)
            
            # Execute scan (blocking in backtest, could be async in live)
            start_time = time.time()
            result = instance.scanner.scan(context)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Update result with timing
            result.execution_time_ms = elapsed_ms
            
            # Update instance tracking
            instance.scan_count += 1
            instance.last_scan_time = context.current_time
            instance.qualifying_symbols.update(result.symbols)
            instance.state = ScannerState.SCAN_COMPLETE
            
            logger.info(
                f"[SCANNER_MANAGER] Scan complete for {instance.module}: "
                f"{len(result.symbols)} symbols, {elapsed_ms:.2f}ms"
            )
            
            if result.symbols:
                logger.info(f"[SCANNER_MANAGER] Qualifying symbols: {result.symbols}")
            
            return True
            
        except Exception as e:
            instance.state = ScannerState.ERROR
            instance.error = str(e)
            logger.error(f"[SCANNER_MANAGER] Scan exception for {instance.module}: {e}", exc_info=True)
            return False
    
    def _execute_teardown(self, instance: ScannerInstance) -> bool:
        """Execute scanner teardown.
        
        Args:
            instance: Scanner instance
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"[SCANNER_MANAGER] Tearing down scanner: {instance.module}")
            
            instance.state = ScannerState.TEARDOWN_PENDING
            
            # Create context
            context = self._create_context(instance)
            
            # Execute teardown (blocking in both modes)
            start_time = time.time()
            instance.scanner.teardown(context)
            elapsed_ms = (time.time() - start_time) * 1000
            
            instance.state = ScannerState.TEARDOWN_COMPLETE
            logger.info(
                f"[SCANNER_MANAGER] Teardown complete for {instance.module} "
                f"({elapsed_ms:.2f}ms)"
            )
            return True
            
        except Exception as e:
            instance.state = ScannerState.ERROR
            instance.error = str(e)
            logger.error(f"[SCANNER_MANAGER] Teardown exception for {instance.module}: {e}", exc_info=True)
            return False
    
    def _create_context(self, instance: ScannerInstance) -> ScanContext:
        """Create scan context for scanner.
        
        Args:
            instance: Scanner instance
        
        Returns:
            ScanContext
        """
        current_time = self._time_manager.get_current_time()
        
        return ScanContext(
            session_data=self._session_data,
            time_manager=self._time_manager,
            mode=self.mode,
            current_time=current_time,
            config=instance.config
        )
    
    def on_session_start(self) -> None:
        """Notify scanner manager that session has started.
        
        Called by SessionCoordinator when session becomes active.
        """
        logger.info("[SCANNER_MANAGER] Session started")
        self._session_started = True
        
        # Initialize schedules for regular session scanners
        for instance in self._scanners.values():
            if instance.regular_schedules:
                self._update_next_scan_time(instance)
    
    def on_session_end(self) -> None:
        """Notify scanner manager that session has ended.
        
        Called by SessionCoordinator when session ends.
        Tears down all remaining scanners.
        """
        logger.info("[SCANNER_MANAGER] Session ended, tearing down scanners")
        self._session_ended = True
        
        # Teardown all scanners that haven't been torn down
        for instance in self._scanners.values():
            if instance.state not in [ScannerState.TEARDOWN_COMPLETE, ScannerState.ERROR]:
                self._execute_teardown(instance)
    
    def check_and_execute_scans(self) -> None:
        """Check if any scanners need to run and execute them.
        
        Called periodically by SessionCoordinator during regular session.
        """
        if not self._session_started or self._session_ended:
            return
        
        current_time = self._time_manager.get_current_time()
        
        for instance in self._scanners.values():
            if not instance.regular_schedules:
                continue
            
            # Check if it's time to scan
            if instance.next_scan_time and current_time >= instance.next_scan_time:
                logger.info(
                    f"[SCANNER_MANAGER] Scheduled scan triggered: {instance.module} "
                    f"at {current_time}"
                )
                
                # Execute scan
                self._execute_scan(instance, "regular")
                
                # Update next scan time
                self._update_next_scan_time(instance)
    
    def _update_next_scan_time(self, instance: ScannerInstance) -> None:
        """Update next scan time for scanner based on schedules.
        
        Args:
            instance: Scanner instance
        """
        if not instance.regular_schedules:
            instance.next_scan_time = None
            return
        
        current_time = self._time_manager.get_current_time()
        current_time_of_day = current_time.time()
        
        # Find next scan time from all schedules
        next_time = None
        
        for schedule in instance.regular_schedules:
            # Parse schedule times
            start_time = self._parse_time(schedule["start"])
            end_time = self._parse_time(schedule["end"])
            interval_str = schedule["interval"]
            
            # Check if we're before this schedule window
            if current_time_of_day < start_time:
                # Next scan is at the start of this window
                from datetime import datetime as dt
                candidate_time = dt.combine(current_time.date(), start_time)
                # Make sure it's timezone-aware if current_time is
                if current_time.tzinfo:
                    candidate_time = candidate_time.replace(tzinfo=current_time.tzinfo)
                
                if next_time is None or candidate_time < next_time:
                    next_time = candidate_time
            
            # Check if we're in this schedule window
            elif start_time <= current_time_of_day <= end_time:
                # Parse interval (e.g., "5m" -> IntervalInfo)
                from app.threads.quality.requirement_analyzer import parse_interval, IntervalType
                interval_info = parse_interval(interval_str)
                
                # Calculate next scan time based on interval
                if interval_info.type == IntervalType.MINUTE:
                    from datetime import timedelta
                    # Convert seconds to timedelta
                    interval_delta = timedelta(seconds=interval_info.seconds)
                    
                    # Next scan is current time + interval
                    candidate_time = current_time + interval_delta
                    
                    # Check if still within schedule window
                    if candidate_time.time() <= end_time:
                        if next_time is None or candidate_time < next_time:
                            next_time = candidate_time
        
        instance.next_scan_time = next_time
        
        if next_time:
            logger.debug(f"[SCANNER_MANAGER] Next scan for {instance.module}: {next_time}")
        else:
            logger.debug(f"[SCANNER_MANAGER] No more scans scheduled for {instance.module}")
    
    def _parse_time(self, time_str: str) -> dt_time:
        """Parse time string in HH:MM format.
        
        Args:
            time_str: Time string (e.g., "09:35")
        
        Returns:
            time object
        """
        parts = time_str.split(':')
        hour = int(parts[0])
        minute = int(parts[1])
        return dt_time(hour, minute)
    
    @property
    def mode(self) -> str:
        """Get operation mode from SystemManager (single source of truth).
        
        Returns:
            'live' or 'backtest'
        """
        return self._system_manager.mode.value
    
    def has_pre_session_scanners(self) -> bool:
        """Check if any scanners are configured for pre-session.
        
        Returns:
            True if any scanner has pre_session=True
        """
        return any(instance.pre_session for instance in self._scanners.values())
    
    def get_scanner_states(self) -> Dict[str, Dict[str, Any]]:
        """Get current state of all scanners.
        
        Returns:
            Dictionary of scanner states
        """
        states = {}
        
        with self._lock:
            for module_path, instance in self._scanners.items():
                states[module_path] = {
                    "state": instance.state.value,
                    "scan_count": instance.scan_count,
                    "last_scan_time": instance.last_scan_time.isoformat() if instance.last_scan_time else None,
                    "next_scan_time": instance.next_scan_time.isoformat() if instance.next_scan_time else None,
                    "qualifying_symbols": list(instance.qualifying_symbols),
                    "error": instance.error
                }
        
        return states
    
    def shutdown(self) -> None:
        """Shutdown scanner manager.
        
        Called during system shutdown.
        """
        logger.info("[SCANNER_MANAGER] Shutting down")
        
        # Teardown any remaining scanners
        for instance in self._scanners.values():
            if instance.state not in [ScannerState.TEARDOWN_COMPLETE, ScannerState.ERROR]:
                try:
                    self._execute_teardown(instance)
                except Exception as e:
                    logger.error(f"[SCANNER_MANAGER] Teardown failed for {instance.module}: {e}")
        
        self._scanners.clear()
        logger.info("[SCANNER_MANAGER] Shutdown complete")
    
    # =========================================================================
    # Session Lifecycle (Phase 1 & 2 of Revised Flow)
    # =========================================================================
    
    def teardown(self):
        """Reset to initial state and deallocate resources (Phase 1).
        
        Called at START of new session (before data loaded).
        Clears scanners, resets state, prepares for fresh session.
        
        Must be idempotent (safe to call multiple times).
        """
        logger.debug("ScannerManager.teardown() - resetting state")
        
        # Teardown all scanners from previous session
        for instance in list(self._scanners.values()):
            if instance.state not in [ScannerState.TEARDOWN_COMPLETE, ScannerState.ERROR]:
                try:
                    self._execute_teardown(instance)
                except Exception as e:
                    logger.error(f"[SCANNER_MANAGER] Teardown failed for {instance.module}: {e}")
        
        # Clear all scanners (will be reloaded in setup)
        self._scanners.clear()
        
        # Reset state flags
        self._initialized = False
        self._session_started = False
        self._session_ended = False
        
        logger.debug("ScannerManager teardown complete")
    
    def setup(self):
        """Initialize for new session (Phase 2).
        
        Called after data loaded, before session activated.
        Can access SessionData (symbols, bars, indicators).
        
        Loads scanners from config, prepares for execution.
        """
        logger.debug("ScannerManager.setup() - initializing for new session")
        
        # Scanners will be loaded by setup_pre_session_scanners()
        # or when session starts (for regular scanners)
        # This is just a placeholder for consistency
        
        logger.debug("ScannerManager setup complete")
