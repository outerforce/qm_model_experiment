from qm_monitor.analysis.capital_flow import CapitalFlowStats
from qm_monitor.analysis.order_book import OrderBookMetrics
from qm_monitor.analysis.order_flow import OrderFlowStats
from qm_monitor.signals.scorer import SignalScorer


def test_buy_signal_high_score():
    scorer = SignalScorer()
    flow = OrderFlowStats(active_buy_volume=100_000, active_sell_volume=20_000, imbalance=0.67)
    book = OrderBookMetrics(sell_pressure_score=0.2, ghost_noise_score=0.1, bid_ask_ratio=1.2)
    capital = CapitalFlowStats(large_net_inflow=800_000, volume_price_divergence=False)
    sig = scorer.evaluate(flow, book, capital)
    assert sig.label == "BUY"
    assert sig.score >= 0.65


def test_divergence_blocks_buy():
    scorer = SignalScorer()
    flow = OrderFlowStats(active_buy_volume=100_000, active_sell_volume=20_000, imbalance=0.67)
    book = OrderBookMetrics(sell_pressure_score=0.2, ghost_noise_score=0.1)
    capital = CapitalFlowStats(large_net_inflow=500_000, volume_price_divergence=True)
    sig = scorer.evaluate(flow, book, capital)
    assert sig.label != "BUY"
