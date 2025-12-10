"""Complete Gap Scanner Example

Demonstrates the full scanner framework with:
- Lightweight data provisioning (adhoc APIs)
- Criteria-based filtering
- Symbol promotion (idempotent add_symbol)
- Teardown cleanup

This scanner runs PRE-SESSION ONLY to find gap-up stocks.

Configuration (session_config.json):
{
  "module": "scanners.examples.gap_scanner_complete",
  "pre_session": true,
  "config": {
    "universe": "data/universes/sp500_sample.txt"
  }
}
"""

from typing import List, Dict, Any
from pathlib import Path

from scanners.base import BaseScanner, ScanContext, ScanResult
from app.logger import logger


class GapScannerComplete(BaseScanner):
    """Gap scanner - finds stocks with significant gaps from previous close.
    
    HARDCODED Criteria (not in config):
    - Gap >= 2% from previous close
    - Volume >= 1,000,000 shares
    - Price <= $500
    
    HARDCODED Indicators (not in config):
    - SMA(20) on 1d bars
    
    Workflow:
    1. Setup: Load universe from file, provision lightweight data
    2. Scan: Query minimal data, find candidates, upgrade to full symbols
    3. Idempotent: Can call add_symbol() repeatedly without tracking state
    """
    
    # HARDCODED CRITERIA (not in config)
    MIN_GAP_PERCENT = 2.0
    MIN_VOLUME = 1_000_000
    MAX_PRICE = 500.0
    
    def setup(self, context: ScanContext) -> bool:
        """Setup lightweight screening data for universe.
        
        This provisions MINIMAL data for symbols loaded from file.
        Note: add_indicator() AUTOMATICALLY provisions required bars
        via requirement_analyzer (unified routine).
        
        Args:
            context: Scan context with session_data access
        
        Returns:
            True if setup successful
        """
        # Load universe from file (path in config)
        universe_file = self.config.get("universe")
        if not universe_file:
            raise ValueError("Universe file path required in config")
        
        self._universe = self._load_universe_from_file(universe_file)
        
        logger.info(
            f"[GAP_SCANNER] Loaded universe from {universe_file}: "
            f"{len(self._universe)} symbols"
        )
        
        # Provision lightweight data for entire universe
        for symbol in self._universe:
            # HARDCODED indicator (not from config)
            # This AUTOMATICALLY provisions bars via requirement_analyzer!
            context.session_data.add_indicator(
                symbol=symbol,
                indicator_type="sma",
                config={
                    "period": 20,
                    "interval": "1d",
                    "type": "trend",
                    "params": {}
                }
            )
            # The above call AUTOMATICALLY (via requirement_analyzer):
            # 1. Determines 1d bars are needed
            # 2. Provisions historical 1d bars (40 days for SMA(20) warmup)
            # 3. Provisions session 1d bars (for real-time updates)
            # 
            # Scanner doesn't need to manually add bars!
        
        logger.info(
            f"[GAP_SCANNER] Setup complete: "
            f"{len(self._universe)} symbols provisioned with indicators "
            f"(bars auto-provisioned via requirement_analyzer)"
        )
        
        return True
    
    def scan(self, context: ScanContext) -> ScanResult:
        """Scan universe and add qualifying symbols.
        
        This queries lightweight data and upgrades qualifying symbols
        to full strategy symbols via add_symbol().
        
        Flow:
        1. Iterate universe (N symbols)
        2. Query adhoc data (1d bars, SMA indicator)
        3. Apply HARDCODED criteria
        4. If qualifies: add_symbol() → triggers FULL loading
        
        Note: add_symbol() is idempotent - safe to call multiple times!
        
        Args:
            context: Scan context with session_data access
        
        Returns:
            ScanResult with qualifying symbols and metadata
        """
        results = []
        metadata = {}
        
        logger.info(
            f"[GAP_SCANNER] Scanning {len(self._universe)} symbols "
            f"(gap>={self.MIN_GAP_PERCENT}%, volume>={self.MIN_VOLUME:,}, "
            f"price<=${self.MAX_PRICE})"
        )
        
        # Scan lightweight universe
        for symbol in self._universe:
            # Query adhoc daily bar
            bar = context.session_data.get_latest_bar(symbol, "1d")
            if not bar:
                continue
            
            # Query adhoc SMA indicator
            sma_indicator = context.session_data.get_indicator(symbol, "sma_20_1d")
            if not sma_indicator or not sma_indicator.valid:
                continue
            
            # Extract values
            price = bar.close
            volume = bar.volume
            sma = sma_indicator.current_value
            
            # Calculate gap
            gap_pct = ((price - sma) / sma) * 100
            
            # Apply HARDCODED criteria
            if gap_pct >= self.MIN_GAP_PERCENT:
                if volume >= self.MIN_VOLUME:
                    if price <= self.MAX_PRICE:
                        # Symbol qualifies!
                        results.append(symbol)
                        metadata[symbol] = {
                            "gap_percent": round(gap_pct, 2),
                            "price": price,
                            "volume": volume,
                            "sma_20d": sma,
                            "scan_time": context.current_time.isoformat()
                        }
                        
                        logger.info(
                            f"[GAP_SCANNER] Found: {symbol} "
                            f"(gap: {gap_pct:.2f}%, price: ${price:.2f}, "
                            f"volume: {volume:,})"
                        )
                        
                        # UPGRADE to full strategy symbol
                        # This is IDEMPOTENT - safe to call multiple times
                        # session_data handles duplicates internally
                        
                        # This triggers:
                        # 1. Add to session_config.symbols
                        # 2. SessionCoordinator.add_symbol_mid_session()
                        # 3. Load ALL streams from config (1m, 5m, 15m, ...)
                        # 4. Load ALL indicators from config (20+)
                        # 5. Load FULL historical (30 days)
                        # 6. Register with AnalysisEngine
                        
                        context.session_data.add_symbol(symbol)
                        
                        # No need to track state!
                        # Scanner doesn't care if symbol was already added
                        # Multiple scans calling add_symbol() is perfectly fine
        
        logger.info(
            f"[GAP_SCANNER] Scan complete: "
            f"{len(results)} symbols found out of {len(self._universe)}"
        )
        
        return ScanResult(
            symbols=results,
            metadata=metadata
        )
    
    def teardown(self, context: ScanContext):
        """Cleanup after scanner completes (no more schedules).
        
        Called after the last scheduled scan completes.
        Use this to remove symbols that didn't qualify and are no longer needed.
        
        This scanner is pre-session only, so teardown is called immediately
        after the single scan() call, before session starts.
        
        Args:
            context: Scan context with session_data access
        """
        logger.info(f"[GAP_SCANNER] Starting teardown")
        
        # Get list of symbols we promoted to full strategy symbols
        config_symbols = set(context.session_data.get_config_symbols())
        
        removed_count = 0
        
        # Remove universe symbols that weren't promoted
        for symbol in self._universe:
            # Skip if this symbol was promoted to full strategy symbol
            if symbol in config_symbols:
                continue
            
            # Check if symbol is locked (has position or pending order)
            if context.session_data.is_symbol_locked(symbol):
                logger.debug(f"[GAP_SCANNER] Keeping {symbol} (locked)")
                continue
            
            # Symbol didn't qualify and has no position - remove it
            removed = context.session_data.remove_symbol(symbol)
            if removed:
                removed_count += 1
                logger.debug(f"[GAP_SCANNER] Removed {symbol} (did not qualify)")
        
        kept_count = len(self._universe) - removed_count
        
        logger.info(
            f"[GAP_SCANNER] Teardown complete: "
            f"Kept {kept_count} symbols, removed {removed_count} symbols"
        )
    
    # Note: _load_universe_from_file() is inherited from BaseScanner


# ============================================================================
# Usage Example (From SessionCoordinator)
# ============================================================================

"""
# In session_config.json
{
  "scanners": [{
    "module": "scanners.examples.gap_scanner_complete",
    "enabled": true,
    "pre_session": true,
    "regular_session": null,
    
    "config": {
      "universe": "data/universes/sp500.txt"
    }
  }]
}

# Scanner name "gap_scanner_complete" derived from module path
# 
# Criteria and indicators are HARDCODED in scanner source:
#   MIN_GAP_PERCENT = 2.0
#   MIN_VOLUME = 1_000_000
#   MAX_PRICE = 500.0
#   Indicators: SMA(20) on 1d bars

# Scanner lifecycle (Pre-session only, clock STOPPED in backtest):

1. Pre-session setup (ONCE):
   scanner.setup(context)
     → add_indicator() for 500 symbols
       → (AUTOMATICALLY provisions bars via requirement_analyzer)
       → Historical: 40 days of 1d bars (SMA(20) warmup)
       → Session: 1d bars (real-time updates)
     → Total: Minimal data (1 indicator per symbol)

2. Pre-session scan (ONCE before session starts):
   scanner.scan(context)
     → Query 500 symbols (minimal data)
     → Find 3 qualifying: ["TSLA", "NVDA", "AMD"]
     → add_symbol() for each (triggers full loading)
     → Result: 3 strategy symbols ready

3. Pre-session teardown (ONCE after last scan):
   scanner.teardown(context)
     → Remove 497 symbols that didn't qualify
     → Keep 3 qualifying symbols (promoted to full)
     → Free resources

4. Session processing (clock STOPPED):
   → Process session_config requirements
   → Load indicators for qualifying symbols
   
5. Session starts (clock RUNNING):
   → Streaming starts at 09:30
   → Scanner does NOT run (no regular_session schedule)
   → Qualifying symbols (TSLA, NVDA, AMD) trade normally

# Position management (AnalysisEngine):
   on_position_open("TSLA"):
     → session_data.lock_symbol("TSLA", "open_position")
   
   on_position_close("TSLA"):
     → session_data.unlock_symbol("TSLA")
   
   Manual cleanup:
     → session_data.remove_symbol("TSLA")
       # Fails if locked ✅
       # Succeeds if unlocked ✅
"""
