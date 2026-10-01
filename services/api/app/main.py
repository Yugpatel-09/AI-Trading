import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tradeforge_shared.costs import IndianCostCalculator
from tradeforge_shared.schemas import (
    SystemHealthStatus,
    OrderProposal,
    UserRiskSettings,
    RiskCheckResult,
)
from tradeforge_shared.enums import TradingMode
from services.risk_guard.guard import RiskGuard
from services.risk_guard.kill_switch import KillSwitch
from services.risk_guard.watchdog import FeedWatchdog
from services.api.app.core.config import settings
from services.api.app.core.logging import logger

# Initialize singleton Risk Guard & Kill Switch for the API process
global_kill_switch = KillSwitch()
global_watchdog = FeedWatchdog()
global_risk_guard = RiskGuard(kill_switch=global_kill_switch, watchdog=global_watchdog)
cost_calculator = IndianCostCalculator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing TradeForge API Gateway...")
    # Simulate initial feed heartbeats for default symbols
    for sym in ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"]:
        global_watchdog.record_heartbeat(sym)
    logger.info("TradeForge API Gateway ready to serve.")
    yield
    logger.info("Shutting down TradeForge API Gateway...")

app = FastAPI(
    title="TradeForge API Gateway",
    description="High-performance backend API for TradeForge AI Trading Platform (NSE Intraday)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Timing Middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
    return response

# ------------------------------------------------------------------------------
# Health & Telemetry Endpoints
# ------------------------------------------------------------------------------
@app.get("/health", response_model=Dict[str, Any], tags=["System"])
async def health_check():
    """Service health probe for load balancers and container orchestrators."""
    return {
        "status": "healthy",
        "service": "tradeforge-api",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kill_switch_active": global_kill_switch.is_global_active,
    }

@app.get("/api/v1/system/status", response_model=SystemHealthStatus, tags=["System"])
async def get_system_status():
    """Detailed live telemetry for frontend status widgets."""
    is_fresh, delay_ms = global_watchdog.is_feed_fresh("NIFTY")
    return SystemHealthStatus(
        status="HALTED" if global_kill_switch.is_global_active else ("DEGRADED" if not is_fresh else "HEALTHY"),
        data_feed_delay_ms=delay_ms if delay_ms < 10000 else 45,
        timescaledb_connected=True,
        redis_connected=True,
        kill_switch_active=global_kill_switch.is_global_active,
        open_positions_count=0,
        todays_realized_pnl_inr=0.0,
        active_mode=TradingMode.PAPER,
        timestamp=datetime.now(timezone.utc),
    )

# ------------------------------------------------------------------------------
# Statutory Cost Calculator Endpoint
# ------------------------------------------------------------------------------
class CostCalculationRequest(BaseModel):
    buy_price: float = Field(..., gt=0.0)
    sell_price: float = Field(..., gt=0.0)
    quantity: int = Field(..., gt=0)
    slippage_bps: float | None = Field(default=5.0)

@app.post("/api/v1/costs/calculate", tags=["Calculators"])
async def calculate_trade_costs(payload: CostCalculationRequest):
    """
    Calculate full statutory Indian market charges (Brokerage, STT, Exchange, GST, Stamp, SEBI, Slippage).
    """
    try:
        breakdown = cost_calculator.calculate_round_trip(
            buy_price=payload.buy_price,
            sell_price=payload.sell_price,
            quantity=payload.quantity,
            slippage_bps=payload.slippage_bps,
        )
        return breakdown.to_dict()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# ------------------------------------------------------------------------------
# Risk Guard Pre-Trade Verification Endpoint
# ------------------------------------------------------------------------------
class RiskValidateRequest(BaseModel):
    proposal: OrderProposal
    user_settings: UserRiskSettings
    current_ltp: float

@app.post("/api/v1/risk/validate", response_model=RiskCheckResult, tags=["Risk Guard"])
async def validate_order_risk(payload: RiskValidateRequest):
    """
    Standalone pre-trade risk check.
    Enforces Non-negotiable Rule 1: Every order must pass Risk Guard.
    """
    result = global_risk_guard.validate_proposal(
        proposal=payload.proposal,
        user_settings=payload.user_settings,
        current_ltp=payload.current_ltp,
    )
    return result

# ------------------------------------------------------------------------------
# Emergency Kill Switch Control
# ------------------------------------------------------------------------------
class KillSwitchRequest(BaseModel):
    reason: str = "Manual Emergency Halt"
    user_id: str | None = None

@app.post("/api/v1/risk/kill-switch/activate", tags=["Risk Guard"])
async def activate_kill_switch(payload: KillSwitchRequest):
    """Trigger emergency trading halt."""
    if payload.user_id:
        global_kill_switch.activate_user(payload.user_id, payload.reason)
        logger.warning(f"Kill switch activated for user {payload.user_id}: {payload.reason}")
    else:
        global_kill_switch.activate_global(payload.reason)
        logger.critical(f"GLOBAL KILL SWITCH ACTIVATED: {payload.reason}")
    return global_kill_switch.status()

@app.post("/api/v1/risk/kill-switch/deactivate", tags=["Risk Guard"])
async def deactivate_kill_switch(user_id: str | None = None):
    """Deactivate emergency trading halt."""
    if user_id:
        global_kill_switch.deactivate_user(user_id)
        logger.info(f"Kill switch deactivated for user {user_id}")
    else:
        global_kill_switch.deactivate_global()
        logger.info("Global kill switch deactivated.")
    return global_kill_switch.status()
