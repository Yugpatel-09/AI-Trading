from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from tradeforge_shared.enums import (
    BrokerType,
    MarketRegime,
    OrderSide,
    OrderStatus,
    OrderType,
    StrategyType,
    TradingMode,
)
from tradeforge_shared.schemas import (
    ExecutionOrder,
    OrderProposal,
    Signal,
    UserRiskSettings,
)

from services.execution.gateway.base import BrokerGateway
from services.execution.order_manager import (
    InvalidOrderError,
    OrderApprovalTimeoutError,
    OrderManager,
    RiskGuardViolationError,
    StopPlacementFailureError,
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
        order_type=OrderType.MARKET,
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
    mock_stop = ExecutionOrder(
        order_id="mock_sl_999",
        idempotency_key="sl_mock_ord_999",
        user_id="usr_om_test",
        broker=BrokerType.PAPER,
        symbol="RELIANCE",
        side=OrderSide.SELL,
        order_type=OrderType.SL_M,
        quantity=50,
        price=2490.0,
        stop_loss=2490.0,
        target=0.0,
        status=OrderStatus.SUBMITTED,
        filled_quantity=0,
        created_at=now,
        updated_at=now,
    )
    gateway.place_order = AsyncMock(return_value=mock_order)
    gateway.place_stop_order = AsyncMock(return_value=mock_stop)
    gateway.flatten_position = AsyncMock()
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
    assert om.get_order(order.order_id) is not None


@pytest.mark.asyncio
async def test_order_manager_proves_nothing_bypasses_risk_guard_kill_switch(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """CRITICAL SAFETY DRILL (Rule 1): Prove broker is NEVER called when kill switch is active."""
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
    mock_broker_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_manager_proves_nothing_bypasses_risk_guard_fat_finger(
    risk_guard, default_user_settings, sample_proposal, mock_broker_gateway, market_time
):
    """CRITICAL SAFETY DRILL (Rule 1): Fat finger price deviation blocks broker dispatch."""
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

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
    """CRITICAL SAFETY DRILL (Rule 1): Stale market data feed blocks broker dispatch."""
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
    """CRITICAL SAFETY DRILL (Rule 7): Every entry order MUST carry a protective stop."""
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    sample_proposal.signal.stop_loss = 0.0

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
    """CRITICAL SAFETY DRILL (Rule 8): Submitting duplicate key returns cached order without broker recall."""
    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_broker_gateway},
    )

    order1 = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert mock_broker_gateway.place_order.call_count == 1

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
    """Risk Guard downsizing: If requested risk exceeds limit, OrderManager downscales."""
    sample_proposal.requested_quantity = 200

    om = OrderManager(risk_guard=risk_guard)
    order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )

    assert order.quantity == 100
    assert order.filled_quantity == 100


@pytest.mark.asyncio
async def test_order_manager_approve_mode_gate(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """WP-B: APPROVE mode holds order until explicit user confirmation."""
    sample_proposal.mode = TradingMode.APPROVE
    om = OrderManager(risk_guard=risk_guard, approval_timeout_seconds=60)

    # 1. Submission puts order into pending approval
    pending_order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert pending_order.status == OrderStatus.PENDING_USER_APPROVAL
    pending_id = pending_order.order_id

    # 2. User confirms/approves order
    executed_order = await om.confirm_pending_order(
        pending_id=pending_id,
        user_id=default_user_settings.user_id,
        action="APPROVE",
        current_time=market_time,
    )
    assert executed_order.status == OrderStatus.FILLED
    assert executed_order.quantity == 50


@pytest.mark.asyncio
async def test_order_manager_approve_mode_expiry_timeout(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """WP-B: APPROVE mode times out and refuses execution if confirmed after expiry."""
    sample_proposal.mode = TradingMode.APPROVE
    om = OrderManager(risk_guard=risk_guard, approval_timeout_seconds=30)

    pending_order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )

    # Fast forward 45 seconds later (past 30s timeout)
    expired_time = market_time + timedelta(seconds=45)
    with pytest.raises(OrderApprovalTimeoutError) as exc_info:
        await om.confirm_pending_order(
            pending_id=pending_order.order_id,
            user_id=default_user_settings.user_id,
            action="APPROVE",
            current_time=expired_time,
        )
    assert "timed out and expired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_order_manager_protective_stop_failure_emergency_flatten(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """
    WP-B: Protective-stop confirmation.
    If the stop fails to place on the broker, FLATTEN the entry immediately.
    """
    mock_gateway = MagicMock(spec=BrokerGateway)
    now = datetime.now(timezone.utc)
    entry_fill = ExecutionOrder(
        order_id="ord_entry_fill_01",
        idempotency_key="om_idem_001",
        user_id="usr_om_test",
        broker=BrokerType.PAPER,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
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
    mock_gateway.place_order = AsyncMock(return_value=entry_fill)
    # Stop placement fails
    mock_gateway.place_stop_order = AsyncMock(side_effect=RuntimeError("Exchange Margin Exhaustion"))
    mock_gateway.flatten_position = AsyncMock(return_value=MagicMock())

    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_gateway},
    )

    with pytest.raises(StopPlacementFailureError) as exc_info:
        await om.submit_order(
            proposal=sample_proposal,
            user_settings=default_user_settings,
            current_ltp=2500.0,
            current_time=market_time,
        )

    assert "Protective stop placement failed" in str(exc_info.value)
    # Emergency flatten was called immediately for the exact filled quantity and opposite side (SELL)
    mock_gateway.flatten_position.assert_called_once_with(
        user_id="usr_om_test",
        symbol="RELIANCE",
        side=OrderSide.SELL,
        quantity=50,
        reason="STOP_LOSS_FAILED: Exchange Margin Exhaustion",
    )


@pytest.mark.asyncio
async def test_order_manager_exponential_backoff_retry(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """WP-B: Transient network errors trigger retries with exponential backoff."""
    mock_gateway = MagicMock(spec=BrokerGateway)
    now = datetime.now(timezone.utc)
    success_order = ExecutionOrder(
        order_id="ord_retry_success",
        idempotency_key="om_idem_001",
        user_id="usr_om_test",
        broker=BrokerType.PAPER,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
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
    mock_gateway.place_stop_order = AsyncMock()
    # Fails twice with network timeout, then succeeds on 3rd attempt
    mock_gateway.place_order = AsyncMock(
        side_effect=[
            ConnectionResetError("Socket reset by peer"),
            TimeoutError("Broker read timeout"),
            success_order,
        ]
    )

    om = OrderManager(
        risk_guard=risk_guard,
        gateways={BrokerType.PAPER: mock_gateway},
    )

    order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert order.status == OrderStatus.FILLED
    assert mock_gateway.place_order.call_count == 3


@pytest.mark.asyncio
async def test_order_manager_state_persistence_and_recovery(
    risk_guard, default_user_settings, sample_proposal, market_time
):
    """WP-B: Crash recovery restores order and idempotency state."""
    om = OrderManager(risk_guard=risk_guard)
    order = await om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )

    # Take snapshot
    snapshot = om.snapshot_state()

    # Simulate server crash by spawning new OrderManager instance
    new_om = OrderManager(risk_guard=risk_guard)
    assert new_om.get_order(order.order_id) is None

    # Recover state
    new_om.recover_state(snapshot)
    recovered_order = new_om.get_order(order.order_id)
    assert recovered_order is not None
    assert recovered_order.order_id == order.order_id
    assert recovered_order.symbol == "RELIANCE"

    # Verify idempotency key is preserved post-recovery
    dup_order = await new_om.submit_order(
        proposal=sample_proposal,
        user_settings=default_user_settings,
        current_ltp=2500.0,
        current_time=market_time,
    )
    assert dup_order.order_id == order.order_id
