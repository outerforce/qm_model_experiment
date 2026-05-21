from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from qm_monitor.config import settings
from qm_monitor.models.market import Level1Snapshot


@dataclass
class PositionState:
    symbol: str
    entry_price: float
    quantity: int = 0
    in_position: bool = False


@dataclass
class RiskAlert:
    action: str  # "close" | "warn"
    reason: str


class RiskController:
    """Dynamic spread alert, stop-loss, take-profit."""

    def __init__(self) -> None:
        self._spread_history: deque[float] = deque(maxlen=200)

    def on_l1(self, snap: Level1Snapshot, position: PositionState | None = None) -> Optional[RiskAlert]:
        spread = snap.ask1.price - snap.bid1.price
        if spread > 0:
            self._spread_history.append(spread)

        if len(self._spread_history) >= 20:
            avg_spread = sum(self._spread_history) / len(self._spread_history)
            if avg_spread > 0 and spread >= avg_spread * settings.spread_alert_multiplier:
                return RiskAlert(
                    action="close",
                    reason=f"买卖价差扩大至均值{settings.spread_alert_multiplier}x，流动性枯竭",
                )

        if position and position.in_position and position.entry_price > 0:
            pnl_pct = (snap.last_price - position.entry_price) / position.entry_price
            if pnl_pct <= settings.stop_loss_pct:
                return RiskAlert(action="close", reason=f"触发止损 {pnl_pct:.2%}")
            if pnl_pct >= settings.take_profit_pct:
                return RiskAlert(action="close", reason=f"触发止盈 {pnl_pct:.2%}")

        return None
