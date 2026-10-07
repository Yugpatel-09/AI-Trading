from typing import Set

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_shared.enums import TradingMode
from tradeforge_shared.schemas import UserRiskSettings

from services.api.app.db.repositories.risk_repo import RiskRepository

# Platform-level invariants that cannot be bypassed by any user
PLATFORM_BLOCKED_SYMBOLS: Set[str] = {
    "IDEA", "YESBANK", "SUZLON", "RCOM", "JPPOWER"
}
PLATFORM_MAX_DAILY_LOSS_CEILING_INR = 50000.0
PLATFORM_MAX_PER_TRADE_LOSS_CEILING_INR = 15000.0
PLATFORM_MAX_OPEN_POSITIONS_LIMIT = 5
PLATFORM_MAX_DAILY_TRADES_LIMIT = 20
PLATFORM_MAX_CONSECUTIVE_LOSS_LIMIT = 5


def get_default_user_risk_settings(user_id: str) -> UserRiskSettings:
    """Instantiate conservative default risk settings for a new user."""
    return UserRiskSettings(
        user_id=user_id,
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_open_positions=2,
        max_daily_trades=8,
        mode=TradingMode.PAPER,
        auto_stop_after_consecutive_losses=3,
        allowed_instruments=["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY"],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )


async def get_user_risk_settings(user_id: str, session: AsyncSession) -> UserRiskSettings:
    """Retrieve user risk limits from database, returning defaults if none stored."""
    repo = RiskRepository(session)
    return await repo.get_by_user_id(user_id)


async def update_user_risk_settings(
    user_id: str, new_settings: UserRiskSettings, session: AsyncSession
) -> UserRiskSettings:
    """
    Update user risk settings after enforcing platform-level safety guardrails.
    Prevents client-side limit tampering or unsafe risk parameter expansion.
    """
    if new_settings.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id in settings payload does not match authenticated user.",
        )

    # 1. Loss per trade vs daily loss check
    if new_settings.max_loss_per_trade_inr > new_settings.max_daily_loss_inr:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Per-trade loss limit cannot exceed daily loss limit.",
        )

    # 2. Daily loss ceiling check
    if new_settings.max_daily_loss_inr > PLATFORM_MAX_DAILY_LOSS_CEILING_INR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Daily loss limit cannot exceed platform ceiling of ₹{PLATFORM_MAX_DAILY_LOSS_CEILING_INR:,.2f}.",
        )

    # 3. Per trade loss ceiling check
    if new_settings.max_loss_per_trade_inr > PLATFORM_MAX_PER_TRADE_LOSS_CEILING_INR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Per-trade loss limit cannot exceed platform ceiling of ₹{PLATFORM_MAX_PER_TRADE_LOSS_CEILING_INR:,.2f}.",
        )

    # 4. Position count and trade count checks
    if not (1 <= new_settings.max_open_positions <= PLATFORM_MAX_OPEN_POSITIONS_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max open positions must be between 1 and {PLATFORM_MAX_OPEN_POSITIONS_LIMIT}.",
        )

    if not (1 <= new_settings.max_daily_trades <= PLATFORM_MAX_DAILY_TRADES_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max daily trades must be between 1 and {PLATFORM_MAX_DAILY_TRADES_LIMIT}.",
        )

    if not (1 <= new_settings.auto_stop_after_consecutive_losses <= PLATFORM_MAX_CONSECUTIVE_LOSS_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Consecutive loss auto-stop must be between 1 and {PLATFORM_MAX_CONSECUTIVE_LOSS_LIMIT}.",
        )

    # 5. Blocked instruments check
    for sym in new_settings.allowed_instruments:
        if sym.upper() in PLATFORM_BLOCKED_SYMBOLS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Symbol {sym.upper()} is on platform risk blocklist and cannot be added.",
            )

    repo = RiskRepository(session)
    return await repo.save_settings(new_settings)
