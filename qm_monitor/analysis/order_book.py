from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from qm_monitor.config import settings
from qm_monitor.models.market import Level2Snapshot, OrderEvent


@dataclass
class OrderBookMetrics:
    sell_pressure_score: float = 0.0
    support_score: float = 0.0
    bid_ask_ratio: float = 1.0
    ghost_noise_score: float = 0.0
    top5_ask_wall: int = 0
    top5_bid_wall: int = 0


class OrderBookAnalyzer:
    """
    Depth analysis: sell pressure, bid support, ghost-order noise.
    Tracks add/cancel pairs per price level to flag spoofing.
    """

    def __init__(self) -> None:
        self._pending_adds: dict[tuple[str, str, float], deque[tuple[int, int]]] = defaultdict(deque)
        self._ghost_events = 0
        self._total_adds = 0
        self._last_l2: Level2Snapshot | None = None

    def on_l2(self, snap: Level2Snapshot) -> OrderBookMetrics:
        self._last_l2 = snap
        top5_ask = sum(lv.volume for lv in snap.asks[:5])
        top5_bid = sum(lv.volume for lv in snap.bids[:5])
        total_ask = snap.ask_total_volume or max(top5_ask, 1)
        total_bid = snap.bid_total_volume or max(top5_bid, 1)
        ratio = total_bid / total_ask if total_ask > 0 else 1.0

        # Sell pressure: heavy ask wall vs thin bid support on top levels
        ask_concentration = top5_ask / total_ask if total_ask else 0
        bid_concentration = top5_bid / total_bid if total_bid else 0
        sell_pressure = min(1.0, max(0.0, ask_concentration - bid_concentration * 0.5 + 0.2))
        support = min(1.0, bid_concentration / max(ask_concentration, 0.01))

        ghost = min(1.0, self._ghost_rate())

        return OrderBookMetrics(
            sell_pressure_score=sell_pressure,
            support_score=support,
            bid_ask_ratio=ratio,
            ghost_noise_score=ghost,
            top5_ask_wall=top5_ask,
            top5_bid_wall=top5_bid,
        )

    def on_order(self, ev: OrderEvent) -> None:
        key = (ev.symbol, ev.side, ev.price)
        if ev.event_type == "add":
            self._total_adds += 1
            self._pending_adds[key].append((ev.ts_ms, ev.volume))
        elif ev.event_type == "cancel":
            adds = self._pending_adds.get(key)
            if not adds:
                return
            add_ts, add_vol = adds.popleft()
            if (
                ev.ts_ms - add_ts <= settings.ghost_cancel_ms
                and add_vol >= 50_000
            ):
                self._ghost_events += 1

    def _ghost_rate(self) -> float:
        if self._total_adds == 0:
            return 0.0
        return self._ghost_events / self._total_adds

    def is_ghost_heavy(self) -> bool:
        return self._ghost_rate() >= settings.ghost_cancel_rate_threshold
