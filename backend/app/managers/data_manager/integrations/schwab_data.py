"""Schwab Data Integration

Provides helpers to fetch bars (1-minute, daily), trade ticks, and bid/ask
quotes from Schwab and map them into our internal dictionary format
for storage in Parquet files.
"""
from __future__ import annotations

from datetime import datetime, timezone, date, time
from typing import List, Dict, Optional

import httpx

from app.config import settings
from app.logger import logger


async def fetch_1m_bars(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch 1-minute bars for a symbol from Schwab REST API.

    Returns a list of bar dicts for Parquet storage:
    symbol, timestamp, interval, open, high, low, close, volume.
    
    Note: Schwab uses OAuth 2.0. This requires a valid access token obtained
    through the OAuth authorization flow. Currently this is not fully implemented.
    """
    if not settings.SCHWAB_APP_KEY or not settings.SCHWAB_APP_SECRET:
        raise RuntimeError("Schwab API credentials are missing")
    
    # Get valid OAuth access token
    from app.integrations.schwab_client import schwab_client
    try:
        access_token = await schwab_client.get_valid_access_token()
    except RuntimeError as e:
        raise RuntimeError(
            f"{str(e)}\n\n"
            "To authorize Schwab:\n"
            "  1. Run 'schwab auth-start' to begin OAuth flow\n"
            "  2. Authorize via browser\n"
            "  3. Complete callback with authorization code\n"
            "  4. Try import again"
        ) from e

    # Use Schwab historical data endpoint base URL
    base_url = settings.SCHWAB_API_BASE_URL.rstrip("/")

    # Schwab expects Unix timestamps in SECONDS (not milliseconds!)
    def _to_schwab_ts(dt: datetime) -> int:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        # timestamp() handles timezone conversion automatically
        return int(dt.timestamp())

    # Schwab limitation: minute data only available for max 10 days per request
    # Need to chunk large date ranges into 10-day segments
    from datetime import timedelta
    
    MAX_DAYS_PER_REQUEST = 10
    all_bars: List[Dict] = []
    
    # Headers for GET request - do NOT include Content-Type for GET requests
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    
    # Symbol is a query parameter, not in the URL path
    url = f"{base_url}/marketdata/v1/pricehistory"
    
    current_start = start
    chunk_num = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_start <= end:
            chunk_num += 1
            
            # Calculate chunk size (max 10 days)
            chunk_end = min(current_start + timedelta(days=MAX_DAYS_PER_REQUEST), end)
            days_in_chunk = (chunk_end - current_start).days
            
            # Cap period at valid values for periodType="day": 1,2,3,4,5,10
            if days_in_chunk <= 1:
                period = 1
            elif days_in_chunk <= 2:
                period = 2
            elif days_in_chunk <= 3:
                period = 3
            elif days_in_chunk <= 4:
                period = 4
            elif days_in_chunk <= 5:
                period = 5
            else:
                period = 10
            
            # Build parameters matching Schwab API examples
            # Schwab requires: periodType, period, startDate, AND endDate
            params = {
                "symbol": symbol.upper(),
                "periodType": "day",
                "period": period,
                "frequencyType": "minute",
                "frequency": 1,
                "startDate": _to_schwab_ts(current_start),
                "endDate": _to_schwab_ts(chunk_end),
                "needExtendedHoursData": "false",
                "needPreviousClose": "false",
            }

            logger.info(
                "Requesting Schwab 1m bars (chunk %d): symbol=%s start=%s end=%s",
                chunk_num,
                symbol.upper(),
                current_start.date(),
                chunk_end.date(),
            )
            
            # Build full request URL for debugging
            from urllib.parse import urlencode
            query_string = urlencode(params)
            full_url = f"{url}?{query_string}"
            
            logger.info(f"Full GET request: {full_url}")
            logger.info(f"Authorization header: Bearer {access_token[:20]}...")
            logger.debug(f"Full headers: {headers}")

            resp = await client.get(url, headers=headers, params=params)
            
            logger.info(f"Response status: {resp.status_code}")
            logger.info(f"Response content-type: {resp.headers.get('content-type')}")

            if resp.status_code != 200:
                # Try to parse error as JSON, otherwise use raw text
                raw_content = resp.content
                text_content = resp.text
                
                logger.error(f"Schwab API Error {resp.status_code}")
                logger.error(f"URL: {url}")
                logger.error(f"Params: {params}")
                logger.error(f"Response raw bytes ({len(raw_content)} bytes): {raw_content}")
                logger.error(f"Response text: '{text_content}'")
                logger.error(f"Response headers: {dict(resp.headers)}")
                
                try:
                    error_json = resp.json()
                    error_detail = str(error_json)
                except Exception as json_err:
                    logger.error(f"Failed to parse JSON: {json_err}")
                    error_detail = text_content if text_content else "(empty response)"
                
                # Create helpful error message
                if resp.status_code == 400:
                    error_msg = (
                        f"Schwab API returned 400 Bad Request.\n"
                        f"Response: {error_detail}\n\n"
                        f"Possible issues:\n"
                        f"  - Invalid symbol: {symbol}\n"
                        f"  - Invalid date range (future dates or too far back)\n"
                        f"  - Invalid parameters\n"
                        f"  - Symbol not supported by Schwab\n"
                    )
                elif resp.status_code == 401:
                    error_msg = "Authentication failed. Try: schwab auth-start"
                else:
                    error_msg = f"Schwab API Error {resp.status_code}: {error_detail}"
                
                raise RuntimeError(error_msg)

            data = resp.json()
            
            # Log what we got back
            logger.info(f"Chunk {chunk_num}: Schwab response keys: {list(data.keys())}")
            logger.info(f"Chunk {chunk_num}: empty={data.get('empty')}, symbol={data.get('symbol')}")
            
            candles = data.get("candles", [])
            logger.info(f"Chunk {chunk_num}: Received {len(candles)} bars")

            for candle in candles:
                try:
                    # Schwab returns Unix timestamp in milliseconds
                    # Get system timezone from SystemManager
                    from app.managers.system_manager import get_system_manager
                    from zoneinfo import ZoneInfo
                    system_mgr = get_system_manager()
                    system_tz = ZoneInfo(system_mgr.timezone)
                    
                    ts_ms = candle.get("datetime")
                    ts = datetime.fromtimestamp(ts_ms / 1000, tz=system_tz)
                    
                    all_bars.append(
                        {
                            "symbol": symbol.upper(),
                            "timestamp": ts,
                            "interval": "1m",
                            "open": float(candle.get("open", 0.0)),
                            "high": float(candle.get("high", 0.0)),
                            "low": float(candle.get("low", 0.0)),
                            "close": float(candle.get("close", 0.0)),
                            "volume": int(candle.get("volume", 0)),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error parsing Schwab bar: {e}")
                    continue
            
            # Move to next chunk
            current_start = chunk_end + timedelta(days=1)

    logger.info(
        f"Schwab returned {len(all_bars)} total 1m bars for {symbol.upper()} ({chunk_num} chunks)"
    )

    return all_bars


async def fetch_1d_bars(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch daily bars for a symbol from Schwab REST API.

    Returns a list of bar dicts for Parquet storage:
    symbol, timestamp, interval, open, high, low, close, volume.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start: Start datetime (interpreted as Eastern Time)
        end: End datetime (interpreted as Eastern Time)
        
    Returns:
        List of bar dictionaries
        
    Raises:
        RuntimeError: If authentication fails or API request fails
    """
    from app.integrations.schwab_client import schwab_client

    try:
        access_token = await schwab_client.get_valid_access_token()
    except RuntimeError as e:
        raise RuntimeError(
            f"{str(e)}\n\n"
            "To authorize Schwab:\n"
            "  1. Run 'schwab auth-start' to begin OAuth flow\n"
            "  2. Authorize via browser\n"
            "  3. Complete callback with authorization code\n"
            "  4. Try import again"
        ) from e

    # Use Schwab historical data endpoint base URL
    base_url = settings.SCHWAB_API_BASE_URL.rstrip("/")

    # Schwab expects Unix timestamps in SECONDS (not milliseconds!)
    def _to_schwab_ts(dt: datetime) -> int:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        # timestamp() handles timezone conversion automatically
        return int(dt.timestamp())

    # For daily bars, we need periodType=month or year (NOT day)
    # Schwab API: periodType=day only supports frequencyType=minute
    days_diff = (end - start).days
    
    # Use appropriate periodType based on range
    # Note: For daily frequency, use month/year periodType
    if days_diff <= 31:  # ~1 month
        period_type = "month"
        period = 1
    elif days_diff <= 186:  # ~6 months
        period_type = "month"
        period = min((days_diff // 30) + 1, 6)
    elif days_diff <= 730:  # ~2 years
        period_type = "year"
        period = min((days_diff // 365) + 1, 2)
    else:
        period_type = "year"
        period = min((days_diff // 365) + 1, 20)
    
    all_bars: List[Dict] = []
    
    # Headers for GET request - do NOT include Content-Type for GET requests
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    
    # Symbol is a query parameter, not in the URL path
    url = f"{base_url}/marketdata/v1/pricehistory"
    
    # Build parameters for daily bars
    params = {
        "symbol": symbol.upper(),
        "periodType": period_type,
        "period": period,
        "frequencyType": "daily",
        "frequency": 1,
        "startDate": _to_schwab_ts(start),
        "endDate": _to_schwab_ts(end),
        "needExtendedHoursData": "false",
        "needPreviousClose": "false",
    }

    logger.info(
        "Requesting Schwab daily bars: symbol=%s start=%s end=%s (period=%s %s)",
        symbol.upper(),
        start.date(),
        end.date(),
        period,
        period_type,
    )
    
    # Build full request URL for debugging
    from urllib.parse import urlencode
    query_string = urlencode(params)
    full_url = f"{url}?{query_string}"
    
    logger.info(f"Full GET request: {full_url}")
    logger.info(f"Authorization header: Bearer {access_token[:20]}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        
        logger.info(f"Response status: {resp.status_code}")
        logger.info(f"Response content-type: {resp.headers.get('content-type')}")

        if resp.status_code != 200:
            # Try to parse error as JSON, otherwise use raw text
            raw_content = resp.content
            text_content = resp.text
            
            logger.error(f"Schwab API Error {resp.status_code}")
            logger.error(f"URL: {url}")
            logger.error(f"Params: {params}")
            logger.error(f"Response raw bytes ({len(raw_content)} bytes): {raw_content}")
            logger.error(f"Response text: '{text_content}'")
            logger.error(f"Response headers: {dict(resp.headers)}")
            
            try:
                error_json = resp.json()
                error_detail = str(error_json)
            except Exception as json_err:
                logger.error(f"Failed to parse JSON: {json_err}")
                error_detail = text_content if text_content else "(empty response)"
            
            # Create helpful error message
            if resp.status_code == 400:
                error_msg = (
                    f"Schwab API returned 400 Bad Request.\n"
                    f"Response: {error_detail}\n\n"
                    f"Possible issues:\n"
                    f"  - Invalid symbol: {symbol}\n"
                    f"  - Invalid date range (future dates or too far back)\n"
                    f"  - Invalid parameters\n"
                    f"  - Symbol not supported by Schwab\n"
                )
            elif resp.status_code == 401:
                error_msg = "Authentication failed. Try: schwab auth-start"
            else:
                error_msg = f"Schwab API Error {resp.status_code}: {error_detail}"
            
            raise RuntimeError(error_msg)

        data = resp.json()
        
        # Log what we got back
        logger.info(f"Schwab response keys: {list(data.keys())}")
        logger.info(f"empty={data.get('empty')}, symbol={data.get('symbol')}")
        
        candles = data.get("candles", [])
        logger.info(f"Received {len(candles)} daily bars")

        for candle in candles:
            try:
                # Schwab returns Unix timestamp in milliseconds
                # Get system timezone from SystemManager
                from app.managers.system_manager import get_system_manager
                from zoneinfo import ZoneInfo
                system_mgr = get_system_manager()
                system_tz = ZoneInfo(system_mgr.timezone)
                
                ts_ms = candle.get("datetime")
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=system_tz)
                
                all_bars.append(
                    {
                        "symbol": symbol.upper(),
                        "timestamp": ts,
                        "interval": "1d",
                        "open": float(candle.get("open", 0.0)),
                        "high": float(candle.get("high", 0.0)),
                        "low": float(candle.get("low", 0.0)),
                        "close": float(candle.get("close", 0.0)),
                        "volume": int(candle.get("volume", 0)),
                    }
                )
            except Exception as e:
                logger.warning(f"Error parsing Schwab daily bar: {e}")
                continue

    logger.info(
        f"Schwab returned {len(all_bars)} daily bars for {symbol.upper()}"
    )

    return all_bars


async def fetch_ticks(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch trade ticks for a symbol from Schwab REST API.

    Note: Schwab API does not provide historical tick/trade data.
    Schwab only provides OHLCV bars at various intervals (1m, 5m, etc).
    
    For tick-level data, use Alpaca API instead.
    This function returns an error to inform users.
    
    Returns:
        Empty list (not implemented)
    """
    logger.error(
        "Schwab API does not provide historical tick/trade data. "
        "Only bar data (1m, 5m, daily, etc) is available from Schwab. "
        "For tick-level data, use Alpaca: 'data api alpaca'"
    )
    
    raise NotImplementedError(
        "Schwab does not provide historical tick/trade data.\n"
        "Available from Schwab: 1m bars, 5m bars, daily bars, etc.\n"
        "For tick data, use: data api alpaca"
    )


async def fetch_quotes(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch bid/ask quotes for a symbol from Schwab REST API.

    Note: Schwab API does not provide historical bid/ask quote data.
    Schwab only provides real-time quotes via streaming and OHLCV bars.
    
    For historical quote data, use Alpaca API instead.
    
    Returns:
        Empty list (not implemented)
    """
    logger.error(
        "Schwab API does not provide historical bid/ask quote data. "
        "Only bar data and real-time streaming quotes are available. "
        "For historical quotes, use Alpaca: 'data api alpaca'"
    )
    
    raise NotImplementedError(
        "Schwab does not provide historical quote data.\n"
        "Available from Schwab: 1m bars, 5m bars, daily bars, real-time streaming\n"
        "For historical quotes, use: data api alpaca"
    )


async def get_latest_quote(symbol: str) -> Optional[Dict]:
    """Get the latest real-time quote for a symbol from Schwab.

    Returns a quote dict with: symbol, bid_price, bid_size, ask_price, ask_size, last_price.
    """
    if not settings.SCHWAB_APP_KEY or not settings.SCHWAB_APP_SECRET:
        raise RuntimeError("Schwab API credentials are missing")

    # Get valid OAuth access token
    from app.integrations.schwab_client import schwab_client
    try:
        access_token = await schwab_client.get_valid_access_token()
    except RuntimeError as e:
        raise RuntimeError(
            f"{str(e)}\n\n"
            "To authorize Schwab, run 'schwab auth-start'"
        ) from e

    base_url = settings.SCHWAB_API_BASE_URL.rstrip("/")
    url = f"{base_url}/marketdata/v1/quotes"

    # Headers for GET request - do NOT include Content-Type for GET requests
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    params = {
        "symbols": symbol.upper(),
        "fields": "quote,fundamental",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        logger.info(f"Requesting Schwab real-time quote for {symbol.upper()}")

        resp = await client.get(url, headers=headers, params=params)

        if resp.status_code != 200:
            logger.error(
                "Schwab quote request failed: status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            return None

        data = resp.json()
        
        # Schwab returns quotes keyed by symbol
        quote_data = data.get(symbol.upper(), {})
        quote = quote_data.get("quote", {})
        
        if not quote:
            logger.warning(f"No quote data returned for {symbol.upper()}")
            return None

        return {
            "symbol": symbol.upper(),
            "bid_price": float(quote.get("bidPrice", 0.0)),
            "bid_size": int(quote.get("bidSize", 0)),
            "ask_price": float(quote.get("askPrice", 0.0)),
            "ask_size": int(quote.get("askSize", 0)),
            "last_price": float(quote.get("lastPrice", 0.0)),
            "last_size": int(quote.get("lastSize", 0)),
            "volume": int(quote.get("totalVolume", 0)),
        }
