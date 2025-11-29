"""
Quality Management - Gap Detection and Quality Scoring

This module provides gap detection and quality measurement functionality
for the Data Quality Manager thread.
"""

from app.threads.quality.gap_detection import (
    GapInfo,
    detect_gaps,
    generate_expected_timestamps,
    group_consecutive_timestamps,
    merge_overlapping_gaps
)

__all__ = [
    'GapInfo',
    'detect_gaps',
    'generate_expected_timestamps',
    'group_consecutive_timestamps',
    'merge_overlapping_gaps'
]
