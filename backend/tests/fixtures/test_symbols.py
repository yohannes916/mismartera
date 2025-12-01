"""Test Symbol Definitions

Synthetic symbols for testing with well-defined characteristics.
Each symbol tests a specific scenario (perfect data, gaps, early close, holiday).
"""
from datetime import date
from typing import Dict, List, Optional


class TestSymbol:
    """Test symbol with known characteristics."""
    
    def __init__(
        self,
        symbol: str,
        description: str,
        trading_days: List[date],
        bars_per_day: int,
        missing_bars: Optional[Dict[date, List[str]]] = None,
        expected_quality: Optional[float] = None
    ):
        self.symbol = symbol
        self.description = description
        self.trading_days = trading_days
        self.bars_per_day = bars_per_day
        self.missing_bars = missing_bars or {}
        self.expected_quality = expected_quality
    
    def get_actual_bars_for_date(self, target_date: date) -> int:
        """Get actual number of bars for a specific date."""
        if target_date not in self.trading_days:
            return 0
        
        missing = len(self.missing_bars.get(target_date, []))
        return self.bars_per_day - missing


# Test symbol definitions
TEST_SYMBOLS = {
    "SYMBOL_X": TestSymbol(
        symbol="SYMBOL_X",
        description="Perfect data - no gaps, regular trading days",
        trading_days=[
            date(2025, 1, 2),   # Thursday
            date(2025, 1, 3),   # Friday
        ],
        bars_per_day=390,  # Full day: 9:30 AM - 4:00 PM
        missing_bars={},
        expected_quality=100.0
    ),
    
    "SYMBOL_Y": TestSymbol(
        symbol="SYMBOL_Y",
        description="Missing bars - small gaps",
        trading_days=[
            date(2025, 1, 2),
            date(2025, 1, 3),
        ],
        bars_per_day=390,
        missing_bars={
            date(2025, 1, 2): ["09:35", "09:36", "10:15"],  # 3 missing
            date(2025, 1, 3): ["14:00", "14:01"],           # 2 missing
        },
        expected_quality=99.23  # (390-3)/390 * 100 for day 1
    ),
    
    "SYMBOL_Z": TestSymbol(
        symbol="SYMBOL_Z",
        description="Early close day (Thanksgiving)",
        trading_days=[
            date(2024, 11, 28),  # Thanksgiving 2024 (half-day)
        ],
        bars_per_day=210,  # Half day: 9:30 AM - 1:00 PM
        missing_bars={},
        expected_quality=100.0
    ),
    
    "SYMBOL_W": TestSymbol(
        symbol="SYMBOL_W",
        description="Holiday - no trading (Christmas)",
        trading_days=[
            date(2024, 12, 25),  # Christmas 2024
        ],
        bars_per_day=0,  # Market closed
        missing_bars={},
        expected_quality=None  # No quality on holidays
    ),
    
    "SYMBOL_V": TestSymbol(
        symbol="SYMBOL_V",
        description="Large gap - significant missing data",
        trading_days=[
            date(2025, 1, 2),
        ],
        bars_per_day=390,
        missing_bars={
            date(2025, 1, 2): [
                f"{h:02d}:{m:02d}" 
                for h in range(10, 12) 
                for m in range(0, 60)
            ],  # Missing 10:00-11:59 (120 bars)
        },
        expected_quality=69.23  # (390-120)/390 * 100
    ),
}


def get_test_symbol(symbol: str) -> TestSymbol:
    """Get test symbol by name."""
    if symbol not in TEST_SYMBOLS:
        raise ValueError(f"Unknown test symbol: {symbol}. Available: {list(TEST_SYMBOLS.keys())}")
    return TEST_SYMBOLS[symbol]


def get_all_test_dates() -> List[date]:
    """Get all unique trading dates across test symbols."""
    dates = set()
    for symbol_data in TEST_SYMBOLS.values():
        dates.update(symbol_data.trading_days)
    return sorted(dates)
