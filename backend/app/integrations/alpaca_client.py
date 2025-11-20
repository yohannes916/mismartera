"""
Alpaca Trading API Client Integration

Minimal client used initially only for connectivity testing.
"""
from typing import Optional, Dict, Any

import httpx

from app.config import settings
from app.logger import logger


class AlpacaClient:
    """Simple Alpaca client for authenticated requests.

    Initially used just to validate API connectivity.
    """

    def __init__(self) -> None:
        self.base_url = settings.ALPACA_API_BASE_URL.rstrip("/")
        self.api_key = settings.ALPACA_API_KEY_ID
        self.api_secret = settings.ALPACA_API_SECRET_KEY
        self.paper_trading = settings.ALPACA_PAPER_TRADING

        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not configured")

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.api_secret or "",
        }

    async def validate_connection(self) -> bool:
        """Validate Alpaca API connectivity using /v2/account.

        Returns True if the request succeeds with HTTP 200.
        """
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca API credentials are missing")
            return False

        url = f"{self.base_url}/v2/account"
        logger.info("Validating Alpaca API connection via /v2/account")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, headers=self._headers())
            except Exception as exc:  # network or DNS errors
                logger.error(f"Error connecting to Alpaca API: {exc}")
                return False

        if response.status_code == 200:
            logger.info("Alpaca connection validated successfully")
            return True

        logger.error(
            "Alpaca connection failed: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        return False


alpaca_client = AlpacaClient()
