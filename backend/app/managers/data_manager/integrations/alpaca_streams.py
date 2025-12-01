"""Alpaca websocket streaming helpers for DataManager.

Provides minimal abstractions to stream bars, trades (ticks), and
quotes using Alpaca's v2 market data websocket API.

These helpers are intentionally thin wrappers that take a shared
``asyncio.Event`` cancel token so higher layers (DataManager/CLI) can
cooperatively stop streams.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Iterable, List

import asyncio
import json

import websockets

from app.config import settings
from app.logger import logger


ALPACA_STREAM_BASE = "wss://stream.data.alpaca.markets/v2/iex"


@dataclass
class StreamBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StreamTick:
    symbol: str
    timestamp: datetime
    price: float
    size: float


@dataclass
class StreamQuote:
    symbol: str
    timestamp: datetime
    bid_price: float | None
    bid_size: float | None
    ask_price: float | None
    ask_size: float | None
    exchange: str | None


async def _connect() -> websockets.WebSocketClientProtocol:
    if not settings.ALPACA.api_key_id or not settings.ALPACA.api_secret_key:
        raise RuntimeError("Alpaca API credentials are missing for streaming")

    uri = ALPACA_STREAM_BASE
    logger.info("Connecting to Alpaca data stream: %s", uri)
    ws = await websockets.connect(uri, ping_interval=20, ping_timeout=20)

    auth_msg = {
        "action": "auth",
        "key": settings.ALPACA.api_key_id,
        "secret": settings.ALPACA.api_secret_key,
    }
    await ws.send(json.dumps(auth_msg))
    auth_resp = json.loads(await ws.recv())
    if not any(item.get("T") == "success" for item in auth_resp):
        raise RuntimeError(f"Alpaca stream auth failed: {auth_resp}")

    return ws


async def stream_bars(*, symbols: Iterable[str], interval: str = "1m", cancel_event: asyncio.Event) -> AsyncIterator[StreamBar]:
    """Stream real-time bars for the given symbols.

    Alpaca's stock bar stream provides 1-minute bars; the ``interval``
    parameter is currently accepted for future compatibility but must be
    "1m" for now.
    """
    if interval != "1m":
        raise NotImplementedError("Alpaca bar streaming currently supports only 1m interval")

    syms = [s.upper() for s in symbols]
    if not syms:
        return

    ws = await _connect()
    try:
        sub_msg = {"action": "subscribe", "bars": syms, "trades": [], "quotes": []}
        await ws.send(json.dumps(sub_msg))

        async for raw in ws:
            if cancel_event.is_set():
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON Alpaca stream message: %s", raw)
                continue

            # Alpaca sends a list of events per frame
            if isinstance(msg, list):
                events = msg
            else:
                events = [msg]

            for ev in events:
                if ev.get("T") != "b":  # bar
                    continue
                try:
                    ts = datetime.fromisoformat(ev["t"].replace("Z", "+00:00"))
                    yield StreamBar(
                        symbol=ev["S"],
                        timestamp=ts,
                        open=float(ev["o"]),
                        high=float(ev["h"]),
                        low=float(ev["l"]),
                        close=float(ev["c"]),
                        volume=float(ev["v"]),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error parsing Alpaca bar event %s: %s", ev, exc)
                    continue
    finally:
        await ws.close()


async def stream_ticks(*, symbols: Iterable[str], cancel_event: asyncio.Event) -> AsyncIterator[StreamTick]:
    """Stream real-time trade ticks for the given symbols."""
    syms = [s.upper() for s in symbols]
    if not syms:
        return

    ws = await _connect()
    try:
        sub_msg = {"action": "subscribe", "trades": syms, "bars": [], "quotes": []}
        await ws.send(json.dumps(sub_msg))

        async for raw in ws:
            if cancel_event.is_set():
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON Alpaca stream message: %s", raw)
                continue

            events: List[dict]
            if isinstance(msg, list):
                events = msg
            else:
                events = [msg]

            for ev in events:
                if ev.get("T") != "t":  # trade
                    continue
                try:
                    ts = datetime.fromisoformat(ev["t"].replace("Z", "+00:00"))
                    yield StreamTick(
                        symbol=ev["S"],
                        timestamp=ts,
                        price=float(ev["p"]),
                        size=float(ev.get("s", 0.0)),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error parsing Alpaca trade event %s: %s", ev, exc)
                    continue
    finally:
        await ws.close()


async def stream_quotes(*, symbols: Iterable[str], cancel_event: asyncio.Event) -> AsyncIterator[StreamQuote]:
    """Stream real-time bid/ask quotes for the given symbols."""
    syms = [s.upper() for s in symbols]
    if not syms:
        return

    ws = await _connect()
    try:
        sub_msg = {"action": "subscribe", "quotes": syms, "bars": [], "trades": []}
        await ws.send(json.dumps(sub_msg))

        async for raw in ws:
            if cancel_event.is_set():
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON Alpaca stream message: %s", raw)
                continue

            events: List[dict]
            if isinstance(msg, list):
                events = msg
            else:
                events = [msg]

            for ev in events:
                if ev.get("T") != "q":  # quote
                    continue
                try:
                    ts = datetime.fromisoformat(ev["t"].replace("Z", "+00:00"))
                    yield StreamQuote(
                        symbol=ev["S"],
                        timestamp=ts,
                        bid_price=float(ev.get("bp")) if ev.get("bp") is not None else None,
                        bid_size=float(ev.get("bs")) if ev.get("bs") is not None else None,
                        ask_price=float(ev.get("ap")) if ev.get("ap") is not None else None,
                        ask_size=float(ev.get("as")) if ev.get("as") is not None else None,
                        exchange=ev.get("x"),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error parsing Alpaca quote event %s: %s", ev, exc)
                    continue
    finally:
        await ws.close()
