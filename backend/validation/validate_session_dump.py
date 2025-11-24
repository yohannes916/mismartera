#!/usr/bin/env python3
"""Session Data Validation Script

Validates CSV dumps from 'data session' command against expected behavioral requirements.
Checks invariants, temporal consistency, queue behavior, and data flow correctness.

Usage:
    python validate_session_dump.py <csv_file> [--config <config_file>] [--db-check]
    
    Defaults:
        csv_file: validation/test_session.csv
        config_file: session_configs/validation_session.json
"""

import csv
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ValidationResult:
    """Result of a validation check."""
    check_name: str
    passed: bool
    row_number: int
    details: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO


@dataclass
class ValidationStats:
    """Statistics from validation run."""
    total_rows: int = 0
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warnings: int = 0
    violations: List[ValidationResult] = field(default_factory=list)
    
    def add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            if result.severity == "WARNING":
                self.warnings += 1
            else:
                self.failed_checks += 1
            self.violations.append(result)


class SessionValidator:
    """Validates session data CSV dumps."""
    
    def __init__(self, csv_file: Path, config_file: Optional[Path] = None, db_check: bool = False):
        self.csv_file = csv_file
        self.config_file = config_file
        self.db_check = db_check
        self.stats = ValidationStats()
        self.rows: List[Dict[str, Any]] = []
        self.symbols: List[str] = []
        self.config = None
        self.expected_streams: Dict[str, Set[str]] = {}  # symbol -> set of expected intervals/types
        
    def load_config(self):
        """Load and parse session configuration file."""
        if not self.config_file or not self.config_file.exists():
            print("⚠️  No config file provided, skipping config-based validation")
            return
        
        print(f"Loading config: {self.config_file}")
        with open(self.config_file, 'r') as f:
            self.config = json.load(f)
        
        # Parse expected streams from config
        if 'data_streams' in self.config:
            for stream_config in self.config['data_streams']:
                symbol = stream_config.get('symbol', '').upper()
                stream_type = stream_config.get('type', '')
                interval = stream_config.get('interval', '')
                
                if symbol not in self.expected_streams:
                    self.expected_streams[symbol] = set()
                
                if stream_type == 'bars':
                    # For bars, track the interval (should only be 1m)
                    self.expected_streams[symbol].add(f"bars_{interval}")
                elif stream_type in ['ticks', 'quotes']:
                    self.expected_streams[symbol].add(stream_type)
        
        print(f"Expected streams from config: {dict(self.expected_streams)}")
        
        # Parse expected derived intervals
        self.expected_derived_intervals = []
        if 'session_data_config' in self.config:
            upkeep_config = self.config['session_data_config'].get('data_upkeep', {})
            self.expected_derived_intervals = upkeep_config.get('derived_intervals', [5, 15])
        
        print(f"Expected derived intervals: {self.expected_derived_intervals}")
    
    def load_csv(self):
        """Load CSV file into memory."""
        print(f"Loading CSV: {self.csv_file}")
        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            self.rows = list(reader)
        
        self.stats.total_rows = len(self.rows)
        print(f"Loaded {self.stats.total_rows} rows")
        
        # Extract symbols from column names
        if self.rows:
            for col in self.rows[0].keys():
                if col.endswith("_volume"):
                    symbol = col.replace("_volume", "")
                    if symbol not in self.symbols:
                        self.symbols.append(symbol)
        
        self.symbols.sort()
        print(f"Symbols found in CSV: {', '.join(self.symbols)}")
    
    def validate_all(self):
        """Run all validation checks."""
        print("\n" + "="*80)
        print("STARTING VALIDATION")
        print("="*80 + "\n")
        
        # Config-based validation
        if self.config:
            print("📋 Validating against config expectations...")
            self.validate_config_expectations()
        
        # System state checks
        print("📊 Validating system state...")
        self.validate_system_state()
        
        # Temporal checks
        print("⏰ Validating temporal consistency...")
        self.validate_temporal_consistency()
        
        # Queue checks
        print("📦 Validating queue behavior...")
        self.validate_queue_behavior()
        
        # Bar data checks
        print("📈 Validating bar data...")
        self.validate_bar_data()
        
        # Price/Volume checks
        print("💰 Validating price and volume...")
        self.validate_price_volume()
        
        # Multi-symbol synchronization
        print("🔄 Validating multi-symbol synchronization...")
        self.validate_multi_symbol_sync()
        
        # Derived bars
        print("📊 Validating derived bars...")
        self.validate_derived_bars()
        
        # Data completeness (NEW)
        print("🔗 Validating data completeness...")
        self.validate_data_completeness()
        
        # Chronological ordering (NEW)
        print("📐 Validating chronological ordering...")
        self.validate_chronological_ordering()
        
        # Session lifecycle
        print("🔄 Validating session lifecycle...")
        self.validate_session_lifecycle()
        
        # Performance
        print("⚡ Validating performance metrics...")
        self.validate_performance()
        
        if self.db_check:
            print("🗄️  Validating against database...")
            self.validate_database()
    
    def validate_config_expectations(self):
        """Validate that expected streams from config appear in CSV."""
        # Check all expected symbols are present
        for expected_symbol in self.expected_streams.keys():
            if expected_symbol not in self.symbols:
                self.stats.add_result(ValidationResult(
                    check_name="config_symbols_present",
                    passed=False,
                    row_number=1,
                    details=f"Expected symbol {expected_symbol} from config not found in CSV",
                    severity="ERROR",
                ))
        
        # Check for unexpected symbols
        for csv_symbol in self.symbols:
            if csv_symbol not in self.expected_streams:
                self.stats.add_result(ValidationResult(
                    check_name="unexpected_symbols",
                    passed=False,
                    row_number=1,
                    details=f"Symbol {csv_symbol} found in CSV but not in config",
                    severity="WARNING",
                ))
        
        # Check expected data types appear in CSV (check last row for completeness)
        if self.rows:
            last_row = self.rows[-1]
            
            for symbol, expected_types in self.expected_streams.items():
                for expected_type in expected_types:
                    if expected_type.startswith('bars_'):
                        interval = expected_type.replace('bars_', '')
                        # Check for queue column
                        queue_key = f"{symbol}_queue_BAR_size"
                        if queue_key not in last_row:
                            self.stats.add_result(ValidationResult(
                                check_name="config_data_types_present",
                                passed=False,
                                row_number=len(self.rows),
                                details=f"Expected bars stream for {symbol} ({interval}) not found in CSV",
                                severity="ERROR",
                            ))
                    elif expected_type in ['ticks', 'quotes']:
                        # Check for tick/quote columns (when implemented)
                        queue_key = f"{symbol}_queue_{expected_type.upper()}_size"
                        if queue_key in last_row:
                            pass  # Found as expected
                        else:
                            self.stats.add_result(ValidationResult(
                                check_name="config_data_types_present",
                                passed=False,
                                row_number=len(self.rows),
                                details=f"Expected {expected_type} stream for {symbol} not found (may not be implemented yet)",
                                severity="WARNING",
                            ))
            
            # Check derived intervals appear
            for symbol in self.symbols:
                for interval in self.expected_derived_intervals:
                    bars_key = f"{symbol}_{interval}m_bars"
                    if bars_key not in last_row:
                        self.stats.add_result(ValidationResult(
                            check_name="derived_intervals_present",
                            passed=False,
                            row_number=len(self.rows),
                            details=f"Expected derived interval {interval}m for {symbol} not found in CSV",
                            severity="WARNING",
                        ))
                    elif int(last_row.get(bars_key, 0) or 0) == 0:
                        self.stats.add_result(ValidationResult(
                            check_name="derived_intervals_computed",
                            passed=False,
                            row_number=len(self.rows),
                            details=f"Derived interval {interval}m for {symbol} was never computed (0 bars at end)",
                            severity="WARNING",
                        ))
    
    def validate_system_state(self):
        """Validate system state invariants."""
        valid_states = {"running", "paused", "stopped"}
        valid_modes = {"backtest", "live"}
        
        for idx, row in enumerate(self.rows):
            row_num = idx + 1
            
            # Check valid states
            state = row.get("system_state", "")
            if state not in valid_states:
                self.stats.add_result(ValidationResult(
                    check_name="system_state_valid",
                    passed=False,
                    row_number=row_num,
                    details=f"Invalid system_state: {state}",
                ))
            
            mode = row.get("system_mode", "")
            if mode not in valid_modes:
                self.stats.add_result(ValidationResult(
                    check_name="system_mode_valid",
                    passed=False,
                    row_number=row_num,
                    details=f"Invalid system_mode: {mode}",
                ))
            
            # Check state never returns to running after stopped
            if idx > 0:
                prev_state = self.rows[idx - 1].get("system_state", "")
                if prev_state == "stopped" and state == "running":
                    self.stats.add_result(ValidationResult(
                        check_name="state_no_restart",
                        passed=False,
                        row_number=row_num,
                        details=f"System restarted after stopping (prev: {prev_state}, curr: {state})",
                    ))
    
    def validate_temporal_consistency(self):
        """Validate temporal consistency."""
        prev_time = None
        prev_timestamp = None
        
        for idx, row in enumerate(self.rows):
            row_num = idx + 1
            
            # Check session_date is constant
            session_date = row.get("session_date", "")
            if idx > 0:
                prev_date = self.rows[idx - 1].get("session_date", "")
                if session_date != prev_date:
                    self.stats.add_result(ValidationResult(
                        check_name="session_date_constant",
                        passed=False,
                        row_number=row_num,
                        details=f"Session date changed: {prev_date} -> {session_date}",
                    ))
            
            # Check session_time is monotonic
            session_time_str = row.get("session_time", "")
            if session_time_str and session_time_str != "N/A":
                try:
                    session_time = datetime.strptime(session_time_str, "%H:%M:%S")
                    
                    if prev_time and session_time < prev_time:
                        self.stats.add_result(ValidationResult(
                            check_name="session_time_monotonic",
                            passed=False,
                            row_number=row_num,
                            details=f"Session time went backwards: {prev_time.strftime('%H:%M:%S')} -> {session_time_str}",
                        ))
                    
                    prev_time = session_time
                except ValueError:
                    pass
            
            # Note: Real-time delta between CSV rows is NOT validated
            # because it depends on backtest speed (60x, 1x, etc.) which
            # should be transparent to validation. We only validate backtest
            # time (session_time) progression.
    
    def validate_queue_behavior(self):
        """Validate queue behavior."""
        for symbol in self.symbols:
            queue_size_key = f"{symbol}_queue_BAR_size"
            oldest_key = f"{symbol}_queue_BAR_oldest"
            newest_key = f"{symbol}_queue_BAR_newest"
            
            prev_size = None
            prev_oldest = None
            
            for idx, row in enumerate(self.rows):
                row_num = idx + 1
                
                # Get queue data
                size_str = row.get(queue_size_key, "")
                oldest_str = row.get(oldest_key, "")
                newest_str = row.get(newest_key, "")
                
                if not size_str:
                    continue
                
                try:
                    size = int(size_str)
                    
                    # Check non-negative
                    if size < 0:
                        self.stats.add_result(ValidationResult(
                            check_name="queue_size_non_negative",
                            passed=False,
                            row_number=row_num,
                            details=f"{symbol}: Queue size negative: {size}",
                        ))
                    
                    # Check monotonic decrease (or same)
                    if prev_size is not None and size > prev_size:
                        self.stats.add_result(ValidationResult(
                            check_name="queue_size_decreasing",
                            passed=False,
                            row_number=row_num,
                            details=f"{symbol}: Queue size increased: {prev_size} -> {size}",
                            severity="WARNING",
                        ))
                    
                    # Check oldest is monotonic
                    if oldest_str and oldest_str != "N/A":
                        try:
                            oldest = datetime.strptime(oldest_str, "%H:%M:%S")
                            
                            if prev_oldest and oldest < prev_oldest:
                                self.stats.add_result(ValidationResult(
                                    check_name="queue_oldest_monotonic",
                                    passed=False,
                                    row_number=row_num,
                                    details=f"{symbol}: Queue oldest went backwards: {prev_oldest.strftime('%H:%M:%S')} -> {oldest_str}",
                                ))
                            
                            prev_oldest = oldest
                        except ValueError:
                            pass
                    
                    # Check oldest <= newest
                    if oldest_str != "N/A" and newest_str != "N/A":
                        try:
                            oldest = datetime.strptime(oldest_str, "%H:%M:%S")
                            newest = datetime.strptime(newest_str, "%H:%M:%S")
                            
                            if oldest > newest:
                                self.stats.add_result(ValidationResult(
                                    check_name="queue_oldest_lte_newest",
                                    passed=False,
                                    row_number=row_num,
                                    details=f"{symbol}: Queue oldest > newest: {oldest_str} > {newest_str}",
                                ))
                        except ValueError:
                            pass
                    
                    # Check if size=0, timestamps should be N/A
                    if size == 0 and (oldest_str != "N/A" or newest_str != "N/A"):
                        self.stats.add_result(ValidationResult(
                            check_name="queue_empty_timestamps",
                            passed=False,
                            row_number=row_num,
                            details=f"{symbol}: Queue empty but timestamps not N/A: oldest={oldest_str}, newest={newest_str}",
                            severity="WARNING",
                        ))
                    
                    prev_size = size
                
                except ValueError:
                    pass
    
    def validate_bar_data(self):
        """Validate bar data invariants."""
        for symbol in self.symbols:
            bars_1m_key = f"{symbol}_1m_bars"
            bars_5m_key = f"{symbol}_5m_bars"
            quality_key = f"{symbol}_bar_quality"
            
            prev_1m = None
            prev_5m = None
            
            for idx, row in enumerate(self.rows):
                row_num = idx + 1
                
                # Check 1m bars monotonic
                bars_1m_str = row.get(bars_1m_key, "")
                if bars_1m_str:
                    try:
                        bars_1m = int(bars_1m_str)
                        
                        if bars_1m < 0:
                            self.stats.add_result(ValidationResult(
                                check_name="bars_1m_non_negative",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: 1m bars negative: {bars_1m}",
                            ))
                        
                        if prev_1m is not None and bars_1m < prev_1m:
                            self.stats.add_result(ValidationResult(
                                check_name="bars_1m_monotonic",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: 1m bars decreased: {prev_1m} -> {bars_1m}",
                            ))
                        
                        prev_1m = bars_1m
                    except ValueError:
                        pass
                
                # Check 5m bars monotonic
                bars_5m_str = row.get(bars_5m_key, "")
                if bars_5m_str:
                    try:
                        bars_5m = int(bars_5m_str)
                        
                        if bars_5m < 0:
                            self.stats.add_result(ValidationResult(
                                check_name="bars_5m_non_negative",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: 5m bars negative: {bars_5m}",
                            ))
                        
                        if prev_5m is not None and bars_5m < prev_5m:
                            self.stats.add_result(ValidationResult(
                                check_name="bars_5m_monotonic",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: 5m bars decreased: {prev_5m} -> {bars_5m}",
                            ))
                        
                        prev_5m = bars_5m
                    except ValueError:
                        pass
                
                # Check quality bounds
                quality_str = row.get(quality_key, "")
                if quality_str:
                    try:
                        quality = float(quality_str)
                        
                        if quality < 0.0 or quality > 100.0:
                            self.stats.add_result(ValidationResult(
                                check_name="bar_quality_bounds",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Bar quality out of bounds: {quality}",
                            ))
                    except ValueError:
                        pass
    
    def validate_price_volume(self):
        """Validate price and volume invariants."""
        for symbol in self.symbols:
            high_key = f"{symbol}_high"
            low_key = f"{symbol}_low"
            volume_key = f"{symbol}_volume"
            
            prev_high = None
            prev_low = None
            prev_volume = None
            
            for idx, row in enumerate(self.rows):
                row_num = idx + 1
                
                high_str = row.get(high_key, "")
                low_str = row.get(low_key, "")
                volume_str = row.get(volume_key, "")
                
                # Check high >= low
                if high_str and low_str:
                    try:
                        high = float(high_str)
                        low = float(low_str)
                        
                        if high < low:
                            self.stats.add_result(ValidationResult(
                                check_name="high_gte_low",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: High < Low: {high} < {low}",
                            ))
                        
                        # Check high is monotonic increasing
                        if prev_high is not None and high < prev_high:
                            self.stats.add_result(ValidationResult(
                                check_name="high_monotonic",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: High decreased: {prev_high} -> {high}",
                            ))
                        
                        # Check low is monotonic decreasing
                        if prev_low is not None and low > prev_low:
                            self.stats.add_result(ValidationResult(
                                check_name="low_monotonic",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Low increased: {prev_low} -> {low}",
                            ))
                        
                        prev_high = high
                        prev_low = low
                    except ValueError:
                        pass
                
                # Check volume monotonic
                if volume_str:
                    try:
                        volume = int(volume_str)
                        
                        if prev_volume is not None and volume < prev_volume:
                            self.stats.add_result(ValidationResult(
                                check_name="volume_monotonic",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Volume decreased: {prev_volume} -> {volume}",
                            ))
                        
                        prev_volume = volume
                    except ValueError:
                        pass
    
    def validate_multi_symbol_sync(self):
        """Validate multi-symbol synchronization."""
        for idx, row in enumerate(self.rows):
            row_num = idx + 1
            session_time = row.get("session_time", "")
            
            # All symbols should show same session_time
            # (This is inherently true since it's one row, but good to document)
            pass
    
    def validate_derived_bars(self):
        """Validate derived bar computation."""
        for symbol in self.symbols:
            bars_1m_key = f"{symbol}_1m_bars"
            bars_5m_key = f"{symbol}_5m_bars"
            
            for idx, row in enumerate(self.rows):
                row_num = idx + 1
                
                bars_1m_str = row.get(bars_1m_key, "")
                bars_5m_str = row.get(bars_5m_key, "")
                
                if bars_1m_str and bars_5m_str:
                    try:
                        bars_1m = int(bars_1m_str)
                        bars_5m = int(bars_5m_str)
                        
                        # Check ratio is reasonable
                        expected_max = (bars_1m // 5) + 1
                        if bars_5m > expected_max:
                            self.stats.add_result(ValidationResult(
                                check_name="derived_bars_ratio",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Too many 5m bars: {bars_5m} (max expected: {expected_max} from {bars_1m} 1m bars)",
                            ))
                        
                        # Check 5m bars appear when enough 1m bars
                        if bars_1m >= 5 and bars_5m == 0:
                            # Allow some lag (60s check interval)
                            if idx > 30:  # After 30 rows (~60s at 2s/row)
                                self.stats.add_result(ValidationResult(
                                    check_name="derived_bars_timely",
                                    passed=False,
                                    row_number=row_num,
                                    details=f"{symbol}: 5m bars not computed yet despite {bars_1m} 1m bars available",
                                    severity="WARNING",
                                ))
                    except ValueError:
                        pass
    
    def validate_session_lifecycle(self):
        """Validate session lifecycle."""
        if not self.rows:
            return
        
        # Check startup
        first_row = self.rows[0]
        if first_row.get("session_active") != "True":
            self.stats.add_result(ValidationResult(
                check_name="session_starts_active",
                passed=False,
                row_number=1,
                details="Session should start with session_active=True",
            ))
        
        # Check completion
        last_row = self.rows[-1]
        last_state = last_row.get("system_state", "")
        if last_state != "stopped":
            self.stats.add_result(ValidationResult(
                check_name="session_ends_stopped",
                passed=False,
                row_number=len(self.rows),
                details=f"Session should end with system_state=stopped (actual: {last_state})",
                severity="WARNING",
            ))
    
    def validate_performance(self):
        """Validate performance metrics (backtest time only, speed-agnostic)."""
        # Check for stalls (session_time not advancing)
        stall_count = 0
        prev_time = None
        
        for idx, row in enumerate(self.rows):
            row_num = idx + 1
            session_time_str = row.get("session_time", "")
            
            if session_time_str and session_time_str != "N/A":
                try:
                    session_time = datetime.strptime(session_time_str, "%H:%M:%S")
                    
                    if prev_time and session_time == prev_time:
                        stall_count += 1
                        if stall_count > 10:
                            self.stats.add_result(ValidationResult(
                                check_name="no_time_stalls",
                                passed=False,
                                row_number=row_num,
                                details=f"Backtest time (session_time) stalled for {stall_count} consecutive rows",
                                severity="WARNING",
                            ))
                            stall_count = 0  # Reset to avoid repeated warnings
                    else:
                        stall_count = 0
                    
                    # Check for large gaps in backtest time (> 5 minutes)
                    if prev_time:
                        delta_minutes = (session_time.hour * 60 + session_time.minute) - \
                                      (prev_time.hour * 60 + prev_time.minute)
                        if delta_minutes > 5:
                            self.stats.add_result(ValidationResult(
                                check_name="no_large_time_gaps",
                                passed=False,
                                row_number=row_num,
                                details=f"Large gap in backtest time: {delta_minutes} minutes from {prev_time.strftime('%H:%M:%S')} to {session_time_str}",
                                severity="WARNING",
                            ))
                    
                    prev_time = session_time
                except ValueError:
                    pass
    
    def validate_data_completeness(self):
        """Validate data completeness: session_data + queue = complete data."""
        for symbol in self.symbols:
            last_bar_key = f"{symbol}_last_bar_ts"
            queue_oldest_key = f"{symbol}_queue_BAR_oldest"
            bars_1m_key = f"{symbol}_1m_bars"
            queue_size_key = f"{symbol}_queue_BAR_size"
            
            for idx, row in enumerate(self.rows):
                row_num = idx + 1
                
                last_bar_ts_str = row.get(last_bar_key, "")
                queue_oldest_str = row.get(queue_oldest_key, "")
                bars_1m_str = row.get(bars_1m_key, "")
                queue_size_str = row.get(queue_size_key, "")
                
                # Check continuity: last_bar + queue_oldest should be consecutive
                if last_bar_ts_str and last_bar_ts_str != "N/A" and queue_oldest_str and queue_oldest_str != "N/A":
                    try:
                        last_bar = datetime.strptime(last_bar_ts_str, "%H:%M:%S")
                        queue_oldest = datetime.strptime(queue_oldest_str, "%H:%M:%S")
                        
                        # They should be consecutive (1 minute apart)
                        expected_oldest = last_bar.replace(minute=(last_bar.minute + 1) % 60)
                        if last_bar.minute == 59:
                            expected_oldest = expected_oldest.replace(hour=(last_bar.hour + 1) % 24)
                        
                        time_diff_minutes = (queue_oldest.hour * 60 + queue_oldest.minute) - \
                                          (last_bar.hour * 60 + last_bar.minute)
                        
                        if time_diff_minutes > 1:
                            self.stats.add_result(ValidationResult(
                                check_name="data_continuity",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Gap between last_bar ({last_bar_ts_str}) and queue_oldest ({queue_oldest_str})",
                                severity="ERROR",
                            ))
                        
                        # Check no overlap
                        if queue_oldest <= last_bar:
                            self.stats.add_result(ValidationResult(
                                check_name="no_data_overlap",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Overlap detected - queue_oldest ({queue_oldest_str}) <= last_bar ({last_bar_ts_str})",
                                severity="ERROR",
                            ))
                    except ValueError:
                        pass
                
                # Check total bars for full day (perfect data)
                if bars_1m_str and queue_size_str:
                    try:
                        bars_1m = int(bars_1m_str)
                        queue_size = int(queue_size_str)
                        total_bars = bars_1m + queue_size
                        
                        # For a full trading day, expect ~390 bars (6.5 hours * 60 min)
                        # Allow some tolerance at beginning/end
                        if idx > 100 and total_bars < 350:  # After warmup period
                            self.stats.add_result(ValidationResult(
                                check_name="total_bars_coverage",
                                passed=False,
                                row_number=row_num,
                                details=f"{symbol}: Total bars ({total_bars}) < expected (390) - missing data?",
                                severity="WARNING",
                            ))
                    except ValueError:
                        pass
    
    def validate_chronological_ordering(self):
        """Validate chronological ordering via pending_items."""
        for idx, row in enumerate(self.rows):
            row_num = idx + 1
            
            # Collect pending items for all symbols
            pending_items = {}
            for symbol in self.symbols:
                pending_key = f"{symbol}_pending_bar_ts"
                queue_oldest_key = f"{symbol}_queue_BAR_oldest"
                
                pending_ts_str = row.get(pending_key, "")
                queue_oldest_str = row.get(queue_oldest_key, "")
                
                if pending_ts_str and pending_ts_str not in ["N/A", "EXHAUSTED"]:
                    try:
                        pending_ts = datetime.strptime(pending_ts_str, "%H:%M:%S")
                        pending_items[symbol] = pending_ts
                        
                        # Validate: pending item should match queue oldest
                        if queue_oldest_str and queue_oldest_str != "N/A":
                            queue_oldest = datetime.strptime(queue_oldest_str, "%H:%M:%S")
                            if pending_ts != queue_oldest:
                                self.stats.add_result(ValidationResult(
                                    check_name="pending_matches_queue",
                                    passed=False,
                                    row_number=row_num,
                                    details=f"{symbol}: Pending item ({pending_ts_str}) != queue oldest ({queue_oldest_str})",
                                    severity="ERROR",
                                ))
                    except ValueError:
                        pass
            
            # Check chronological ordering across symbols
            if len(pending_items) >= 2:
                sorted_symbols = sorted(pending_items.keys(), key=lambda s: pending_items[s])
                # Verify they are in chronological order (no inversions)
                for i in range(len(sorted_symbols) - 1):
                    s1, s2 = sorted_symbols[i], sorted_symbols[i + 1]
                    if pending_items[s1] > pending_items[s2]:
                        self.stats.add_result(ValidationResult(
                            check_name="chronological_interleaving",
                            passed=False,
                            row_number=row_num,
                            details=f"Chronological inversion: {s1} ({pending_items[s1].strftime('%H:%M:%S')}) after {s2} ({pending_items[s2].strftime('%H:%M:%S')})",
                            severity="WARNING",
                        ))
    
    def validate_database(self):
        """Validate against database (placeholder)."""
        print("⚠️  Database validation not yet implemented")
        # TODO: Connect to database and verify:
        # - Total bars (session_data + queue) match database
        # - Final volume matches
        # - High/Low match
        # - First/last bar timestamps match
        # - Queue timestamps correspond to real bar timestamps
    
    def print_report(self):
        """Print validation report."""
        print("\n" + "="*80)
        print("VALIDATION REPORT")
        print("="*80 + "\n")
        
        print(f"Total Rows: {self.stats.total_rows}")
        print(f"Total Checks: {self.stats.total_checks}")
        print(f"Passed: {self.stats.passed_checks} ({self.stats.passed_checks/self.stats.total_checks*100:.1f}%)")
        print(f"Failed: {self.stats.failed_checks}")
        print(f"Warnings: {self.stats.warnings}")
        
        if self.stats.violations:
            print(f"\n{'='*80}")
            print(f"VIOLATIONS ({len(self.stats.violations)})")
            print(f"{'='*80}\n")
            
            # Group by severity
            errors = [v for v in self.stats.violations if v.severity == "ERROR"]
            warnings = [v for v in self.stats.violations if v.severity == "WARNING"]
            
            if errors:
                print(f"🚨 ERRORS ({len(errors)}):")
                for v in errors[:20]:  # Show first 20
                    print(f"  Row {v.row_number}: [{v.check_name}] {v.details}")
                if len(errors) > 20:
                    print(f"  ... and {len(errors) - 20} more errors")
            
            if warnings:
                print(f"\n⚠️  WARNINGS ({len(warnings)}):")
                for v in warnings[:20]:  # Show first 20
                    print(f"  Row {v.row_number}: [{v.check_name}] {v.details}")
                if len(warnings) > 20:
                    print(f"  ... and {len(warnings) - 20} more warnings")
        else:
            print("\n✅ All checks passed!")
        
        print(f"\n{'='*80}\n")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate session data CSV dumps against behavioral requirements"
    )
    parser.add_argument(
        'csv_file',
        nargs='?',
        default='validation/test_session.csv',
        help='Path to CSV file (default: validation/test_session.csv)'
    )
    parser.add_argument(
        '--config',
        default='session_configs/example_session.json',
        help='Path to session config JSON (default: session_configs/example_session.json)'
    )
    parser.add_argument(
        '--db-check',
        action='store_true',
        help='Enable database cross-validation'
    )
    
    args = parser.parse_args()
    
    csv_file = Path(args.csv_file)
    config_file = Path(args.config) if args.config else None
    
    if not csv_file.exists():
        print(f"Error: CSV file not found: {csv_file}")
        sys.exit(1)
    
    if config_file and not config_file.exists():
        print(f"Warning: Config file not found: {config_file}")
        print("Proceeding without config-based validation...")
        config_file = None
    
    validator = SessionValidator(csv_file, config_file, args.db_check)
    validator.load_config()
    validator.load_csv()
    validator.validate_all()
    validator.print_report()
    
    # Exit with error code if there are failures
    if validator.stats.failed_checks > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
