# QM Stock Monitor — 实时买卖量股价监控

基于市场微观结构（订单流、盘口深度、大单资金流向）的量化监控工具，用于评估短期「是否值得买入」。

## 架构

```
行情源 (WebSocket L1/L2/Tick)
    ↓ 断线重连
异步队列
    ↓
├─ 订单流分析：主动买/卖识别、不平衡度
├─ 盘口分析：卖压、托盘、幽灵单过滤
├─ 资金流向：大单阈值追踪、量价背离
    ↓
信号评分 (BUY / WATCH / HOLD)
    ↓
动态风控 (价差扩大 / 止盈止损)
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 终端 1：启动本地模拟 Level-2 行情
python main.py mock-server

# 终端 2：连接 WebSocket 并显示实时监控面板
python main.py monitor -s 510300 600519

# 或：无需 WebSocket，进程内演示
python main.py demo -s 510300
```

## 核心指标说明

| 模块 | 说明 |
|------|------|
| **主动买卖** | 成交价 ≥ 卖一 → 主动买入；≤ 买一 → 主动卖出 |
| **订单流不平衡** | `(主动买量 - 主动卖量) / 总量`，滚动窗口默认 60s |
| **盘口卖压** | 卖一至卖五挂单集中度 vs 买盘支撑 |
| **幽灵单** | 大额挂单在 500ms 内撤单，撤单率过高则降权 |
| **大单净流入** | 单笔成交额 ≥ 50 万（可配置）的主动方向净值 |
| **量价背离** | 价格创新高但委买/委卖比下降 → 不宜追高 |

## 接入真实行情

将 `QM_WS_URL` 指向券商或数据商的 WebSocket 端点，推送 JSON 需符合以下格式：

```json
{"type": "tick", "symbol": "510300", "ts_ms": 1710000000000, "price": 3.86, "volume": 5000, "bid1": 3.85, "ask1": 3.86}
{"type": "l2", "symbol": "510300", "ts_ms": 1710000000000, "last_price": 3.86, "bids": [[3.85, 10000]], "asks": [[3.86, 8000]], "bid_total_volume": 500000, "ask_total_volume": 480000}
{"type": "order", "symbol": "510300", "ts_ms": 1710000000000, "side": "ask", "price": 3.90, "volume": 200000, "event_type": "add"}
```

`.env` 示例：

```env
QM_WS_URL=wss://your-broker-market-stream
QM_SYMBOLS=510300,600519
QM_LARGE_ORDER_THRESHOLD=500000
QM_MIN_BUY_SCORE=0.65
```

## 项目结构

```
qm_monitor/
  config.py           # 配置（环境变量 QM_*）
  models/market.py    # L1/L2/Tick 数据模型
  data/               # WebSocket 客户端 + 模拟行情
  analysis/           # 订单流、盘口、资金流向
  signals/scorer.py   # 买入信号评分
  risk/               # 价差/止盈止损
  pipeline/monitor.py # 异步流水线
main.py               # CLI 入口
tests/                # 单元测试
```

## 测试

```bash
pip install pytest
pytest tests/ -q
```

## 迭代建议

1. **第一阶段（当前）**：跑通 Tick + 主动买卖量 + 信号评分
2. **第二阶段**：接入真实 Level-2，校准大单阈值与窗口
3. **第三阶段**：回测框架、多标的并行、告警推送（钉钉/邮件）

> 本工具仅供学习研究，不构成投资建议。实盘前请充分回测并遵守当地法规。
