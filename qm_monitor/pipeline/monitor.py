from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from qm_monitor.analysis.capital_flow import CapitalFlowAnalyzer
from qm_monitor.analysis.order_book import OrderBookAnalyzer, OrderBookMetrics
from qm_monitor.analysis.order_flow import OrderFlowAnalyzer
from qm_monitor.config import settings
from qm_monitor.data.websocket_client import MarketWebSocketClient, parse_market_message
from qm_monitor.models.market import (
    Level1Snapshot,
    Level2Snapshot,
    MonitorSnapshot,
    OrderEvent,
    TickTrade,
)
from qm_monitor.risk.risk_control import PositionState, RiskController
from qm_monitor.signals.scorer import SignalScorer

logger = logging.getLogger(__name__)

SnapshotCallback = Callable[[MonitorSnapshot], Awaitable[None]]


class SymbolState:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.order_flow = OrderFlowAnalyzer()
        self.order_book = OrderBookAnalyzer()
        self.capital = CapitalFlowAnalyzer()
        self.last_price = 0.0
        self.last_ts = 0
        self.last_book = OrderBookMetrics()


class StockMonitor:
    """Async pipeline: WebSocket -> queue -> analyzers -> signals."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        ws_url: str | None = None,
        use_mock_stream: bool = False,
    ) -> None:
        self.symbols = symbols or settings.symbols
        self._client = MarketWebSocketClient(url=ws_url, symbols=self.symbols)
        self._use_mock_stream = use_mock_stream
        self._states = {s: SymbolState(s) for s in self.symbols}
        self._scorer = SignalScorer()
        self._risk = RiskController()
        self._positions: dict[str, PositionState] = {
            s: PositionState(symbol=s, entry_price=0.0) for s in self.symbols
        }
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=settings.queue_maxsize)

    async def _producer(self) -> None:
        if self._use_mock_stream:
            from qm_monitor.data.mock_feed import mock_stream_local

            async for raw in mock_stream_local(self.symbols):
                parsed = parse_market_message(raw)
                if parsed is not None:
                    await self._enqueue(parsed)
            return

        async for msg in self._client.stream():
            await self._enqueue(msg)

    async def _enqueue(self, msg: Level1Snapshot | Level2Snapshot | TickTrade | OrderEvent) -> None:
        try:
            self._queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Queue full, dropping oldest message")
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self._queue.put(msg)

    def _process(self, msg: Level1Snapshot | Level2Snapshot | TickTrade | OrderEvent) -> MonitorSnapshot | None:
        symbol = msg.symbol
        if symbol not in self._states:
            self._states[symbol] = SymbolState(symbol)
        st = self._states[symbol]

        if isinstance(msg, OrderEvent):
            st.order_book.on_order(msg)
            return None

        if isinstance(msg, Level1Snapshot):
            st.last_price = msg.last_price
            st.last_ts = msg.ts_ms
            spread = msg.ask1.price - msg.bid1.price
            alert = self._risk.on_l1(msg, self._positions.get(symbol))
            if alert:
                self._positions[symbol].in_position = False
                return self._snapshot(st, signal="CLOSE", risk_alert=alert.reason, spread=spread)
            return None

        if isinstance(msg, Level2Snapshot):
            st.last_book = st.order_book.on_l2(msg)
            st.capital.on_l2(msg)
            st.last_price = msg.last_price
            st.last_ts = msg.ts_ms
            return self._evaluate(st, spread=0.0)

        if isinstance(msg, TickTrade):
            st.order_flow.on_tick(msg)
            st.capital.on_tick(msg)
            st.last_price = msg.price
            st.last_ts = msg.ts_ms
            return self._evaluate(st, spread=0.0)

        return None

    def _evaluate(self, st: SymbolState, spread: float) -> MonitorSnapshot:
        flow = st.order_flow.stats(st.last_ts)
        capital = st.capital.stats(st.last_ts)
        signal = self._scorer.evaluate(flow, st.last_book, capital)

        risk_alert = None
        if capital.volume_price_divergence and self._positions[st.symbol].in_position:
            risk_alert = "量价背离，建议减仓"
            self._positions[st.symbol].in_position = False

        if signal.label == "BUY" and not self._positions[st.symbol].in_position:
            self._positions[st.symbol] = PositionState(
                symbol=st.symbol, entry_price=st.last_price, in_position=True
            )

        return self._snapshot(
            st,
            signal=signal.label,
            buy_score=signal.score,
            spread=spread,
            risk_alert=risk_alert,
        )

    def _snapshot(
        self,
        st: SymbolState,
        signal: str,
        buy_score: float = 0.0,
        spread: float = 0.0,
        risk_alert: str | None = None,
    ) -> MonitorSnapshot:
        flow = st.order_flow.stats(st.last_ts)
        capital = st.capital.stats(st.last_ts)
        book = st.last_book
        return MonitorSnapshot(
            symbol=st.symbol,
            ts_ms=st.last_ts,
            last_price=st.last_price,
            order_flow_imbalance=flow.imbalance,
            active_buy_volume=flow.active_buy_volume,
            active_sell_volume=flow.active_sell_volume,
            bid_ask_ratio=book.bid_ask_ratio,
            large_net_inflow=capital.large_net_inflow,
            sell_pressure_score=book.sell_pressure_score,
            ghost_noise_score=book.ghost_noise_score,
            volume_price_divergence=capital.volume_price_divergence,
            buy_score=buy_score,
            signal=signal,
            spread=spread,
            risk_alert=risk_alert,
        )

    async def _consumer(self, on_snapshot: SnapshotCallback) -> None:
        while True:
            msg = await self._queue.get()
            snap = self._process(msg)
            if snap is not None:
                await on_snapshot(snap)

    async def run(self, on_snapshot: SnapshotCallback) -> None:
        await asyncio.gather(self._producer(), self._consumer(on_snapshot))
