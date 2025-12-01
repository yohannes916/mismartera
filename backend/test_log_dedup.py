#!/usr/bin/env python3
"""
Test script to demonstrate log deduplication functionality.

This script shows how the LogDeduplicationFilter suppresses repeated
logs from the same location within the configured time threshold.
"""
import time
from app.logger import logger

def test_basic_deduplication():
    """Test that consecutive logs from same location are suppressed."""
    print("\n=== Test 1: Basic Deduplication ===")
    print("Logging 5 times rapidly from same line (should only see 1 log):\n")
    
    for i in range(5):
        logger.debug(f"Registered SYMBOL_{i} -> EXCHANGE")  # Same line number
        time.sleep(0.1)  # 100ms apart - within 1s threshold
    
    print("\nExpected: Only 1 log message in the file (others suppressed)")


def test_different_lines():
    """Test that logs from different lines are NOT suppressed."""
    print("\n=== Test 2: Different Lines (Not Suppressed) ===")
    print("Logging from different lines (should see all logs):\n")
    
    logger.debug("Log from line 1")
    logger.debug("Log from line 2")
    logger.debug("Log from line 3")
    
    print("\nExpected: All 3 log messages appear")


def test_time_threshold():
    """Test that logs after time threshold are NOT suppressed."""
    print("\n=== Test 3: Time Threshold ===")
    print("Logging from same line with 1.5s delay (should see both):\n")
    
    logger.debug("First log from this line")
    time.sleep(1.5)  # Wait longer than 1s threshold
    logger.debug("Second log from this line")
    
    print("\nExpected: Both logs appear (1.5s > 1s threshold)")


def test_multiple_locations():
    """Test tracking of multiple different locations."""
    print("\n=== Test 4: Multiple Locations ===")
    print("Logging from 3 different locations rapidly (should see 3 logs):\n")
    
    logger.debug("Location A")
    logger.info("Location B")
    logger.warning("Location C")
    
    print("\nExpected: All 3 logs appear (different locations)")


def simulate_loop_scenario():
    """Simulate the original use case - loop logging."""
    print("\n=== Test 5: Loop Scenario (Original Use Case) ===")
    print("Simulating symbol registration loop (should only see 1 log):\n")
    
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    for symbol in symbols:
        logger.debug(f"Registered {symbol} -> NASDAQ")  # Same line in loop
    
    print("\nExpected: Only 1 log (others suppressed within 1s)")


if __name__ == "__main__":
    print("=" * 70)
    print("LOG DEDUPLICATION TEST")
    print("=" * 70)
    print("\nConfiguration:")
    print("  - LOG_DEDUP_ENABLED: True")
    print("  - LOG_DEDUP_HISTORY: 5")
    print("  - LOG_DEDUP_THRESHOLD: 1.0s")
    print("\nCheck: backend/data/logs/app.log")
    print("=" * 70)
    
    # Run tests
    test_basic_deduplication()
    time.sleep(2)  # Clear threshold between tests
    
    test_different_lines()
    time.sleep(2)
    
    test_time_threshold()
    time.sleep(2)
    
    test_multiple_locations()
    time.sleep(2)
    
    simulate_loop_scenario()
    
    print("\n" + "=" * 70)
    print("Tests complete! Check backend/data/logs/app.log for results")
    print("=" * 70)
