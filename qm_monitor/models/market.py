from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TradeDirection(str, Enum):
    ACTIVE_BUY = "active_buy"
    ACTIVE_SELL = "active_sell"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class QuoteLevel:
    price: float
    volume: int


@dataclass
class Level1Snapshot:
    symbol: str
    ts_ms: int
    last_price: float
    last_volume: int
    bid1: QuoteLevel
    ask1: QuoteLevel
    total_volume: int = 0
    total_turnover: float = 0.0


@dataclass
class Level2Snapshot:
    """Ten-level order book snapshot."""

    symbol: str
    ts_ms: int
    last_price: float
    bids: list[QuoteLevel] = field(default_factory=list)
    asks: list[QuoteLevel] = field(default_factory=list)
    bid_total_volume: int = 0
    ask_total_volume: int = 0


@dataclass
class TickTrade:
    symbol: str
    ts_ms: int
    price: float
    volume: int
    bid1_at_trade: float
    ask1_at_trade: float
    direction: TradeDirection = TradeDirection.NEUTRAL


@dataclass
class OrderEvent:
    """Level-2 order add/cancel for ghost-order detection."""

    symbol: str
    ts_ms: int
    side: str  # "bid" | "ask"
    price: float
    volume: int
    event_type: str  # "add" | "cancel" | "trade"


@dataclass
class MonitorSnapshot:
    symbol: str
    ts_ms: int
    last_price: float
    order_flow_imbalance: float
    active_buy_volume: int
    active_sell_volume: int
    bid_ask_ratio: float
    large_net_inflow: float
    sell_pressure_score: float
    ghost_noise_score: float
    volume_price_divergence: bool
    buy_score: float
    signal: str
    spread: float
    risk_alert: Optional[str] = None
