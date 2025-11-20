"""Alpaca market data integration for DataManager.

Provides helpers to fetch 1-minute bars from Alpaca and map them into
our internal bar dictionary format used by MarketDataRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict

import httpx

from app.config import settings
from app.logger import logger


async def fetch_1m_bars(
    symbol: str,
    start: datetime,
    end: datetime,
) -> List[Dict]:
    """Fetch 1-minute bars for a symbol from Alpaca REST API.

    Returns a list of bar dicts with keys matching MarketDataRepository
    expectations: symbol, timestamp, interval, open, high, low, close, volume.
    """
    if not settings.ALPACA_API_KEY_ID or not settings.ALPACA_API_SECRET_KEY:
        raise RuntimeError("Alpaca API credentials are missing")

    # Use Alpaca historical data endpoint base URL
    base_url = settings.ALPACA_DATA_BASE_URL.rstrip("/")

    # Alpaca expects RFC 3339 / ISO timestamps in UTC
    def _to_alpaca_ts(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

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

    logger.info(
        "Requesting Alpaca 1m bars: symbol=%s start=%s end=%s", 
        symbol.upper(),
        params["start"],
        params["end"],
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
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

    result: List[Dict] = []
    for bar in bars:
        try:
            ts_str = bar.get("t")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            result.append(
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

    logger.info("Fetched %s 1m bars from Alpaca for %s", len(result), symbol.upper())
    return result
