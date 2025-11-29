"""Symbol-to-Exchange Mapping System

Maps stock symbols to their primary exchanges for data storage and retrieval.
Symbols within an exchange group (e.g., US_EQUITY) are unique across all exchanges.
"""
from typing import Dict, Optional
from app.logger import logger


# Symbol to Exchange mapping
# Format: {SYMBOL: EXCHANGE_CODE}
SYMBOL_EXCHANGE_MAP: Dict[str, str] = {}


def register_symbol(symbol: str, exchange: str) -> None:
    """Register a symbol with its primary exchange
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        exchange: Exchange code (e.g., 'NYSE', 'NASDAQ')
    """
    symbol = symbol.upper()
    SYMBOL_EXCHANGE_MAP[symbol] = exchange
    logger.debug(f"Registered {symbol} -> {exchange}")


def get_symbol_exchange(symbol: str, default_exchange: str = "NYSE") -> str:
    """Get the exchange for a symbol
    
    Args:
        symbol: Stock symbol
        default_exchange: Fallback exchange if symbol not found
        
    Returns:
        Exchange code
    """
    symbol = symbol.upper()
    return SYMBOL_EXCHANGE_MAP.get(symbol, default_exchange)


def has_symbol(symbol: str) -> bool:
    """Check if a symbol is registered
    
    Args:
        symbol: Stock symbol
        
    Returns:
        True if symbol is registered
    """
    return symbol.upper() in SYMBOL_EXCHANGE_MAP


def get_all_symbols_for_exchange(exchange: str) -> list[str]:
    """Get all symbols registered to an exchange
    
    Args:
        exchange: Exchange code
        
    Returns:
        List of symbols
    """
    return [sym for sym, exch in SYMBOL_EXCHANGE_MAP.items() if exch == exchange]


def clear_mappings() -> None:
    """Clear all symbol-to-exchange mappings"""
    SYMBOL_EXCHANGE_MAP.clear()
    logger.info("Cleared all symbol-exchange mappings")


def load_symbols_from_config(symbols_config: list[dict]) -> None:
    """Load symbol mappings from configuration
    
    Args:
        symbols_config: List of dicts with 'symbol' and 'exchange' keys
        
    Example:
        >>> load_symbols_from_config([
        ...     {'symbol': 'AAPL', 'exchange': 'NASDAQ'},
        ...     {'symbol': 'GOOGL', 'exchange': 'NASDAQ'},
        ... ])
    """
    for config in symbols_config:
        symbol = config.get('symbol')
        exchange = config.get('exchange', 'NYSE')
        if symbol:
            register_symbol(symbol, exchange)
    logger.info(f"Loaded {len(symbols_config)} symbol mappings from config")


# Common US symbols (can be extended)
_US_EQUITY_SYMBOLS = {
    # NASDAQ
    'AAPL': 'NASDAQ',
    'MSFT': 'NASDAQ',
    'GOOGL': 'NASDAQ',
    'GOOG': 'NASDAQ',
    'AMZN': 'NASDAQ',
    'NVDA': 'NASDAQ',
    'META': 'NASDAQ',
    'TSLA': 'NASDAQ',
    'AMD': 'NASDAQ',
    'NFLX': 'NASDAQ',
    
    # NYSE
    'BRK.A': 'NYSE',
    'BRK.B': 'NYSE',
    'JPM': 'NYSE',
    'V': 'NYSE',
    'UNH': 'NYSE',
    'MA': 'NYSE',
    'HD': 'NYSE',
    'PG': 'NYSE',
    'JNJ': 'NYSE',
    'BAC': 'NYSE',
    'XOM': 'NYSE',
    'CVX': 'NYSE',
    'WMT': 'NYSE',
    'LLY': 'NYSE',
    'ABBV': 'NYSE',
    'MRK': 'NYSE',
    'KO': 'NYSE',
    'PEP': 'NYSE',
    'COST': 'NASDAQ',
    'AVGO': 'NASDAQ',
    'NKE': 'NYSE',
    'DIS': 'NYSE',
    'CSCO': 'NASDAQ',
    'ADBE': 'NASDAQ',
    'INTC': 'NASDAQ',
    'PFE': 'NYSE',
    'CRM': 'NYSE',
    'TMO': 'NYSE',
    'VZ': 'NYSE',
    'CMCSA': 'NASDAQ',
    'ORCL': 'NYSE',
    'ABT': 'NYSE',
    'MCD': 'NYSE',
    'QCOM': 'NASDAQ',
    'TXN': 'NASDAQ',
    'DHR': 'NYSE',
    'HON': 'NASDAQ',
    'UNP': 'NYSE',
    'NEE': 'NYSE',
    'UPS': 'NYSE',
    'LOW': 'NYSE',
    'BMY': 'NYSE',
    'RTX': 'NYSE',
    'T': 'NYSE',
    'AMGN': 'NASDAQ',
    'BA': 'NYSE',
    'SPGI': 'NYSE',
    'SBUX': 'NASDAQ',
    'CAT': 'NYSE',
    'GE': 'NYSE',
    'AMD': 'NASDAQ',
    'PYPL': 'NASDAQ',
    'TMUS': 'NASDAQ',
    'SCHW': 'NYSE',
    'AXP': 'NYSE',
    'BLK': 'NYSE',
    'DE': 'NYSE',
    'INTU': 'NASDAQ',
    'GILD': 'NASDAQ',
    'MDT': 'NYSE',
    'CI': 'NYSE',
    'ISRG': 'NASDAQ',
    'MMM': 'NYSE',
    'BKNG': 'NASDAQ',
    'LRCX': 'NASDAQ',
    'REGN': 'NASDAQ',
    'AMAT': 'NASDAQ',
    'ZTS': 'NYSE',
    'SYK': 'NYSE',
    'CB': 'NYSE',
    'VRTX': 'NASDAQ',
    'MU': 'NASDAQ',
    'MDLZ': 'NASDAQ',
    'CHTR': 'NASDAQ',
    'EQIX': 'NASDAQ',
    'ADI': 'NASDAQ',
    'PLD': 'NYSE',
    'SO': 'NYSE',
    'DUK': 'NYSE',
    'EOG': 'NYSE',
    'CSX': 'NASDAQ',
    'CL': 'NYSE',
    'APD': 'NYSE',
    'MMC': 'NYSE',
    'SHW': 'NYSE',
    'ITW': 'NYSE',
    'NSC': 'NYSE',
    'NOC': 'NYSE',
    'GD': 'NYSE',
    'EMR': 'NYSE',
    'ATVI': 'NASDAQ',
    'FISV': 'NASDAQ',
    'ICE': 'NYSE',
    'RIVN': 'NASDAQ',
    'LCID': 'NASDAQ',
    'NIO': 'NYSE',
}


def initialize_default_mappings():
    """Initialize with default US equity symbol mappings"""
    for symbol, exchange in _US_EQUITY_SYMBOLS.items():
        register_symbol(symbol, exchange)
    logger.info(f"Initialized with {len(_US_EQUITY_SYMBOLS)} default US equity symbols")


# Auto-initialize on import
initialize_default_mappings()
