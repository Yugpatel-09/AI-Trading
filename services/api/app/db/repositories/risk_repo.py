from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_shared.enums import TradingMode
from tradeforge_shared.schemas import UserRiskSettings

from services.api.app.db.models import UserRiskSettingsModel


class RiskRepository:
    """Repository managing UserRiskSettings persistent storage."""
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> UserRiskSettings:
        stmt = select(UserRiskSettingsModel).where(UserRiskSettingsModel.user_id == user_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        if not record:
            # Default institutional settings for new user
            return UserRiskSettings(user_id=user_id)

        return UserRiskSettings(
            user_id=record.user_id,
            capital_allocated_inr=record.capital_allocated_inr,
            max_loss_per_trade_inr=record.max_loss_per_trade_inr,
            max_daily_loss_inr=record.max_daily_loss_inr,
            max_open_positions=record.max_open_positions,
            max_daily_trades=record.max_daily_trades,
            mode=TradingMode(record.mode),
            auto_stop_after_consecutive_losses=record.auto_stop_after_consecutive_losses,
            allowed_instruments=list(record.allowed_instruments),
            trading_start_time_ist=record.trading_start_time_ist,
            trading_end_time_ist=record.trading_end_time_ist,
        )

    async def save_settings(self, settings: UserRiskSettings) -> UserRiskSettings:
        stmt = select(UserRiskSettingsModel).where(UserRiskSettingsModel.user_id == settings.user_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record:
            record.capital_allocated_inr = settings.capital_allocated_inr
            record.max_loss_per_trade_inr = settings.max_loss_per_trade_inr
            record.max_daily_loss_inr = settings.max_daily_loss_inr
            record.max_open_positions = settings.max_open_positions
            record.max_daily_trades = settings.max_daily_trades
            record.mode = settings.mode.value
            record.auto_stop_after_consecutive_losses = settings.auto_stop_after_consecutive_losses
            record.allowed_instruments = list(settings.allowed_instruments)
            record.trading_start_time_ist = settings.trading_start_time_ist
            record.trading_end_time_ist = settings.trading_end_time_ist
            record.updated_at = now
        else:
            record = UserRiskSettingsModel(
                user_id=settings.user_id,
                capital_allocated_inr=settings.capital_allocated_inr,
                max_loss_per_trade_inr=settings.max_loss_per_trade_inr,
                max_daily_loss_inr=settings.max_daily_loss_inr,
                max_open_positions=settings.max_open_positions,
                max_daily_trades=settings.max_daily_trades,
                mode=settings.mode.value,
                auto_stop_after_consecutive_losses=settings.auto_stop_after_consecutive_losses,
                allowed_instruments=list(settings.allowed_instruments),
                trading_start_time_ist=settings.trading_start_time_ist,
                trading_end_time_ist=settings.trading_end_time_ist,
                updated_at=now,
            )
            self.session.add(record)

        await self.session.flush()
        return settings
