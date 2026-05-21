from __future__ import annotations

from dataclasses import dataclass

from qm_monitor.analysis.capital_flow import CapitalFlowStats
from qm_monitor.analysis.order_book import OrderBookMetrics
from qm_monitor.analysis.order_flow import OrderFlowStats
from qm_monitor.config import settings


@dataclass
class BuySignal:
    score: float
    label: str
    reasons: list[str]


class SignalScorer:
    """
    Composite buy score:
    - order flow imbalance (active buy dominance)
    - light sell pressure on book
    - large-order net inflow
    - no volume-price divergence
    - low ghost noise
    """

    def evaluate(
        self,
        flow: OrderFlowStats,
        book: OrderBookMetrics,
        capital: CapitalFlowStats,
    ) -> BuySignal:
        reasons: list[str] = []
        score = 0.0

        # Order flow (weight 0.35)
        if flow.imbalance >= settings.order_flow_imbalance_min:
            flow_score = min(1.0, (flow.imbalance - settings.order_flow_imbalance_min) / 0.35 + 0.5)
            score += 0.35 * flow_score
            reasons.append(f"主动买入占优 imbalance={flow.imbalance:.2%}")
        elif flow.imbalance <= -settings.order_flow_imbalance_min:
            score -= 0.1
            reasons.append(f"主动卖出偏强 imbalance={flow.imbalance:.2%}")

        # Sell pressure inverted (weight 0.25)
        pressure_ok = 1.0 - book.sell_pressure_score
        score += 0.25 * pressure_ok
        if book.sell_pressure_score < 0.4:
            reasons.append("盘口卖压较轻")
        elif book.sell_pressure_score > 0.7:
            reasons.append("盘口卖压较重")

        # Large order inflow (weight 0.25)
        if capital.large_net_inflow > 0:
            inflow_score = min(1.0, capital.large_net_inflow / (settings.large_order_threshold * 3))
            score += 0.25 * inflow_score
            reasons.append(f"大单净流入 {capital.large_net_inflow/1e4:.1f}万")
        elif capital.large_net_inflow < -settings.large_order_threshold:
            score -= 0.15
            reasons.append("大单净流出")

        # Divergence penalty (weight 0.10)
        if capital.volume_price_divergence:
            score -= 0.2
            reasons.append("量价背离预警")
        else:
            score += 0.1
            reasons.append("未检测到量价背离")

        # Ghost noise penalty (weight 0.05)
        if book.ghost_noise_score > settings.ghost_cancel_rate_threshold:
            score -= 0.15
            reasons.append(f"幽灵单噪音 ghost_rate={book.ghost_noise_score:.0%}")
        else:
            score += 0.05 * (1.0 - book.ghost_noise_score)

        score = max(0.0, min(1.0, score))

        if score >= settings.min_buy_score and not capital.volume_price_divergence:
            label = "BUY"
        elif score >= 0.45:
            label = "WATCH"
        else:
            label = "HOLD"

        return BuySignal(score=score, label=label, reasons=reasons)
