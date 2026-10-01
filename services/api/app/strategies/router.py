from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from tradeforge_shared.enums import StrategyType
from services.engine.strategies.scalper_1m import Scalper1M
from services.engine.strategies.scalper_5m import Scalper5M
from services.engine.strategies.scalper_10m_orb import Scalper10MORB
from services.backtester.engine import Backtester
from scripts.seed_data import generate_candles

router = APIRouter(prefix="/api/v1/strategies", tags=["Strategies & Backtesting"])

STRATEGIES_CATALOG = [
    {
        "id": StrategyType.SCALPER_1M.value,
        "name": "1-Minute VWAP Pullback Scalper",
        "timeframe": "1m",
        "description": "Fast intraday scalper exploiting VWAP retests in direction of 5m trend with volume expansion. Best for high-liquidity large caps.",
        "target_pct": 0.25,
        "stop_loss": "0.8x ATR",
        "trade_duration": "1 - 10 minutes",
        "max_trades_per_day": 12,
        "best_regime": "Active Trending",
        "status": "ACTIVE",
    },
    {
        "id": StrategyType.SCALPER_5M.value,
        "name": "5-Minute EMA Cross & Supertrend Scalper",
        "timeframe": "5m",
        "description": "Momentum scalper triggering on EMA 9/21 cross aligned with 15m trend and volume. Balances trade frequency with low slippage overhead.",
        "target_pct": 0.45,
        "stop_loss": "1.0x ATR",
        "trade_duration": "5 - 40 minutes",
        "max_trades_per_day": 8,
        "best_regime": "Clean Trends",
        "status": "ACTIVE",
    },
    {
        "id": StrategyType.SCALPER_10M_ORB.value,
        "name": "10-Minute Opening Range Breakout (ORB)",
        "timeframe": "10m",
        "description": "Breakout scalper taking trades after 09:35 IST when price breaks and retests the initial opening range high or low with index confirmation.",
        "target_pct": 0.75,
        "stop_loss": "1.1x ATR",
        "trade_duration": "10 - 90 minutes",
        "max_trades_per_day": 5,
        "best_regime": "High-Volume Breakouts",
        "status": "ACTIVE",
    },
]

class BacktestRequest(BaseModel):
    strategy_id: str = Field(..., description="SCALPER_1M, SCALPER_5M, or SCALPER_10M_ORB")
    symbol: str = Field(default="NIFTY")
    initial_capital: float = Field(default=100000.0, ge=10000.0)
    risk_per_trade: float = Field(default=1000.0, ge=100.0)
    candle_count: int = Field(default=100, ge=30, le=500)

@router.get("/")
async def list_strategies():
    """Fetch library of available AI scalpers."""
    return STRATEGIES_CATALOG

@router.post("/backtest")
async def run_backtest(payload: BacktestRequest):
    """
    Run backtest on historical/synthetic market data.
    Enforces Rule 5 (Exact same strategy code) & Rule 6 (Indian statutory cost modeling).
    """
    tf = "1m" if "1M" in payload.strategy_id else ("5m" if "5M" in payload.strategy_id else "10m")
    base_price = 22000.0 if "NIFTY" in payload.symbol else 2500.0

    candles = generate_candles(payload.symbol, base_price=base_price, count=payload.candle_count, timeframe=tf)

    if payload.strategy_id == StrategyType.SCALPER_1M.value:
        strat = Scalper1M()
    elif payload.strategy_id == StrategyType.SCALPER_5M.value:
        strat = Scalper5M()
    elif payload.strategy_id == StrategyType.SCALPER_10M_ORB.value:
        strat = Scalper10MORB()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown strategy: {payload.strategy_id}")

    backtester = Backtester()
    results = backtester.run(
        strategy=strat,
        candles=candles,
        initial_capital=payload.initial_capital,
        risk_per_trade_inr=payload.risk_per_trade,
    )
    return results
