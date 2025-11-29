"""
Exchange Groups for Holiday Management
Defines which exchanges share holiday calendars
"""
from typing import Dict, List, Set


# Exchange groups that share the same holiday calendar
EXCHANGE_GROUPS: Dict[str, List[str]] = {
    # US Equity Markets (NYSE rules - SEC-mandated holidays)
    "US_EQUITY": [
        "NYSE",        # New York Stock Exchange
        "NASDAQ",      # NASDAQ Stock Market
        "AMEX",        # NYSE American (formerly American Stock Exchange)
        "NYSE_ARCA",   # NYSE Arca (options and ETFs platform)
    ],
    
    # US Options Markets (follow equity market closures but may have different hours)
    "US_OPTIONS": [
        "CBOE",        # Chicago Board Options Exchange
        "ISE",         # International Securities Exchange
        "PHLX",        # NASDAQ PHLX (Philadelphia Stock Exchange)
    ],
    
    # US Futures Markets (CME Group - different holiday schedule)
    "US_FUTURES": [
        "CME",         # Chicago Mercantile Exchange
        "CBOT",        # Chicago Board of Trade
        "NYMEX",       # New York Mercantile Exchange
        "COMEX",       # Commodity Exchange
    ],
    
    # UK Equity Markets
    "UK_EQUITY": [
        "LSE",         # London Stock Exchange
        "AIM",         # Alternative Investment Market
    ],
    
    # Japanese Equity Markets
    "JP_EQUITY": [
        "TSE",         # Tokyo Stock Exchange
        "JPX",         # Japan Exchange Group
    ],
    
    # European Markets (can be expanded)
    "EU_EQUITY": [
        "XETRA",       # Deutsche Börse (Frankfurt)
        "EURONEXT",    # Euronext (Paris, Amsterdam, Brussels)
    ],
}


# Reverse mapping: Exchange -> Group
EXCHANGE_TO_GROUP: Dict[str, str] = {}
for group, exchanges in EXCHANGE_GROUPS.items():
    for exchange in exchanges:
        EXCHANGE_TO_GROUP[exchange] = group


def get_exchanges_in_group(group: str) -> List[str]:
    """Get all exchanges in a group
    
    Args:
        group: Group name (e.g., "US_EQUITY")
        
    Returns:
        List of exchange codes in the group
        
    Examples:
        >>> get_exchanges_in_group("US_EQUITY")
        ['NYSE', 'NASDAQ', 'AMEX', 'NYSE_ARCA']
    """
    return EXCHANGE_GROUPS.get(group, [])


def get_group_for_exchange(exchange: str) -> str:
    """Get the group an exchange belongs to
    
    Args:
        exchange: Exchange code (e.g., "NYSE")
        
    Returns:
        Group name, or the exchange itself if not in a group
        
    Examples:
        >>> get_group_for_exchange("NYSE")
        'US_EQUITY'
    """
    return EXCHANGE_TO_GROUP.get(exchange, exchange)


def get_all_exchanges_for_import(exchange_or_group: str) -> Set[str]:
    """Get all exchanges that should receive holidays
    
    This is the key function for imports - it expands a group name
    to all exchanges in that group, or returns a single exchange.
    
    Args:
        exchange_or_group: Either a group name (US_EQUITY) or exchange (NYSE)
        
    Returns:
        Set of exchange codes
        
    Examples:
        >>> get_all_exchanges_for_import("US_EQUITY")
        {'NYSE', 'NASDAQ', 'AMEX', 'NYSE_ARCA'}
        
        >>> get_all_exchanges_for_import("NYSE")
        {'NYSE'}
    """
    if exchange_or_group in EXCHANGE_GROUPS:
        # It's a group - return all exchanges in group
        return set(EXCHANGE_GROUPS[exchange_or_group])
    else:
        # It's a single exchange
        return {exchange_or_group}


def is_valid_group(group: str) -> bool:
    """Check if a string is a valid exchange group
    
    Args:
        group: Group name to check
        
    Returns:
        True if valid group
    """
    return group in EXCHANGE_GROUPS


def is_valid_exchange(exchange: str) -> bool:
    """Check if a string is a known exchange
    
    Args:
        exchange: Exchange code to check
        
    Returns:
        True if known exchange
    """
    return exchange in EXCHANGE_TO_GROUP


def list_all_groups() -> List[str]:
    """List all available exchange groups
    
    Returns:
        List of group names
    """
    return list(EXCHANGE_GROUPS.keys())


def list_all_exchanges() -> List[str]:
    """List all known exchanges
    
    Returns:
        List of exchange codes
    """
    return list(EXCHANGE_TO_GROUP.keys())


def get_group_info(group: str) -> Dict[str, any]:
    """Get detailed information about an exchange group
    
    Args:
        group: Group name
        
    Returns:
        Dict with group info (exchanges, count, etc.)
    """
    exchanges = EXCHANGE_GROUPS.get(group, [])
    return {
        "group": group,
        "exchanges": exchanges,
        "count": len(exchanges),
        "valid": group in EXCHANGE_GROUPS
    }


# Metadata about each group (optional - for display purposes)
GROUP_METADATA: Dict[str, Dict[str, str]] = {
    "US_EQUITY": {
        "name": "US Equity Markets",
        "country": "USA",
        "timezone": "America/New_York",
        "description": "NYSE, NASDAQ, and related US equity exchanges",
    },
    "US_OPTIONS": {
        "name": "US Options Markets",
        "country": "USA",
        "timezone": "America/New_York",
        "description": "US options exchanges (CBOE, ISE, PHLX)",
    },
    "US_FUTURES": {
        "name": "US Futures Markets",
        "country": "USA",
        "timezone": "America/Chicago",
        "description": "CME Group exchanges (CME, CBOT, NYMEX, COMEX)",
    },
    "UK_EQUITY": {
        "name": "UK Equity Markets",
        "country": "UK",
        "timezone": "Europe/London",
        "description": "London Stock Exchange and AIM",
    },
    "JP_EQUITY": {
        "name": "Japanese Equity Markets",
        "country": "Japan",
        "timezone": "Asia/Tokyo",
        "description": "Tokyo Stock Exchange and Japan Exchange Group",
    },
    "EU_EQUITY": {
        "name": "European Equity Markets",
        "country": "EU",
        "timezone": "Europe/Paris",
        "description": "Major European exchanges (Xetra, Euronext)",
    },
}


def get_group_metadata(group: str) -> Dict[str, str]:
    """Get metadata for an exchange group
    
    Args:
        group: Group name
        
    Returns:
        Dict with metadata (name, country, timezone, description)
    """
    return GROUP_METADATA.get(group, {
        "name": group,
        "country": "Unknown",
        "timezone": "UTC",
        "description": f"Exchange group: {group}"
    })
