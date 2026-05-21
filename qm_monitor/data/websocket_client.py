from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from qm_monitor.config import settings
from qm_monitor.models.market import Level1Snapshot, Level2Snapshot, OrderEvent, QuoteLevel, TickTrade

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], None]


def parse_market_message(raw: dict) -> Optional[Level1Snapshot | Level2Snapshot | TickTrade | OrderEvent]:
    msg_type = raw.get("type")
    symbol = raw.get("symbol", "")
    ts_ms = int(raw.get("ts_ms", 0))

    if msg_type == "l1":
        return Level1Snapshot(
            symbol=symbol,
            ts_ms=ts_ms,
            last_price=float(raw["last_price"]),
            last_volume=int(raw.get("last_volume", 0)),
            bid1=QuoteLevel(float(raw["bid1_price"]), int(raw["bid1_volume"])),
            ask1=QuoteLevel(float(raw["ask1_price"]), int(raw["ask1_volume"])),
            total_volume=int(raw.get("total_volume", 0)),
            total_turnover=float(raw.get("total_turnover", 0)),
        )
    if msg_type == "l2":
        return Level2Snapshot(
            symbol=symbol,
            ts_ms=ts_ms,
            last_price=float(raw["last_price"]),
            bids=[QuoteLevel(float(p), int(v)) for p, v in raw.get("bids", [])],
            asks=[QuoteLevel(float(p), int(v)) for p, v in raw.get("asks", [])],
            bid_total_volume=int(raw.get("bid_total_volume", 0)),
            ask_total_volume=int(raw.get("ask_total_volume", 0)),
        )
    if msg_type == "tick":
        return TickTrade(
            symbol=symbol,
            ts_ms=ts_ms,
            price=float(raw["price"]),
            volume=int(raw["volume"]),
            bid1_at_trade=float(raw["bid1"]),
            ask1_at_trade=float(raw["ask1"]),
        )
    if msg_type == "order":
        return OrderEvent(
            symbol=symbol,
            ts_ms=ts_ms,
            side=raw["side"],
            price=float(raw["price"]),
            volume=int(raw["volume"]),
            event_type=raw["event_type"],
        )
    return None


class MarketWebSocketClient:
    """WebSocket subscriber with exponential backoff reconnect."""

    def __init__(
        self,
        url: str | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        self.url = url or settings.ws_url
        self.symbols = symbols or settings.symbols
        self._reconnect_delay = settings.reconnect_base_sec

    async def stream(self) -> AsyncIterator[Level1Snapshot | Level2Snapshot | TickTrade | OrderEvent]:
        subscribe_msg = json.dumps({"action": "subscribe", "symbols": self.symbols})

        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=10) as ws:
                    await ws.send(subscribe_msg)
                    logger.info("Connected to %s, subscribed %s", self.url, self.symbols)
                    self._reconnect_delay = settings.reconnect_base_sec

                    async for message in ws:
                        try:
                            raw = json.loads(message)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON: %s", message[:200])
                            continue
                        parsed = parse_market_message(raw)
                        if parsed is not None:
                            yield parsed
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                logger.warning("WebSocket disconnected: %s, reconnect in %.1fs", exc, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    settings.reconnect_max_sec,
                )
