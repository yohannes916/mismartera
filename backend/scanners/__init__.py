"""Scanner Framework

Dynamic symbol scanner framework for ad-hoc symbol discovery and provisioning.

Scanners can:
- Load lightweight data for large universes (hundreds of symbols)
- Scan for qualifying symbols using custom criteria
- Promote qualifying symbols to full strategy symbols
- Clean up unused symbols during teardown

Key Concepts:
- Lightweight provisioning: add_indicator() with automatic bars
- Full promotion: add_symbol() triggers full loading
- Idempotent operations: Safe to call multiple times
- Lock protection: Cannot remove symbols with open positions
- Teardown cleanup: Remove unqualified symbols after last scan
"""

from scanners.base import (
    BaseScanner,
    ScanContext,
    ScanResult,
)

__all__ = [
    "BaseScanner",
    "ScanContext",
    "ScanResult",
]
