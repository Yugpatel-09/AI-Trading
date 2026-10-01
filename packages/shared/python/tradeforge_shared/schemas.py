from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from tradeforge_shared.enums import (
    TradingMode,
    OrderSide,
    OrderType,
    OrderStatus,
    MarketRegime,
    StrategyType,
    BrokerType,
)

class Candle(BaseModel):
    """OHLCV market bar."""
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    timeframe: str  # "1m", "5m", "10m"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None

class Signal(BaseModel):
    """AI Strategy Signal with mandatory protective stop and plain-English rationale."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    strategy_type: StrategyType
    symbol: str
    side: OrderSide
    timeframe: str
    timestamp: datetime
    entry_price: float
    stop_loss: float = Field(..., description="Mandatory protective stop price")
    target: float = Field(..., description="Target profit price")
    trailing_stop_delta: Optional[float] = None
    time_stop_minutes: int = 45
    regime: MarketRegime
    quality_score: float = Field(..., ge=0.0, le=1.0, description="LightGBM probability score")
    expected_net_gain_pct: float
    reason: str = Field(..., description="Human-readable plain English rationale")

class UserRiskSettings(BaseModel):
    """User-configured risk ceiling."""
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    capital_allocated_inr: float = Field(default=100000.0, ge=5000.0)
    max_loss_per_trade_inr: float = Field(default=1000.0, ge=100.0)
    max_daily_loss_inr: float = Field(default=3000.0, ge=500.0)
    max_open_positions: int = Field(default=2, ge=1, le=5)
    max_daily_trades: int = Field(default=8, ge=1, le=20)
    mode: TradingMode = TradingMode.PAPER
    auto_stop_after_consecutive_losses: int = Field(default=3, ge=1, le=5)
    allowed_instruments: List[str] = Field(default_factory=lambda: ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY"])
    trading_start_time_ist: str = "09:20:00"
    trading_end_time_ist: str = "15:00:00"

class RiskCheckResult(BaseModel):
    """Output from RiskGuard validation."""
    approved: bool
    reason: str
    adjusted_quantity: int = 0
    calculated_risk_inr: float = 0.0
    violations: List[str] = Field(default_factory=list)

class OrderProposal(BaseModel):
    """Order submitted to Risk Guard for validation."""
    idempotency_key: str
    user_id: str
    signal: Signal
    requested_quantity: int
    mode: TradingMode
    broker: BrokerType = BrokerType.PAPER

class ExecutionOrder(BaseModel):
    """Order routed through broker gateway."""
    order_id: str
    idempotency_key: str
    user_id: str
    broker: BrokerType
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    stop_loss: float
    target: float
    status: OrderStatus
    filled_quantity: int = 0
    average_fill_price: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    rejection_reason: Optional[str] = None
    fees: Optional[Dict[str, float]] = None

class SystemHealthStatus(BaseModel):
    """Live telemetry status for UI status bar."""
    status: str = "HEALTHY"
    data_feed_delay_ms: int = 42
    timescaledb_connected: bool = True
    redis_connected: bool = True
    kill_switch_active: bool = False
    open_positions_count: int = 0
    todays_realized_pnl_inr: float = 0.0
    active_mode: TradingMode = TradingMode.PAPER
    timestamp: datetime = Field(default_factory=datetime.utcnow)
