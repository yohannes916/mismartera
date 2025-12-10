"""Momentum Scanner Example

Demonstrates regular session scanning with scheduled execution.
Runs during market hours to find stocks with strong momentum.
"""

from typing import List
from scanners.base import BaseScanner, ScanContext, ScanResult
from app.logger import logger


class MomentumScanner(BaseScanner):
    """Momentum scanner - finds stocks with strong upward momentum.
    
    HARDCODED Criteria (not in config):
    - Price above SMA(20)
    - Volume >= 500,000 shares
    - Positive price change
    
    HARDCODED Indicators (not in config):
    - SMA(20) on 1d bars
    
    Workflow:
    1. Setup: Load universe, provision lightweight data
    2. Scan: Query data every 5 minutes, find momentum stocks
    3. Teardown: Remove symbols that never qualified
    """
    
    # HARDCODED CRITERIA (not in config)
    MIN_VOLUME = 500_000
    
    def setup(self, context: ScanContext) -> bool:
        """Setup lightweight screening data for universe.
        
        This provisions MINIMAL data for symbols loaded from file.
        Note: add_indicator() AUTOMATICALLY provisions required bars.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load universe from config
            universe_file = self.config.get("universe")
            if not universe_file:
                logger.error("[MOMENTUM_SCANNER] No universe file specified in config")
                return False
            
            logger.info(f"[MOMENTUM_SCANNER] Loading universe from: {universe_file}")
            self._universe = self._load_universe_from_file(universe_file)
            logger.info(f"[MOMENTUM_SCANNER] Loaded {len(self._universe)} symbols")
            
            # Provision lightweight data for screening
            logger.info(
                f"[MOMENTUM_SCANNER] Provisioning data for {len(self._universe)} symbols "
                "(this may take a moment)"
            )
            
            for symbol in self._universe:
                # Add indicator - bars will be automatically provisioned!
                # This calls requirement_analyzer which determines needed bars
                context.session_data.add_indicator(
                    symbol=symbol,
                    indicator_type="sma",
                    config={
                        "period": 20,
                        "interval": "1d"
                    }
                )
            
            logger.info("[MOMENTUM_SCANNER] Setup complete - data provisioned")
            return True
            
        except FileNotFoundError as e:
            logger.error(f"[MOMENTUM_SCANNER] Universe file not found: {e}")
            return False
        except Exception as e:
            logger.error(f"[MOMENTUM_SCANNER] Setup failed: {e}", exc_info=True)
            return False
    
    def scan(self, context: ScanContext) -> ScanResult:
        """Scan universe for momentum stocks.
        
        Called on schedule (e.g., every 5 minutes during session).
        
        Responsibilities:
        - Query lightweight data
        - Find stocks with strong momentum
        - Promote qualifying symbols via add_symbol() (idempotent)
        
        Returns:
            ScanResult with qualifying symbols
        """
        logger.info(f"[MOMENTUM_SCANNER] Scanning {len(self._universe)} symbols for momentum...")
        
        qualifying_symbols = []
        
        for symbol in self._universe:
            try:
                # Get symbol data
                symbol_data = context.session_data.get_symbol_data(symbol)
                if not symbol_data:
                    continue
                
                # Check criteria
                if self._meets_criteria(symbol, symbol_data, context):
                    # Promote to full symbol (idempotent - safe to call multiple times)
                    context.session_data.add_symbol(symbol)
                    qualifying_symbols.append(symbol)
                    logger.debug(f"[MOMENTUM_SCANNER] {symbol} qualifies for momentum")
                
            except Exception as e:
                logger.warning(f"[MOMENTUM_SCANNER] Error checking {symbol}: {e}")
                continue
        
        logger.info(f"[MOMENTUM_SCANNER] Found {len(qualifying_symbols)} momentum stocks")
        
        return ScanResult(
            symbols=qualifying_symbols,
            metadata={
                "scanned": len(self._universe),
                "qualified": len(qualifying_symbols),
                "criteria": "price_above_sma20_and_volume"
            }
        )
    
    def teardown(self, context: ScanContext) -> None:
        """Cleanup after scanner completes.
        
        Called when scanner has no more scheduled scans.
        
        Responsibilities:
        - Remove symbols that never qualified
        - Only remove if not locked (no open position)
        - Skip config symbols (never remove those)
        """
        logger.info("[MOMENTUM_SCANNER] Teardown starting")
        
        # Get config symbols (never remove these)
        config_symbols = context.session_data.get_config_symbols()
        
        # Get all symbols we've seen qualify during any scan
        qualified_symbols = set()
        for symbol in self._universe:
            symbol_data = context.session_data.get_symbol_data(symbol)
            if symbol_data:
                # If symbol has data, it qualified at some point
                qualified_symbols.add(symbol)
        
        # Remove symbols that didn't qualify
        removed_count = 0
        for symbol in self._universe:
            # Skip if config symbol
            if symbol in config_symbols:
                logger.debug(f"[MOMENTUM_SCANNER] Skipping {symbol} (config symbol)")
                continue
            
            # Skip if qualified at any point
            if symbol in qualified_symbols:
                logger.debug(f"[MOMENTUM_SCANNER] Keeping {symbol} (qualified)")
                continue
            
            # Try to remove (will check if locked)
            if context.session_data.remove_symbol_adhoc(symbol):
                removed_count += 1
                logger.debug(f"[MOMENTUM_SCANNER] Removed {symbol} (never qualified)")
        
        kept_count = len(self._universe) - removed_count
        
        logger.info(
            f"[MOMENTUM_SCANNER] Teardown complete: "
            f"Kept {kept_count} symbols, removed {removed_count} symbols"
        )
    
    def _meets_criteria(self, symbol: str, symbol_data, context: ScanContext) -> bool:
        """Check if symbol meets momentum criteria.
        
        Criteria:
        - Volume >= MIN_VOLUME
        - Current price above SMA(20)
        - Positive price change
        
        Args:
            symbol: Symbol to check
            symbol_data: SymbolSessionData instance
            context: Scan context
        
        Returns:
            True if qualifies, False otherwise
        """
        # Volume check
        if symbol_data.metrics.volume < self.MIN_VOLUME:
            return False
        
        # Get latest 1m bar
        latest_bar = symbol_data.get_latest_bar("1m")
        if not latest_bar:
            return False
        
        current_price = latest_bar.close
        
        # Get SMA(20) indicator
        sma_indicator = symbol_data.indicators.get("sma_20_1d")
        if not sma_indicator or not sma_indicator.values:
            return False
        
        sma_value = sma_indicator.values[-1]
        
        # Price above SMA check
        if current_price <= sma_value:
            return False
        
        # Positive price change check
        if latest_bar.close <= latest_bar.open:
            return False
        
        return True


# Export for scanner manager
__all__ = ["MomentumScanner"]
