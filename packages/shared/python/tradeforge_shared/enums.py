from enum import Enum


class TradingMode(str, Enum):
    """Platform operating mode for order routing."""
    PAPER = "PAPER"       # Virtual simulation on live market feeds (Default)
    APPROVE = "APPROVE"   # Trade setup proposed by AI, requires explicit user mobile/web approval
    AUTO = "AUTO"         # Autonomous execution strictly bounded by RiskGuard limits

class OrderSide(str, Enum):
    """Order transaction side."""
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    """Order type category."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"             # Stop-Loss limit
    SL_M = "SL_M"         # Stop-Loss market

class OrderStatus(str, Enum):
    """Lifecycle status of an execution order."""
    PENDING = "PENDING"
    PENDING_USER_APPROVAL = "PENDING_USER_APPROVAL"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTED = "SUBMITTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class MarketRegime(str, Enum):
    """Market regime classification evaluated by Specialist 1."""
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGE_BOUND = "RANGE_BOUND"
    VOLATILE_CHAOTIC = "VOLATILE_CHAOTIC"

class StrategyType(str, Enum):
    """Core scalper and breakout strategies."""
    SCALPER_1M = "SCALPER_1M"           # 1-minute VWAP pullback with 5m trend confirmation
    SCALPER_5M = "SCALPER_5M"           # 5-minute EMA 9/21 cross & Supertrend flip
    SCALPER_10M_ORB = "SCALPER_10M_ORB" # 10-minute Opening Range Breakout with retest

class BrokerType(str, Enum):
    """Supported Indian broker integrations."""
    PAPER = "PAPER"
    ZERODHA = "ZERODHA"
    UPSTOX = "UPSTOX"
    ANGEL_ONE = "ANGEL_ONE"
    GROWW = "GROWW"
    DHAN = "DHAN"
