from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QM_", env_file=".env", extra="ignore")

    # WebSocket endpoint (replace with broker/L2 provider URL)
    ws_url: str = "ws://127.0.0.1:8765"
    symbols: list[str] = ["510300", "600519"]

    # Order flow window (seconds)
    flow_window_sec: float = 60.0

    # Large order threshold (CNY notional)
    large_order_threshold: float = 500_000.0

    # Ghost order: cancel within this many ms after add
    ghost_cancel_ms: float = 500.0
    ghost_cancel_rate_threshold: float = 0.7

    # Signal thresholds
    min_buy_score: float = 0.65
    order_flow_imbalance_min: float = 0.15

    # Risk control
    spread_alert_multiplier: float = 2.0
    stop_loss_pct: float = -0.02
    take_profit_pct: float = 0.03

    # Async queue
    queue_maxsize: int = 10_000
    reconnect_base_sec: float = 1.0
    reconnect_max_sec: float = 60.0


settings = MonitorSettings()
