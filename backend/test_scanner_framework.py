"""Scanner Framework Test Validation Script

Validates scanner framework behavior by analyzing system logs.

Usage:
    python test_scanner_framework.py [log_file]
    
    If no log_file specified, uses latest from logs/mismartera_*.log
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict


class ScannerTestValidator:
    """Validates scanner framework test results."""
    
    def __init__(self, log_file: str):
        """Initialize validator with log file."""
        self.log_file = log_file
        self.log_lines = []
        self.results = {
            "initialization": {"passed": False, "details": []},
            "pre_session": {"passed": False, "details": []},
            "regular_session": {"passed": False, "details": []},
            "teardown": {"passed": False, "details": []},
            "errors": [],
            "warnings": []
        }
    
    def load_logs(self) -> bool:
        """Load log file."""
        try:
            with open(self.log_file, 'r') as f:
                self.log_lines = f.readlines()
            print(f"✅ Loaded {len(self.log_lines)} log lines from {self.log_file}")
            return True
        except FileNotFoundError:
            print(f"❌ Log file not found: {self.log_file}")
            return False
        except Exception as e:
            print(f"❌ Error loading log file: {e}")
            return False
    
    def validate(self) -> Dict[str, Any]:
        """Run all validation checks."""
        print("\n" + "="*70)
        print("SCANNER FRAMEWORK TEST VALIDATION")
        print("="*70 + "\n")
        
        self.check_initialization()
        self.check_pre_session_setup()
        self.check_regular_session_scans()
        self.check_teardown()
        self.check_errors_warnings()
        
        return self.results
    
    def check_initialization(self):
        """Validate scanner manager initialization."""
        print("📋 Checking Scanner Initialization...")
        
        # Check scanner manager creation
        scanner_mgr_created = any("[SESSION_FLOW] 2.b.3: ScannerManager created" in line 
                                  for line in self.log_lines)
        
        # Check scanner manager initialized
        scanner_mgr_initialized = any("[SESSION_FLOW] 2.b.4: ScannerManager initialized" in line 
                                      for line in self.log_lines)
        
        # Check scanners loaded
        scanners_loaded = []
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Loaded scanner: (.+)', line)
            if match:
                scanners_loaded.append(match.group(1))
        
        # Check scanner count
        scanner_count_match = None
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Loaded (\d+) scanners', line)
            if match:
                scanner_count_match = int(match.group(1))
                break
        
        if scanner_mgr_created and scanner_mgr_initialized:
            self.results["initialization"]["passed"] = True
            print("  ✅ Scanner manager created and initialized")
        else:
            print("  ❌ Scanner manager initialization failed")
            return
        
        if scanners_loaded:
            self.results["initialization"]["details"] = scanners_loaded
            print(f"  ✅ Loaded {len(scanners_loaded)} scanners:")
            for scanner in scanners_loaded:
                print(f"     - {scanner}")
        else:
            print("  ❌ No scanners loaded")
        
        if scanner_count_match:
            print(f"  ✅ Scanner count verified: {scanner_count_match}")
        
        print()
    
    def check_pre_session_setup(self):
        """Validate pre-session scanner execution."""
        print("🔍 Checking Pre-Session Scanner Setup...")
        
        # Check pre-session phase started
        pre_session_started = any("PHASE_2.5: Pre-Session Scanner Setup" in line 
                                  for line in self.log_lines)
        
        if not pre_session_started:
            print("  ❌ Pre-session phase not started")
            return
        
        # Check setup calls
        setups = []
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Setting up scanner: (.+)', line)
            if match:
                setups.append(match.group(1))
        
        # Check scan calls (pre-session)
        pre_scans = []
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Scanning \(pre-session\): (.+)', line)
            if match:
                pre_scans.append(match.group(1))
        
        # Check teardowns (pre-session only scanners)
        teardowns = []
        for line in self.log_lines:
            if "Tearing down pre-session-only scanner" in line:
                match = re.search(r'scanner: (.+)', line)
                if match:
                    teardowns.append(match.group(1))
        
        # Check for qualifying symbols
        qualifying_symbols = []
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Qualifying symbols: \[(.+)\]', line)
            if match:
                symbols = match.group(1).replace("'", "").replace('"', '').split(", ")
                qualifying_symbols.extend(symbols)
        
        if setups:
            print(f"  ✅ Setup called for {len(setups)} scanners")
            for scanner in setups:
                print(f"     - {scanner}")
        
        if pre_scans:
            print(f"  ✅ Pre-session scan executed for {len(pre_scans)} scanners")
            for scanner in pre_scans:
                print(f"     - {scanner}")
            self.results["pre_session"]["passed"] = True
        
        if teardowns:
            print(f"  ✅ Teardown executed for {len(teardowns)} pre-session-only scanners")
            for scanner in teardowns:
                print(f"     - {scanner}")
        
        if qualifying_symbols:
            print(f"  ✅ Found {len(qualifying_symbols)} qualifying symbols:")
            print(f"     {qualifying_symbols}")
            self.results["pre_session"]["details"] = qualifying_symbols
        
        print()
    
    def check_regular_session_scans(self):
        """Validate regular session scanner execution."""
        print("⏰ Checking Regular Session Scans...")
        
        # Check session started notification
        session_started = any("[SCANNER_MANAGER] Session started" in line 
                             for line in self.log_lines)
        
        if not session_started:
            print("  ℹ️  No regular session scanners scheduled")
            return
        
        print("  ✅ Session start notification sent")
        
        # Check for next scan time initialization
        next_scan_times = []
        for line in self.log_lines:
            match = re.search(r'\[SCANNER_MANAGER\] Next scan for (.+): (.+)', line)
            if match:
                scanner = match.group(1)
                scan_time = match.group(2)
                next_scan_times.append((scanner, scan_time))
        
        if next_scan_times:
            print(f"  ✅ Scheduled {len(next_scan_times)} regular session scanners:")
            for scanner, scan_time in next_scan_times:
                print(f"     - {scanner} at {scan_time}")
        
        # Check for scheduled scan triggers
        triggered_scans = []
        for line in self.log_lines:
            if "Scheduled scan triggered" in line:
                match = re.search(r'triggered: (.+) at (.+)', line)
                if match:
                    scanner = match.group(1)
                    time = match.group(2)
                    triggered_scans.append((scanner, time))
        
        if triggered_scans:
            print(f"  ✅ Executed {len(triggered_scans)} scheduled scans:")
            for scanner, time in triggered_scans:
                print(f"     - {scanner} at {time}")
            self.results["regular_session"]["passed"] = True
            self.results["regular_session"]["details"] = triggered_scans
        else:
            print("  ℹ️  No scheduled scans triggered (check if time window reached)")
        
        print()
    
    def check_teardown(self):
        """Validate scanner teardown."""
        print("🧹 Checking Scanner Teardown...")
        
        # Check session end notification
        session_ended = any("[SCANNER_MANAGER] Session ended" in line 
                           for line in self.log_lines)
        
        if not session_ended:
            print("  ❌ Session end notification not found")
            return
        
        print("  ✅ Session end notification sent")
        
        # Check teardown calls
        teardowns = []
        for line in self.log_lines:
            if "[SCANNER_MANAGER] Tearing down scanner:" in line:
                match = re.search(r'scanner: (.+)', line)
                if match:
                    scanner = match.group(1)
                    if scanner not in teardowns:  # Avoid duplicates
                        teardowns.append(scanner)
        
        if teardowns:
            print(f"  ✅ Teardown executed for {len(teardowns)} scanners:")
            for scanner in teardowns:
                print(f"     - {scanner}")
            self.results["teardown"]["passed"] = True
            self.results["teardown"]["details"] = teardowns
        
        print()
    
    def check_errors_warnings(self):
        """Check for errors and warnings."""
        print("⚠️  Checking for Errors and Warnings...")
        
        errors = []
        warnings = []
        
        for line in self.log_lines:
            if "[SCANNER" in line or "SCANNER_MANAGER" in line:
                if " ERROR " in line or "Error" in line or "FAILED" in line:
                    errors.append(line.strip())
                elif " WARNING " in line or "Warning" in line:
                    warnings.append(line.strip())
        
        if errors:
            print(f"  ❌ Found {len(errors)} errors:")
            for error in errors[:5]:  # Show first 5
                print(f"     {error}")
            if len(errors) > 5:
                print(f"     ... and {len(errors) - 5} more")
            self.results["errors"] = errors
        else:
            print("  ✅ No errors found")
        
        if warnings:
            print(f"  ⚠️  Found {len(warnings)} warnings:")
            for warning in warnings[:5]:  # Show first 5
                print(f"     {warning}")
            if len(warnings) > 5:
                print(f"     ... and {len(warnings) - 5} more")
            self.results["warnings"] = warnings
        else:
            print("  ✅ No warnings found")
        
        print()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70 + "\n")
        
        passed = 0
        total = 4
        
        if self.results["initialization"]["passed"]:
            print("✅ Initialization: PASSED")
            passed += 1
        else:
            print("❌ Initialization: FAILED")
        
        if self.results["pre_session"]["passed"]:
            print("✅ Pre-Session: PASSED")
            passed += 1
        else:
            print("❌ Pre-Session: FAILED")
        
        if self.results["regular_session"]["passed"]:
            print("✅ Regular Session: PASSED")
            passed += 1
        else:
            print("ℹ️  Regular Session: N/A (may not have reached scheduled time)")
        
        if self.results["teardown"]["passed"]:
            print("✅ Teardown: PASSED")
            passed += 1
        else:
            print("❌ Teardown: FAILED")
        
        print(f"\n📊 Score: {passed}/{total} checks passed")
        
        if self.results["errors"]:
            print(f"❌ {len(self.results['errors'])} errors detected")
        
        if self.results["warnings"]:
            print(f"⚠️  {len(self.results['warnings'])} warnings detected")
        
        if passed == total and not self.results["errors"]:
            print("\n🎉 Scanner framework test: PASSED!")
        elif passed >= 2:
            print("\n✅ Scanner framework test: PARTIALLY PASSED")
        else:
            print("\n❌ Scanner framework test: FAILED")


def find_latest_log() -> str:
    """Find latest log file."""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return None
    
    log_files = list(logs_dir.glob("mismartera_*.log"))
    if not log_files:
        return None
    
    # Sort by modification time, newest first
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(log_files[0])


def main():
    """Main entry point."""
    # Get log file
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = find_latest_log()
        if not log_file:
            print("❌ No log file found. Please specify a log file:")
            print("   python test_scanner_framework.py logs/mismartera_YYYYMMDD_HHMMSS.log")
            sys.exit(1)
        print(f"📄 Using latest log file: {log_file}\n")
    
    # Run validation
    validator = ScannerTestValidator(log_file)
    
    if not validator.load_logs():
        sys.exit(1)
    
    validator.validate()
    validator.print_summary()


if __name__ == "__main__":
    main()
