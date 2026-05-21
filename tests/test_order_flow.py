from qm_monitor.analysis.order_flow import OrderFlowAnalyzer, classify_trade
from qm_monitor.models.market import TickTrade, TradeDirection


def test_classify_active_buy():
    tick = TickTrade("510300", 1000, 3.86, 1000, 3.85, 3.86)
    assert classify_trade(tick) == TradeDirection.ACTIVE_BUY


def test_classify_active_sell():
    tick = TickTrade("510300", 1000, 3.85, 1000, 3.85, 3.86)
    assert classify_trade(tick) == TradeDirection.ACTIVE_SELL


def test_order_flow_imbalance():
    analyzer = OrderFlowAnalyzer(window_sec=60.0)
    for _ in range(5):
        analyzer.on_tick(TickTrade("510300", 2000, 3.86, 5000, 3.85, 3.86))
    for _ in range(2):
        analyzer.on_tick(TickTrade("510300", 3000, 3.85, 1000, 3.85, 3.86))
    stats = analyzer.stats(3000)
    assert stats.active_buy_volume > stats.active_sell_volume
    assert stats.imbalance > 0
