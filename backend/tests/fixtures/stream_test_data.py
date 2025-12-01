"""Test Data Scenarios for Stream Determination Integration Tests

Defines controlled test scenarios with known database availability
for testing stream determination logic.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple, Optional


@dataclass
class StreamTestScenario:
    """Test scenario definition with known DB availability."""
    name: str
    description: str
    symbol: str
    date_range: Tuple[date, date]
    
    # Database availability flags
    has_1s: bool
    has_1m: bool
    has_1d: bool
    has_quotes: bool
    
    # Expected outcomes for testing
    expected_stream_interval: Optional[str]  # What should be streamed
    expected_generate_intervals: List[str]   # What should be generated
    
    # Additional metadata
    quality_1s: float = 100.0  # Quality of 1s data if available
    quality_1m: float = 100.0  # Quality of 1m data if available
    quality_1d: float = 100.0  # Quality of 1d data if available


# =============================================================================
# Test Scenarios
# =============================================================================

SCENARIOS = {
    # Perfect 1s data available
    "perfect_1s": StreamTestScenario(
        name="Perfect 1s Data",
        description="Symbol has complete 1s data available",
        symbol="TEST_1S",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=True,
        has_1m=False,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval="1s",
        expected_generate_intervals=[],
        quality_1s=100.0
    ),
    
    # Perfect 1m data available
    "perfect_1m": StreamTestScenario(
        name="Perfect 1m Data",
        description="Symbol has complete 1m data available",
        symbol="TEST_1M",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=False,
        has_1m=True,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval="1m",
        expected_generate_intervals=[],
        quality_1m=100.0
    ),
    
    # Only daily data available
    "only_1d": StreamTestScenario(
        name="Only Daily Data",
        description="Symbol only has daily bars available",
        symbol="TEST_1D",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=False,
        has_1m=False,
        has_1d=True,
        has_quotes=False,
        expected_stream_interval="1d",
        expected_generate_intervals=[],
        quality_1d=100.0
    ),
    
    # Both 1s and 1m available (should stream 1s)
    "1s_and_1m": StreamTestScenario(
        name="Both 1s and 1m Available",
        description="Symbol has both 1s and 1m, should stream 1s (smallest)",
        symbol="TEST_1S_1M",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=True,
        has_1m=True,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval="1s",
        expected_generate_intervals=["1m"],  # 1m will be generated
        quality_1s=100.0,
        quality_1m=100.0
    ),
    
    # All intervals available (should stream 1s)
    "all_intervals": StreamTestScenario(
        name="All Intervals Available",
        description="Symbol has 1s, 1m, and 1d, should stream 1s",
        symbol="TEST_ALL",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=True,
        has_1m=True,
        has_1d=True,
        has_quotes=True,
        expected_stream_interval="1s",
        expected_generate_intervals=["1m", "1d"],
        quality_1s=100.0,
        quality_1m=100.0,
        quality_1d=100.0
    ),
    
    # No base interval (error case)
    "no_base": StreamTestScenario(
        name="No Base Interval",
        description="Symbol has no base intervals (error)",
        symbol="TEST_EMPTY",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=False,
        has_1m=False,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval=None,  # Error
        expected_generate_intervals=[]
    ),
    
    # 1m with gaps (for gap filling tests)
    "1m_with_gaps": StreamTestScenario(
        name="1m with Gaps",
        description="Symbol has 1m data with gaps",
        symbol="TEST_1M_GAPS",
        date_range=(date(2025, 1, 2), date(2025, 1, 2)),
        has_1s=False,
        has_1m=True,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval="1m",
        expected_generate_intervals=[],
        quality_1m=99.0  # Has gaps
    ),
    
    # Complete 1s, gaps in 1m (for gap filling)
    "1s_complete_1m_gaps": StreamTestScenario(
        name="Complete 1s, Gaps in 1m",
        description="Complete 1s data available, can fill 1m gaps",
        symbol="TEST_GAPFILL",
        date_range=(date(2025, 1, 2), date(2025, 1, 2)),
        has_1s=True,
        has_1m=True,
        has_1d=False,
        has_quotes=False,
        expected_stream_interval="1s",
        expected_generate_intervals=["1m"],
        quality_1s=100.0,
        quality_1m=99.0  # Has gaps (can be filled from 1s)
    ),
    
    # Quote testing scenarios
    "with_quotes": StreamTestScenario(
        name="With Quotes",
        description="Symbol has 1m bars and quotes",
        symbol="TEST_QUOTES",
        date_range=(date(2025, 1, 2), date(2025, 1, 3)),
        has_1s=False,
        has_1m=True,
        has_1d=False,
        has_quotes=True,
        expected_stream_interval="1m",
        expected_generate_intervals=[],
        quality_1m=100.0
    ),
}


def get_scenario(name: str) -> StreamTestScenario:
    """Get test scenario by name.
    
    Args:
        name: Scenario name (key in SCENARIOS dict)
    
    Returns:
        StreamTestScenario
    
    Raises:
        KeyError: If scenario not found
    """
    return SCENARIOS[name]


def get_all_scenarios() -> Dict[str, StreamTestScenario]:
    """Get all test scenarios.
    
    Returns:
        Dict of scenario name -> StreamTestScenario
    """
    return SCENARIOS.copy()


def get_scenarios_by_availability(
    has_1s: Optional[bool] = None,
    has_1m: Optional[bool] = None,
    has_1d: Optional[bool] = None
) -> List[StreamTestScenario]:
    """Filter scenarios by DB availability.
    
    Args:
        has_1s: Filter by 1s availability (None = any)
        has_1m: Filter by 1m availability (None = any)
        has_1d: Filter by 1d availability (None = any)
    
    Returns:
        List of matching scenarios
    """
    results = []
    for scenario in SCENARIOS.values():
        if has_1s is not None and scenario.has_1s != has_1s:
            continue
        if has_1m is not None and scenario.has_1m != has_1m:
            continue
        if has_1d is not None and scenario.has_1d != has_1d:
            continue
        results.append(scenario)
    return results


# =============================================================================
# Helper Functions for Test Data Generation
# =============================================================================

def create_mock_availability(scenario: StreamTestScenario):
    """Create AvailabilityInfo from scenario.
    
    Args:
        scenario: StreamTestScenario
    
    Returns:
        AvailabilityInfo matching scenario
    """
    from app.threads.quality.stream_determination import AvailabilityInfo
    
    return AvailabilityInfo(
        symbol=scenario.symbol,
        has_1s=scenario.has_1s,
        has_1m=scenario.has_1m,
        has_1d=scenario.has_1d,
        has_quotes=scenario.has_quotes
    )


# =============================================================================
# Test Data Examples
# =============================================================================

# Example: Get all scenarios with only 1m data
# scenarios_1m_only = get_scenarios_by_availability(has_1s=False, has_1m=True, has_1d=False)

# Example: Get specific scenario
# perfect_1s_scenario = get_scenario("perfect_1s")

# Example: Create availability info for testing
# from stream_test_data import SCENARIOS, create_mock_availability
# scenario = SCENARIOS["perfect_1s"]
# availability = create_mock_availability(scenario)
