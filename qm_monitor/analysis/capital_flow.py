from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from qm_monitor.analysis.order_flow import classify_trade
from qm_monitor.config import settings
from qm_monitor.models.market import Level2Snapshot, TickTrade, TradeDirection


@dataclass
class CapitalFlowStats:
    large_buy_notional: float = 0.0
    large_sell_notional: float = 0.0
    large_net_inflow: float = 0.0
    price_high: float = 0.0
    price_low: float = 0.0
    volume_price_divergence: bool = False
    large_buy_ratio: float = 0.0


class CapitalFlowAnalyzer:
    """Large-order tracking and volume-price divergence."""

    def __init__(
        self,
        large_threshold: float | None = None,
        window_sec: float | None = None,
    ) -> None:
        self.threshold = large_threshold or settings.large_order_threshold
        self.window_ms = int((window_sec or settings.flow_window_sec) * 1000)
        self._large_trades: deque[tuple[int, TradeDirection, float]] = deque()
        self._prices: deque[tuple[int, float]] = deque()
        self._bid_ask_history: deque[tuple[int, float]] = deque()

    def on_tick(self, tick: TickTrade) -> CapitalFlowStats:
        notional = tick.price * tick.volume
        direction = classify_trade(tick)
        self._prices.append((tick.ts_ms, tick.price))
        if notional >= self.threshold:
            self._large_trades.append((tick.ts_ms, direction, notional))
        self._evict(tick.ts_ms)
        return self.stats(tick.ts_ms)

    def on_l2(self, snap: Level2Snapshot) -> None:
        total = snap.bid_total_volume + snap.ask_total_volume
        ratio = snap.bid_total_volume / total if total > 0 else 0.5
        self._bid_ask_history.append((snap.ts_ms, ratio))
        self._evict(snap.ts_ms)

    def _evict(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        for q in (self._large_trades, self._prices, self._bid_ask_history):
            while q and q[0][0] < cutoff:
                q.popleft()

    def stats(self, now_ms: int | None = None) -> CapitalFlowStats:
        if now_ms is not None:
            self._evict(now_ms)

        buy_n = sell_n = 0.0
        for _, d, n in self._large_trades:
            if d == TradeDirection.ACTIVE_BUY:
                buy_n += n
            elif d == TradeDirection.ACTIVE_SELL:
                sell_n += n

        prices = [p for _, p in self._prices]
        high = max(prices) if prices else 0.0
        low = min(prices) if prices else 0.0
        current = prices[-1] if prices else 0.0

        divergence = self._detect_divergence(current, high)

        total_large = buy_n + sell_n
        buy_ratio = buy_n / total_large if total_large > 0 else 0.0

        return CapitalFlowStats(
            large_buy_notional=buy_n,
            large_sell_notional=sell_n,
            large_net_inflow=buy_n - sell_n,
            price_high=high,
            price_low=low,
            volume_price_divergence=divergence,
            large_buy_ratio=buy_ratio,
        )

    def _detect_divergence(self, current: float, high: float) -> bool:
        """New price high but bid/ask ratio declining -> exhaustion warning."""
        if not self._bid_ask_history or len(self._prices) < 5:
            return False
        near_high = high > 0 and current >= high * 0.998
        ratios = [r for _, r in self._bid_ask_history]
        if len(ratios) < 4:
            return False
        recent = sum(ratios[-2:]) / 2
        earlier = sum(ratios[:2]) / 2
        ratio_falling = recent < earlier * 0.95
        return near_high and ratio_falling
