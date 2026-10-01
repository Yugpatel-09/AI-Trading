from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from tradeforge_shared.enums import (
    BrokerType,
    MarketRegime,
    OrderSide,
    OrderStatus,
    StrategyType,
    TradingMode,
)
from tradeforge_shared.schemas import ExecutionOrder, OrderProposal, Signal, UserRiskSettings

from services.execution.gateway.base import BrokerGateway
from services.execution.order_manager import (
    InvalidOrderError,
    OrderManager,
    RiskGuardViolationError,
)
from services.risk_guard.guard import RiskGuard


@pytest.fixture
def market_time():
    """Valid trading session timestamp (10:30 IST)."""
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime(2026, 10, 1, 10, 30, 0, tzinfo=ist)


@pytest.fixture
def risk_guard():
    rg = RiskGuard()
    rg.watchdog.record_heartbeat("RELIANCE")
    rg.watchdog.record_heartbeat("NIFTY")
    return rg


@pytest.fixture
def default_user_settings():
    return UserRiskSettings(
        user_id="usr_om_test",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_open_positions=2,
        max_daily_trades=5,
        mode=TradingMode.PAPER,
        auto_stop_after_consecutive_losses=3,
        allowed_instruments=["RELIANCE", "NIFTY"],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )


@pytest.fixture
def sample_proposal():
    signal = Signal(
        id="sig_om_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=2500.0,
        stop_loss=2490.0,  # 10 Rs stop distance
        target=2520.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.85,
        expected_net_gain_pct=0.45,
        reason="Test OrderManager entry",
    )
    return OrderProposal(
        idempotency_key="om_idem_001",
        user_id="usr_om_test",
        signal=signal,
        requested_quantity=50,  # 50 * 10 = ₹500 risk <= ₹1,000 limit
        mode=TradingMode.PAPER,
        broker=BrokerType.PAPER,
    )


@pytest.fixture
def mock_broker_gateway():
    gateway = MagicMock(spec=BrokerGateway)
    order_id = "mock_ord_999"
    now = datetime.now(timezone.utc)
    mock_order = ExecutionOrder(
        order_id=order_id,
        idempotency_key="om_idem_001",
        user_id="usr_om_test",
        broker=BrokerType.PAPER,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type="MARKET",  # type: ignore[arg-type]
        quantity=50,
        price=2500.0,
        stop_loss=2490.0,
        target=2520.0,
        status=OrderStatus.FILLED,
        filled_quantity=50,
        average_fill_price=2500.0,
        created_at=now,
        updated_at=now,
    )
    gateway.place_order = AsyncMock(return_value=mock_order)
    return gateway


@pytest.mark.asyncio
async def test_order_manager_executes_valid_order_with_entry_and_stop(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """Happy Path: OrderManager validates risk and routes entry + stop to broker."""
    om = OrderManager(risk_guard=risk_guard)
    order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )

    assert order.status == OrderStatus.FILLED
    assert order.quantity == 50
    assert order.stop_loss == 2490.0
    assert order.target == 2520.0
    # Verified in internal ledger
    assert om.get_order(order.order_id) is not None


@pytest.mark.asyncio
async def test_order_manager_proves_nothing_bypasses_risk_guard_kill_switch(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """
    CRITICAL SAFETY DRILL (Rule 1):
    Prove that when Risk Guard triggers (Kill Switch), broker is NEVER called.
    """
    risk_guard.kill_switch.activate_global("Emergency Circuit Breaker")
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    with pytest.raises(RiskGuardViolationError) as exc_info:
        await om.submit_order(
            proposal=sample_proposal,
            user_settings=default_user_settings,
            current_ltp=2500.0,
            current_time=market_time,
        )

    assert "Kill switch is active" in str(exc_info.value)
    # Proof: broker.place_order was NEVER invoked
    mock_broker_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_manager_proves_nothing_bypasses_risk_guard_fat_finger(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """
    CRITICAL SAFETY DRILL (Rule 1):
    Fat finger price deviation (>2.5%) blocks broker dispatch.
    """
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    # Price deviates from LTP (2500 vs 2800 -> 12% deviation)
    sample_proposal.signal.entry_price = 2800.0

    with pytest.raises(RiskGuardViolationError) as exc_info:
        await om.submit_order(
            proposal=sample_proposal,
            user_settings=default_user_settings,
            current_ltp=2500.0,
            current_time=market_time,
        )

    assert "Fat-finger check failed" in str(exc_info.value)
    mock_broker_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_manager_proves_nothing_bypasses_risk_guard_stale_feed(
    default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """
    CRITICAL SAFETY DRILL (Rule 1):
    Stale market data feed blocks broker dispatch.
    """
    # Empty risk guard has no heartbeats registered
    empty_guard = RiskGuard()
    om = OrderManager(
        risk_guard=empty_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    with pytest.raises(RiskGuardViolationError) as exc_info:
        await om.submit_order(
            proposal=sample_proposal,
            user_settings=default_user_settings,
            current_ltp=2500.0,
            current_time=market_time,
        )

    assert "feed is stale" in str(exc_info.value).lower()
    mock_broker_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_manager_blocks_entry_without_protective_stop(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """
    CRITICAL SAFETY DRILL (Rule 7):
    Every entry order MUST carry a protective stop. Missing stop is rejected before broker.
    """
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    sample_proposal.signal.stop_loss = 0.0  # Invalid protective stop

    with pytest.raises(InvalidOrderError) as exc_info:
        await om.submit_order(
            proposal=sample_proposal,
            user_settings=default_user_settings,
            current_ltp=2500.0,
            current_time=market_time,
        )

    assert "stop-loss is mandatory" in str(exc_info.value).lower()
    mock_broker_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_manager_enforces_idempotency_prevents_duplicate_broker_calls(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """
    CRITICAL SAFETY DRILL (Rule 8):
    Submitting the same idempotency key twice must NEVER produce duplicate broker orders.
    """
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    # 1. First submission -> broker called once
    order1 = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert mock_broker_gateway.place_order.call_count == 1

    # 2. Duplicate submission with identical key -> broker NOT called again, cached order returned
    order2 = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert mock_broker_gateway.place_order.call_count == 1
    assert order1.order_id == order2.order_id


@pytest.mark.asyncio
async def test_order_manager_downscales_quantity_per_risk_guard(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """
    Risk Guard downsizing: If requested risk exceeds limit, OrderManager passes
    downscaled quantity to the broker.
    """
    # 200 shares * ₹10 stop distance = ₹2,000 risk > ₹1,000 max_loss_per_trade_inr
    sample_proposal.requested_quantity = 200

    om = OrderManager(risk_guard=risk_guard)
    order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )

    # Downsized to 100 shares (100 * ₹10 = ₹1,000)
    assert order.quantity == 100
    assert order.filled_quantity == 100
