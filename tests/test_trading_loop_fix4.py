"""
FIX-4 Verification Test: Trading Loop Runner End-to-End Replay.
Replays one full synthetic trading day of 1-minute candles (09:15 to 15:30 IST = 375 candles)
through TradingLoopRunner -> FeatureStore -> Strategy -> RiskGuard -> OrderManager -> PaperBroker,
and verifies that all orders, fills, positions, trades, and audit logs are persisted in the database.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tradeforge_shared.enums import BrokerType, MarketRegime, OrderStatus, TradingMode
from tradeforge_shared.schemas import Candle, UserRiskSettings

from services.api.app.core.config import settings
from services.api.app.db.models import (
    AuditLogModel,
    Base,
    ExecutionOrderModel,
    FillModel,
    PositionModel,
    TradeModel,
)
from services.api.app.db.repositories.user_repo import UserRepository
from services.engine.data_feed.resampler import IST
from services.engine.regime.classifier import RegimeDetector
from services.engine.runner import HistoricalReplayProvider, TradingLoopRunner
from services.engine.strategies.scalper_1m import Scalper1M
from services.execution.gateway.paper_broker import PaperBroker
from services.execution.order_manager import OrderManager
from services.risk_guard.guard import RiskGuard


class AlwaysBullishRegimeDetector(RegimeDetector):
    """Fixture regime detector to ensure repeatable trend classification for test runs."""
    def classify_regime(self, candles, index_direction=None, index_candles=None):
        return MarketRegime.TRENDING_BULLISH


def generate_full_day_candles(
    symbol: str = "NIFTY",
    start_price: float = 22000.0,
) -> list[Candle]:
    """
    Generate 375 1-minute candles representing a full NSE trading day (09:15 to 15:30 IST).
    Includes a strong early bullish trend with a VWAP pullback around 09:35 IST to trigger Scalper1M,
    followed by a rally that hits target.
    """
    start_dt = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    candles: list[Candle] = []
    p = start_price

    for minute in range(375):
        t = start_dt + timedelta(minutes=minute)

        if minute < 24:
            change = 0.0002
            vol = 2000
            o = round(p, 2)
            c = round(o * (1 + change), 2)
            h = round(max(o, c) + 3.0, 2)
            low_val = round(min(o, c) - 2.0, 2)
        elif minute == 24:
            # Candle 24: intra-candle dip below VWAP, but close stays healthy above VWAP
            o = round(p, 2)
            c = round(o + 2.0, 2)
            h = round(c + 3.0, 2)
            low_val = round(22000.0, 2)  # deep dip below VWAP (VWAP is ~22050)
            vol = 2000
        elif minute == 25:
            # Candle 25: rebound back above VWAP with volume surge (triggers Scalper1M)
            o = round(p, 2)
            c = round(o + 20.0, 2)
            h = round(c + 3.0, 2)
            low_val = round(o - 1.0, 2)
            vol = 15000
        elif 25 < minute < 45:
            # Strong continuation upward hitting profit target
            change = 0.001
            vol = 4000
            o = round(p, 2)
            c = round(o * (1 + change), 2)
            h = round(max(o, c) + 3.0, 2)
            low_val = round(min(o, c) - 2.0, 2)
        else:
            # Rest of day
            change = 0.00005 if minute % 2 == 0 else -0.00004
            vol = 2000
            o = round(p, 2)
            c = round(o * (1 + change), 2)
            h = round(max(o, c) + 3.0, 2)
            low_val = round(min(o, c) - 2.0, 2)

        vwap = round((h + low_val + c) / 3.0, 2)

        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                timestamp=t,
                open=o,
                high=h,
                low=low_val,
                close=c,
                volume=vol,
                vwap=vwap,
            )
        )
        p = c

    return candles


@pytest.mark.asyncio
async def test_trading_loop_end_to_end_replay_and_persistence(tmp_path):
    """
    FIX-4 End-to-End Verification:
    Replays a full 375-minute day through TradingLoopRunner,
    verifying signals -> orders -> fills -> positions -> trades -> audit log in DB.
    """
    db_file = tmp_path / "trading_loop_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 1. Seed user in isolated DB
    async with session_maker() as session:
        u_repo = UserRepository(session)
        user = await u_repo.create_user("loop_trader@tradeforge.io", "StrongP@ss2026!", email_verified=True)
        await session.commit()
        user_id = user.id

    # 2. Risk Settings
    user_settings = UserRiskSettings(
        user_id=user_id,
        capital_allocated_inr=500000.0,
        max_loss_per_trade_inr=5000.0,
        max_daily_loss_inr=15000.0,
        max_open_positions=2,
        max_daily_trades=10,
        mode=TradingMode.PAPER,
        allowed_instruments=["NIFTY", "BANKNIFTY"],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )

    # 3. Create full-day candle fixture (375 1m candles)
    candles = generate_full_day_candles("NIFTY", start_price=22000.0)
    assert len(candles) == 375
    replay_provider = HistoricalReplayProvider(candles)

    # 4. Strategy with bullish regime detector
    strategy = Scalper1M(
        target_pct=0.0025,
        stop_atr_mult=0.8,
        regime_detector=AlwaysBullishRegimeDetector(),
    )

    # 5. RiskGuard & OrderManager with PaperBroker slippage and spread
    risk_guard = RiskGuard(signing_secret=settings.SECRET_KEY)
    paper_broker = PaperBroker(
        initial_capital=500000.0,
        signing_secret=settings.SECRET_KEY,
        slippage_bps=2.0,
        spread_bps=1.0,
    )
    order_manager = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: paper_broker},
    )

    # 6. Initialize Runner
    runner = TradingLoopRunner(
        provider=replay_provider,
        strategies=[strategy],
        user_settings=user_settings,
        session_factory=session_maker,
        order_manager=order_manager,
        risk_guard=risk_guard,
        symbol="NIFTY",
        lot_size=25,
        slippage_bps=2.0,
        spread_bps=1.0,
    )

    # 7. Execute Trading Loop
    summary = await runner.run()

    # --- ASSERTIONS ---
    assert summary["candles_processed"] == 375
    assert summary["orders_placed"] > 0, "Trading loop must have placed at least one order"
    assert summary["trades_completed"] > 0, "Trading loop must have completed at least one trade"
    assert summary["total_costs"] > 0, "Indian statutory costs must be modeled and > 0"

    # 8. Verify DB Persistence
    async with session_maker() as session:
        # Check Orders persisted
        order_stmt = select(ExecutionOrderModel).where(ExecutionOrderModel.user_id == user_id)
        orders = (await session.execute(order_stmt)).scalars().all()
        assert len(orders) == summary["orders_placed"]
        for o in orders:
            assert o.status in (OrderStatus.FILLED.value, OrderStatus.PARTIAL_FILL.value)
            assert o.symbol == "NIFTY"
            assert o.quantity == 25
            assert o.average_fill_price is not None
            assert o.average_fill_price > 0

        # Check Fills persisted
        fill_stmt = select(FillModel).where(FillModel.user_id == user_id)
        fills = (await session.execute(fill_stmt)).scalars().all()
        assert len(fills) >= len(orders)
        for f in fills:
            assert f.symbol == "NIFTY"
            assert f.filled_quantity == 25
            assert f.fill_price > 0

        # Check Trades persisted
        trade_stmt = select(TradeModel).where(TradeModel.user_id == user_id)
        trades = (await session.execute(trade_stmt)).scalars().all()
        assert len(trades) == summary["trades_completed"]
        for t in trades:
            assert t.symbol == "NIFTY"
            assert t.quantity == 25
            assert t.entry_price > 0
            assert t.exit_price > 0
            assert t.total_costs > 0  # Cost breakdown modeled
            assert round(t.net_pnl, 2) == round(t.gross_pnl - t.total_costs, 2)

        # Check Position persisted
        pos_stmt = select(PositionModel).where(PositionModel.user_id == user_id)
        positions = (await session.execute(pos_stmt)).scalars().all()
        assert len(positions) > 0

        # Check Audit Log entries persisted
        audit_stmt = select(AuditLogModel).where(AuditLogModel.user_id == user_id)
        audit_logs = (await session.execute(audit_stmt)).scalars().all()
        assert len(audit_logs) >= 2
        actions = [log.action for log in audit_logs]
        assert "ORDER_EXECUTED" in actions
        assert "POSITION_CLOSED" in actions

    await engine.dispose()
