#!/usr/bin/env python3
"""Entry point: mock feed server or live monitor dashboard."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from rich.console import Console
from rich.live import Live
from rich.table import Table

from qm_monitor.config import settings
from qm_monitor.data.mock_feed import MockMarketFeed
from qm_monitor.models.market import MonitorSnapshot
from qm_monitor.pipeline.monitor import StockMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
console = Console()


def build_table(rows: dict[str, MonitorSnapshot]) -> Table:
    table = Table(title="实时买卖量监控 · QM Stock Monitor")
    table.add_column("标的", style="cyan")
    table.add_column("最新价", justify="right")
    table.add_column("信号", style="bold")
    table.add_column("评分", justify="right")
    table.add_column("订单流不平衡", justify="right")
    table.add_column("主动买/卖量", justify="right")
    table.add_column("大单净流入", justify="right")
    table.add_column("卖压", justify="right")
    table.add_column("幽灵单噪音", justify="right")
    table.add_column("风控", style="red")

    for sym, s in sorted(rows.items()):
        signal_style = {"BUY": "green", "WATCH": "yellow", "CLOSE": "red", "RISK": "red"}.get(
            s.signal, "white"
        )
        table.add_row(
            sym,
            f"{s.last_price:.2f}",
            f"[{signal_style}]{s.signal}[/{signal_style}]",
            f"{s.buy_score:.2f}",
            f"{s.order_flow_imbalance:+.1%}",
            f"{s.active_buy_volume}/{s.active_sell_volume}",
            f"{s.large_net_inflow/1e4:.1f}万",
            f"{s.sell_pressure_score:.0%}",
            f"{s.ghost_noise_score:.0%}",
            s.risk_alert or "-",
        )
    return table


async def run_monitor(use_mock_stream: bool, symbols: list[str]) -> None:
    rows: dict[str, MonitorSnapshot] = {}

    async def on_snapshot(snap: MonitorSnapshot) -> None:
        rows[snap.symbol] = snap

    monitor = StockMonitor(symbols=symbols, use_mock_stream=use_mock_stream)

    with Live(console=console, refresh_per_second=4) as live:
        async def refresh_loop() -> None:
            while True:
                if rows:
                    live.update(build_table(rows))
                await asyncio.sleep(0.25)

        await asyncio.gather(monitor.run(on_snapshot), refresh_loop())


async def run_mock_server() -> None:
    feed = MockMarketFeed()
    await feed.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="基于实时买卖量的股价监控量化工具")
    parser.add_argument(
        "mode",
        choices=["monitor", "mock-server", "demo"],
        help="monitor=连接WS; mock-server=启动模拟行情; demo=进程内模拟无需WS",
    )
    parser.add_argument("-s", "--symbols", nargs="+", default=settings.symbols)
    args = parser.parse_args()

    if args.mode == "mock-server":
        asyncio.run(run_mock_server())
    elif args.mode == "demo":
        asyncio.run(run_monitor(use_mock_stream=True, symbols=args.symbols))
    else:
        asyncio.run(run_monitor(use_mock_stream=False, symbols=args.symbols))


if __name__ == "__main__":
    main()
