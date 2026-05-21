from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from qm_monitor.config import settings
from qm_monitor.models.market import TickTrade, TradeDirection


def classify_trade(tick: TickTrade) -> TradeDirection:
    """Infer active side: trade at ask -> active buy; at bid -> active sell."""
    if tick.price >= tick.ask1_at_trade - 1e-6:
        return TradeDirection.ACTIVE_BUY
    if tick.price <= tick.bid1_at_trade + 1e-6:
        return TradeDirection.ACTIVE_SELL
    mid = (tick.bid1_at_trade + tick.ask1_at_trade) / 2
    if tick.price > mid:
        return TradeDirection.ACTIVE_BUY
    if tick.price < mid:
        return TradeDirection.ACTIVE_SELL
    return TradeDirection.NEUTRAL


@dataclass
class OrderFlowStats:
    active_buy_volume: int = 0
    active_sell_volume: int = 0
    imbalance: float = 0.0
    trade_count: int = 0

    @property
    def net_volume(self) -> int:
        return self.active_buy_volume - self.active_sell_volume


class OrderFlowAnalyzer:
    """Rolling window order-flow imbalance from tick trades."""

    def __init__(self, window_sec: float | None = None) -> None:
        self.window_ms = int((window_sec or settings.flow_window_sec) * 1000)
        self._ticks: deque[tuple[int, TradeDirection, int]] = deque()

    def on_tick(self, tick: TickTrade) -> OrderFlowStats:
        direction = classify_trade(tick)
        tick.direction = direction
        if direction == TradeDirection.NEUTRAL:
            return self.stats(tick.ts_ms)

        self._ticks.append((tick.ts_ms, direction, tick.volume))
        self._evict(tick.ts_ms)
        return self.stats(tick.ts_ms)

    def _evict(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        while self._ticks and self._ticks[0][0] < cutoff:
            self._ticks.popleft()

    def stats(self, now_ms: int | None = None) -> OrderFlowStats:
        if now_ms is not None:
            self._evict(now_ms)
        buy_vol = sell_vol = 0
        for _, d, v in self._ticks:
            if d == TradeDirection.ACTIVE_BUY:
                buy_vol += v
            elif d == TradeDirection.ACTIVE_SELL:
                sell_vol += v
        total = buy_vol + sell_vol
        imbalance = (buy_vol - sell_vol) / total if total > 0 else 0.0
        return OrderFlowStats(
            active_buy_volume=buy_vol,
            active_sell_volume=sell_vol,
            imbalance=imbalance,
            trade_count=len(self._ticks),
        )
