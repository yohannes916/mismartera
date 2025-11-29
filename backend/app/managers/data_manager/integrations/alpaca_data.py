"""Alpaca Data Integration

Provides helpers to fetch bars (1-minute, daily), trade ticks, and bid/ask
quotes from Alpaca and map them into our internal dictionary format
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
    """Fetch 1-minute bars for a symbol from Alpaca REST API.

    Returns a list of bar dicts for Parquet storage:
    symbol, timestamp, interval, open, high, low, close, volume.
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")

    # Use Alpaca historical data endpoint base URL
    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")

    # Alpaca expects RFC 3339 / ISO timestamps
    def _to_alpaca_ts(dt: datetime) -> str:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return dt.isoformat()

    params = {
        "timeframe": "1Min",
        "start": _to_alpaca_ts(start),
        "end": _to_alpaca_ts(end),
        "adjustment": "raw",
        "limit": 10000,
    }

    url = f"{base_url}/v2/stocks/{symbol.upper()}/bars"

    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }

    all_bars: List[Dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 0
        next_page_token: str | None = None

        while True:
            page += 1
            if next_page_token:
                params["page_token"] = next_page_token
            else:
                params.pop("page_token", None)

            logger.info(
                f"[Alpaca] Requesting 1m bars for {symbol.upper()} (page {page}, total fetched: {len(all_bars)}) | Range: {params['start']} to {params['end']}"
            )

            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code != 200:
                logger.error(
                    "Alpaca bars request failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise RuntimeError(
                    f"Alpaca bars request failed: {resp.status_code} {resp.text[:200]}"
                )

            data = resp.json()
            bars = data.get("bars", [])
            bars_in_page = len(bars)
            
            logger.info(
                f"[Alpaca] Received {bars_in_page} bars in page {page} for {symbol.upper()}"
            )

            for bar in bars:
                try:
                    ts_str = bar.get("t")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    all_bars.append(
                        {
                            "symbol": symbol.upper(),
                            "timestamp": ts,
                            "interval": "1m",
                            "open": float(bar["o"]),
                            "high": float(bar["h"]),
                            "low": float(bar["l"]),
                            "close": float(bar["c"]),
                            "volume": float(bar["v"]),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed Alpaca bar: %s (error=%s)", bar, exc)
                    continue

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                logger.info(
                    f"[Alpaca] ✓ Completed pagination for {symbol.upper()} (total: {len(all_bars)} bars from {page} pages)"
                )
                break
            else:
                logger.info(
                    f"[Alpaca] → More data available, fetching next page for {symbol.upper()}..."
                )

    logger.info(f"[Alpaca] ✓ Final: Fetched {len(all_bars)} 1m bars from Alpaca for {symbol.upper()}")
    return all_bars


async def fetch_1d_bars(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch daily bars for a symbol from Alpaca REST API.

    Returns a list of bar dicts for Parquet storage:
    symbol, timestamp, interval, open, high, low, close, volume.
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")

    # Use Alpaca historical data endpoint base URL
    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")

    # Alpaca expects RFC 3339 / ISO timestamps
    def _to_alpaca_ts(dt: datetime) -> str:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return dt.isoformat()

    params = {
        "timeframe": "1Day",
        "start": _to_alpaca_ts(start),
        "end": _to_alpaca_ts(end),
        "adjustment": "raw",
        "limit": 10000,
    }

    url = f"{base_url}/v2/stocks/{symbol.upper()}/bars"

    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }

    all_bars: List[Dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 0
        next_page_token: str | None = None

        while True:
            page += 1
            if next_page_token:
                params["page_token"] = next_page_token
            else:
                params.pop("page_token", None)

            logger.info(
                f"[Alpaca] Requesting daily bars for {symbol.upper()} (page {page}, total fetched: {len(all_bars)}) | Range: {params['start']} to {params['end']}"
            )

            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code != 200:
                logger.error(
                    "Alpaca daily bars request failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise RuntimeError(
                    f"Alpaca daily bars request failed: {resp.status_code} {resp.text[:200]}"
                )

            data = resp.json()
            bars = data.get("bars", [])
            bars_in_page = len(bars)
            
            logger.info(
                f"[Alpaca] Received {bars_in_page} daily bars in page {page} for {symbol.upper()}"
            )

            for bar in bars:
                try:
                    ts_str = bar.get("t")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    all_bars.append(
                        {
                            "symbol": symbol.upper(),
                            "timestamp": ts,
                            "interval": "1d",
                            "open": float(bar["o"]),
                            "high": float(bar["h"]),
                            "low": float(bar["l"]),
                            "close": float(bar["c"]),
                            "volume": float(bar["v"]),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed Alpaca daily bar: %s (error=%s)", bar, exc)
                    continue

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                logger.info(
                    f"[Alpaca] ✓ Completed pagination for {symbol.upper()} daily bars (total: {len(all_bars)} bars from {page} pages)"
                )
                break
            else:
                logger.info(
                    f"[Alpaca] → More daily data available, fetching next page for {symbol.upper()}..."
                )

    logger.info(f"[Alpaca] ✓ Final: Fetched {len(all_bars)} daily bars from Alpaca for {symbol.upper()}")
    return all_bars


async def fetch_ticks(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch trade ticks for a symbol from Alpaca REST API.

    We map each trade tick into a MarketData-compatible dict using
    ``interval='tick'`` and setting open/high/low/close to the trade
    price, and volume to the trade size.
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")

    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")

    def _to_alpaca_ts(dt: datetime) -> str:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return dt.isoformat()

    params = {
        "start": _to_alpaca_ts(start),
        "end": _to_alpaca_ts(end),
        "limit": 10000,
    }

    url = f"{base_url}/v2/stocks/{symbol.upper()}/trades"

    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }

    ticks: List[Dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 0
        next_page_token: str | None = None

        while True:
            page += 1
            if next_page_token:
                params["page_token"] = next_page_token
            else:
                params.pop("page_token", None)

            logger.debug(
                f"[Alpaca] Requesting ticks for {symbol.upper()} (page {page}, total fetched: {len(ticks)}) | Range: {params['start']} to {params['end']}"
            )

            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code != 200:
                logger.error(
                    "Alpaca ticks request failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise RuntimeError(
                    f"Alpaca ticks request failed: {resp.status_code} {resp.text[:200]}"
                )

            data = resp.json()
            trades = data.get("trades", [])
            trades_in_page = len(trades)
            
            logger.debug(
                f"[Alpaca] Received {trades_in_page} ticks in page {page} for {symbol.upper()}"
            )

            for trade in trades:
                try:
                    ts_str = trade.get("t")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    price = float(trade["p"])
                    size = float(trade.get("s", 0))
                    ticks.append(
                        {
                            "symbol": symbol.upper(),
                            "timestamp": ts,
                            "interval": "tick",
                            "open": price,
                            "high": price,
                            "low": price,
                            "close": price,
                            "volume": size,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed Alpaca tick: %s (error=%s)", trade, exc)
                    continue

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                logger.info(
                    f"[Alpaca] ✓ Completed pagination for {symbol.upper()} ticks (total: {len(ticks)} ticks from {page} pages)"
                )
                break
            else:
                logger.debug(
                    f"[Alpaca] → More tick data available, fetching next page for {symbol.upper()}..."
                )

    logger.info(f"[Alpaca] ✓ Final: Fetched {len(ticks)} ticks from Alpaca for {symbol.upper()}")
    return ticks


async def fetch_quotes(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch historical bid/ask quotes for a symbol from Alpaca REST API.

    Returns a list of dicts for Parquet storage
    with keys: symbol, timestamp, bid_price, bid_size, ask_price, ask_size,
    exchange.
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")

    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")

    def _to_alpaca_ts(dt: datetime) -> str:
        if dt.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return dt.isoformat()

    params = {
        "start": _to_alpaca_ts(start),
        "end": _to_alpaca_ts(end),
        "limit": 10000,
    }

    url = f"{base_url}/v2/stocks/{symbol.upper()}/quotes"

    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }

    quotes: List[Dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 0
        next_page_token: str | None = None

        while True:
            page += 1
            if next_page_token:
                params["page_token"] = next_page_token
            else:
                params.pop("page_token", None)

            logger.info(
                f"[Alpaca] Requesting quotes for {symbol.upper()} (page {page}, total fetched: {len(quotes)}) | Range: {params['start']} to {params['end']}"
            )

            resp = await client.get(url, headers=headers, params=params)

            if resp.status_code != 200:
                logger.error(
                    "Alpaca quotes request failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise RuntimeError(
                    f"Alpaca quotes request failed: {resp.status_code} {resp.text[:200]}"
                )

            data = resp.json()
            quote_items = data.get("quotes") or []
            quotes_in_page = len(quote_items)
            
            logger.info(
                f"[Alpaca] Received {quotes_in_page} quotes in page {page} for {symbol.upper()}"
            )

            for q in quote_items:
                try:
                    ts_str = q.get("t")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    quotes.append(
                        {
                            "symbol": symbol.upper(),
                            "timestamp": ts,
                            "bid_price": float(q.get("bp")) if q.get("bp") is not None else None,
                            "bid_size": float(q.get("bs")) if q.get("bs") is not None else None,
                            "ask_price": float(q.get("ap")) if q.get("ap") is not None else None,
                            "ask_size": float(q.get("as")) if q.get("as") is not None else None,
                            "exchange": q.get("x"),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping malformed Alpaca quote: %s (error=%s)", q, exc)
                    continue

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                logger.info(
                    f"[Alpaca] ✓ Completed pagination for {symbol.upper()} quotes (total: {len(quotes)} quotes from {page} pages)"
                )
                break
            else:
                logger.info(
                    f"[Alpaca] → More quote data available, fetching next page for {symbol.upper()}..."
                )

    logger.info(f"[Alpaca] ✓ Final: Fetched {len(quotes)} quotes from Alpaca for {symbol.upper()}")
    return quotes


async def fetch_snapshot(symbol: str) -> Optional[Dict]:
    """Fetch latest snapshot for a symbol from Alpaca REST API.
    
    Snapshot includes:
    - Latest trade
    - Latest quote (bid/ask)
    - Latest minute bar
    - Latest daily bar
    - Previous daily bar
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Dict with snapshot data or None if failed
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")
    
    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")
    url = f"{base_url}/v2/stocks/{symbol.upper()}/snapshot"
    
    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            
            # Parse the snapshot data
            snapshot = {
                "symbol": symbol.upper(),
                "latest_trade": None,
                "latest_quote": None,
                "minute_bar": None,
                "daily_bar": None,
                "prev_daily_bar": None,
            }
            
            # Latest trade
            if "latestTrade" in data and data["latestTrade"]:
                t = data["latestTrade"]
                snapshot["latest_trade"] = {
                    "price": float(t.get("p", 0)),
                    "size": int(t.get("s", 0)),
                    "timestamp": datetime.fromisoformat(t["t"].replace("Z", "+00:00")) if "t" in t else None,
                }
            
            # Latest quote
            if "latestQuote" in data and data["latestQuote"]:
                q = data["latestQuote"]
                snapshot["latest_quote"] = {
                    "bid_price": float(q.get("bp", 0)),
                    "bid_size": int(q.get("bs", 0)),
                    "ask_price": float(q.get("ap", 0)),
                    "ask_size": int(q.get("as", 0)),
                    "timestamp": datetime.fromisoformat(q["t"].replace("Z", "+00:00")) if "t" in q else None,
                }
            
            # Minute bar
            if "minuteBar" in data and data["minuteBar"]:
                m = data["minuteBar"]
                snapshot["minute_bar"] = {
                    "open": float(m.get("o", 0)),
                    "high": float(m.get("h", 0)),
                    "low": float(m.get("l", 0)),
                    "close": float(m.get("c", 0)),
                    "volume": int(m.get("v", 0)),
                    "timestamp": datetime.fromisoformat(m["t"].replace("Z", "+00:00")) if "t" in m else None,
                }
            
            # Daily bar
            if "dailyBar" in data and data["dailyBar"]:
                d = data["dailyBar"]
                snapshot["daily_bar"] = {
                    "open": float(d.get("o", 0)),
                    "high": float(d.get("h", 0)),
                    "low": float(d.get("l", 0)),
                    "close": float(d.get("c", 0)),
                    "volume": int(d.get("v", 0)),
                    "timestamp": datetime.fromisoformat(d["t"].replace("Z", "+00:00")) if "t" in d else None,
                }
            
            # Previous daily bar
            if "prevDailyBar" in data and data["prevDailyBar"]:
                p = data["prevDailyBar"]
                snapshot["prev_daily_bar"] = {
                    "open": float(p.get("o", 0)),
                    "high": float(p.get("h", 0)),
                    "low": float(p.get("l", 0)),
                    "close": float(p.get("c", 0)),
                    "volume": int(p.get("v", 0)),
                    "timestamp": datetime.fromisoformat(p["t"].replace("Z", "+00:00")) if "t" in p else None,
                }
            
            logger.info(f"Fetched snapshot for {symbol.upper()}")
            return snapshot
            
        except httpx.HTTPStatusError as exc:
            logger.error(f"Alpaca snapshot HTTP error for {symbol}: {exc.response.status_code}")
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to fetch Alpaca snapshot for {symbol}: {exc}")
            return None


async def fetch_session_data(symbol: str, session_date: date) -> Optional[Dict]:
    """Fetch session high/low/volume using Alpaca's daily bar endpoint.
    
    This is more reliable than snapshot for getting complete session data
    as it returns the full day's aggregated OHLCV data.
    
    Args:
        symbol: Stock symbol
        session_date: Trading date to fetch
        
    Returns:
        Dict with session data (high, low, volume, open, close) or None if failed
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")
    
    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")
    url = f"{base_url}/v2/stocks/{symbol.upper()}/bars"
    
    # Request daily bar for specific session
    # Get system timezone from SystemManager
    from app.managers.system_manager import get_system_manager
    from zoneinfo import ZoneInfo
    system_mgr = get_system_manager()
    system_tz = ZoneInfo(system_mgr.timezone)
    
    start_dt = datetime.combine(session_date, time.min, tzinfo=system_tz)
    end_dt = datetime.combine(session_date, time.max, tzinfo=system_tz)
    
    params = {
        "timeframe": "1Day",
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "limit": 1,
    }
    
    headers = {
        "APCA-API-KEY-ID": settings.ALPACA_API_KEY_ID,
        "APCA-API-SECRET-KEY": settings.ALPACA_API_SECRET_KEY,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            
            if "bars" not in data or not data["bars"]:
                logger.warning(f"No session data returned from Alpaca for {symbol} on {session_date}")
                return None
            
            bars = data["bars"]
            if not bars:
                return None
            
            bar = bars[0]
            
            session_data = {
                "symbol": symbol.upper(),
                "session_date": session_date,
                "open": float(bar.get("o", 0)),
                "high": float(bar.get("h", 0)),
                "low": float(bar.get("l", 0)),
                "close": float(bar.get("c", 0)),
                "volume": int(bar.get("v", 0)),
                "timestamp": datetime.fromisoformat(bar["t"].replace("Z", "+00:00")) if "t" in bar else None,
            }
            
            logger.info(f"Fetched session data for {symbol} on {session_date}")
            return session_data
            
        except httpx.HTTPStatusError as exc:
            logger.error(f"Alpaca session data HTTP error for {symbol}: {exc.response.status_code}")
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to fetch Alpaca session data for {symbol}: {exc}")
            return None
