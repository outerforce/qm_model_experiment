from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import AsyncIterator

import websockets
from websockets.server import serve

from qm_monitor.config import settings

logger = logging.getLogger(__name__)

# Base prices for demo symbols (ETF / large cap)
BASE_PRICES = {
    "510300": 3.85,
    "600519": 1680.0,
    "000001": 11.2,
}


class MockMarketFeed:
    """Local WebSocket server emitting synthetic L1/L2/tick/order events."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._states: dict[str, dict] = {}

    def _init_symbol(self, symbol: str) -> dict:
        base = BASE_PRICES.get(symbol, 10.0)
        tick = base * 0.01
        return {
            "price": base,
            "tick": tick,
            "bid_total": random.randint(500_000, 2_000_000),
            "ask_total": random.randint(500_000, 2_000_000),
            "phase": 0,
        }

    def _gen_l2(self, symbol: str, ts_ms: int) -> dict:
        st = self._states[symbol]
        p, tick = st["price"], st["tick"]
        bids = [[round(p - tick * (i + 1), 2), random.randint(1000, 50_000)] for i in range(10)]
        asks = [[round(p + tick * (i + 1), 2), random.randint(1000, 50_000)] for i in range(10)]
        # Simulate sell pressure or absorption
        if random.random() < 0.1:
            asks[0][1] = random.randint(200_000, 500_000)
        if random.random() < 0.08:
            bids[0][1] = random.randint(200_000, 500_000)
        st["bid_total"] = sum(v for _, v in bids)
        st["ask_total"] = sum(v for _, v in asks)
        return {
            "type": "l2",
            "symbol": symbol,
            "ts_ms": ts_ms,
            "last_price": p,
            "bids": bids,
            "asks": asks,
            "bid_total_volume": st["bid_total"],
            "ask_total_volume": st["ask_total"],
        }

    def _gen_tick(self, symbol: str, ts_ms: int) -> dict:
        st = self._states[symbol]
        p, tick = st["price"], st["tick"]
        bid1 = round(p - tick, 2)
        ask1 = round(p + tick, 2)
        # Bias toward active buy in accumulation phase
        st["phase"] = (st["phase"] + 1) % 200
        if st["phase"] < 80:
            price = ask1 if random.random() < 0.65 else bid1
            vol = random.randint(500, 80_000) if random.random() < 0.3 else random.randint(100, 5000)
        else:
            price = bid1 if random.random() < 0.55 else ask1
            vol = random.randint(100, 8000)
        if price >= ask1 - 1e-6:
            st["price"] = min(st["price"] * 1.0003, ask1 + tick * 3)
        elif price <= bid1 + 1e-6:
            st["price"] = max(st["price"] * 0.9997, bid1 - tick * 3)
        else:
            st["price"] = price
        return {
            "type": "tick",
            "symbol": symbol,
            "ts_ms": ts_ms,
            "price": price,
            "volume": vol,
            "bid1": bid1,
            "ask1": ask1,
        }

    def _gen_order_event(self, symbol: str, ts_ms: int) -> dict | None:
        if random.random() > 0.15:
            return None
        st = self._states[symbol]
        side = random.choice(["bid", "ask"])
        price = round(st["price"] + (0.01 if side == "ask" else -0.01), 2)
        # Ghost order: add then quick cancel pattern injected occasionally
        if random.random() < 0.05:
            return {
                "type": "order",
                "symbol": symbol,
                "ts_ms": ts_ms,
                "side": side,
                "price": price,
                "volume": random.randint(100_000, 300_000),
                "event_type": "add",
                "_ghost": True,
            }
        return {
            "type": "order",
            "symbol": symbol,
            "ts_ms": ts_ms,
            "side": side,
            "price": price,
            "volume": random.randint(5000, 40_000),
            "event_type": random.choice(["add", "cancel"]),
        }

    async def _handle_client(self, websocket: websockets.WebSocketServerProtocol) -> None:
        subscribed: list[str] = []
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            msg = json.loads(raw)
            if msg.get("action") == "subscribe":
                subscribed = msg.get("symbols", list(BASE_PRICES.keys()))
                for s in subscribed:
                    if s not in self._states:
                        self._states[s] = self._init_symbol(s)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            subscribed = list(BASE_PRICES.keys())
            for s in subscribed:
                self._states.setdefault(s, self._init_symbol(s))

        ghost_pending: list[tuple[str, dict]] = []
        while True:
            ts_ms = int(asyncio.get_event_loop().time() * 1000)
            for symbol in subscribed:
                await websocket.send(json.dumps(self._gen_l2(symbol, ts_ms)))
                await websocket.send(json.dumps(self._gen_tick(symbol, ts_ms + 1)))
                l1 = self._states[symbol]
                bid1 = round(l1["price"] - l1["tick"], 2)
                ask1 = round(l1["price"] + l1["tick"], 2)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "l1",
                            "symbol": symbol,
                            "ts_ms": ts_ms + 2,
                            "last_price": l1["price"],
                            "last_volume": random.randint(100, 5000),
                            "bid1_price": bid1,
                            "bid1_volume": random.randint(5000, 80_000),
                            "ask1_price": ask1,
                            "ask1_volume": random.randint(5000, 80_000),
                        }
                    )
                )
                ev = self._gen_order_event(symbol, ts_ms + 3)
                if ev:
                    await websocket.send(json.dumps({k: v for k, v in ev.items() if not k.startswith("_")}))
                    if ev.get("_ghost"):
                        ghost_pending.append(
                            (
                                symbol,
                                {
                                    "type": "order",
                                    "symbol": symbol,
                                    "ts_ms": ts_ms + 50,
                                    "side": ev["side"],
                                    "price": ev["price"],
                                    "volume": ev["volume"],
                                    "event_type": "cancel",
                                },
                            )
                        )
            for sym, cancel_ev in ghost_pending:
                await websocket.send(json.dumps(cancel_ev))
            ghost_pending.clear()
            await asyncio.sleep(0.05)

    async def run(self) -> None:
        logger.info("Mock feed listening ws://%s:%s", self.host, self.port)
        async with serve(self._handle_client, self.host, self.port):
            await asyncio.Future()

    @staticmethod
    async def run_standalone() -> None:
        feed = MockMarketFeed()
        await feed.run()


async def mock_stream_local(symbols: list[str]) -> AsyncIterator[dict]:
    """In-process generator without WebSocket (for unit tests)."""
    feed = MockMarketFeed()
    for s in symbols:
        feed._states[s] = feed._init_symbol(s)
    while True:
        ts_ms = int(asyncio.get_event_loop().time() * 1000)
        for symbol in symbols:
            yield feed._gen_l2(symbol, ts_ms)
            yield feed._gen_tick(symbol, ts_ms + 1)
        await asyncio.sleep(0.01)
