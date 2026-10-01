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
from tradeforge_shared.schemas import ExecutionOrder, OrderProposal, Signal, UserRiskSettings

from services.execution.gateway.base import BrokerGateway
from services.execution.order_manager import (
    OrderManager,
    RiskGuardViolationError,
    StopPlacementFailureError,
)
from services.risk_guard.guard import RiskGuard
from services.risk_guard.kill_switch import KillSwitch
from services.risk_guard.watchdog import FeedWatchdog


@pytest.fixture
def order_path_fixture():
    ist = timezone(timedelta(hours=5, minutes=30))
    market_time = datetime(2026, 10, 1, 10, 30, 0, tzinfo=ist)

    ks = KillSwitch()
    wd = FeedWatchdog(max_staleness_ms=5000)
    wd.record_heartbeat("RELIANCE", timestamp=market_time)
    wd.record_heartbeat("NIFTY", timestamp=market_time)

    guard = RiskGuard(kill_switch=ks, watchdog=wd)

    user_settings = UserRiskSettings(
        user_id="drill_chain_user",
        capital_allocated_inr=200000.0,
        max_loss_per_trade_inr=2000.0,
        max_daily_loss_inr=6000.0,
        max_open_positions=3,
        max_daily_trades=10,
        mode=TradingMode.PAPER,
        allowed_instruments=["RELIANCE", "NIFTY"],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )

    sig = Signal(
        id="sig_chain_drill_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=market_time,
        entry_price=2500.0,
        stop_loss=2480.0,  # 20 Rs stop distance
        target=2540.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.82,
        expected_net_gain_pct=0.45,
        reason="Chain failure drill signal",
    )

    proposal = OrderProposal(
        idempotency_key="idemp_chain_drill_01",
        user_id=user_settings.user_id,
        signal=sig,
        requested_quantity=50,  # 50 * 20 = ₹1,000 risk <= ₹2,000 limit
        mode=TradingMode.PAPER,
        broker=BrokerType.PAPER,
    )

    return guard, ks, wd, user_settings, proposal, market_time


@pytest.mark.asyncio
async def test_chain_drill_1_dead_feed(order_path_fixture):
    """
    FAILURE DRILL 1: Dead/Stale Feed through real chain.
    FeedWatchdog detects staleness (>5000ms). OrderManager rejects via Risk Guard.
    Gateway is NEVER invoked.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    # Set feed heartbeat to 10 seconds in the past
    stale_time = market_time - timedelta(seconds=10)
    wd.record_heartbeat("RELIANCE", timestamp=stale_time)

    mock_gateway = MagicMock(spec=BrokerGateway)
    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})

    with pytest.raises(RiskGuardViolationError) as exc_info:
        await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)

    assert "feed is stale or unavailable" in str(exc_info.value).lower()
    mock_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_chain_drill_2_broker_down(order_path_fixture):
    """
    FAILURE DRILL 2: Broker Down through real chain.
    Broker gateway connection drops. OrderManager retries with backoff and fails safely.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    mock_gateway = MagicMock(spec=BrokerGateway)
    # Simulate connection dropout across all retries
    mock_gateway.place_order = AsyncMock(side_effect=ConnectionRefusedError("Broker gateway unreachable"))

    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})

    with pytest.raises(RuntimeError) as exc_info:
        await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)

    assert "Broker gateway call failed after 3 attempts" in str(exc_info.value)
    # Proves exponential backoff retried exactly 3 times
    assert mock_gateway.place_order.call_count == 3


@pytest.mark.asyncio
async def test_chain_drill_3_duplicate_signals(order_path_fixture):
    """
    FAILURE DRILL 3: Duplicate Signals through real chain.
    Network replay / duplicate signal with same idempotency key is submitted.
    OrderManager intercepts and blocks duplicate broker execution.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    mock_gateway = MagicMock(spec=BrokerGateway)
    now = datetime.now(timezone.utc)
    mock_order = ExecutionOrder(
        order_id="ord_chain_dup_1",
        idempotency_key=proposal.idempotency_key,
        user_id=proposal.user_id,
        broker=BrokerType.PAPER,
        symbol=proposal.signal.symbol,
        side=proposal.signal.side,
        order_type=OrderType.MARKET,
        quantity=50,
        price=2500.0,
        stop_loss=2480.0,
        target=2540.0,
        status=OrderStatus.FILLED,
        filled_quantity=50,
        average_fill_price=2500.0,
        created_at=now,
        updated_at=now,
    )
    mock_gateway.place_order = AsyncMock(return_value=mock_order)
    mock_gateway.place_stop_order = AsyncMock()

    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})

    # First attempt: succeeds
    res1 = await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)
    assert res1.status == OrderStatus.FILLED
    assert mock_gateway.place_order.call_count == 1

    # Second attempt (duplicate signal): returns cached order, zero extra broker calls
    res2 = await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)
    assert res2.order_id == res1.order_id
    assert mock_gateway.place_order.call_count == 1


@pytest.mark.asyncio
async def test_chain_drill_4_server_crash_mid_order_recovery(order_path_fixture):
    """
    FAILURE DRILL 4: Server Crash Mid-Order through real chain.
    OrderManager executes an order, crashes, restarts, and restores state.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    om = OrderManager(risk_guard=guard)
    order = await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)
    assert order.status == OrderStatus.FILLED

    # Take snapshot (in production, saved to PostgreSQL/Redis)
    crash_snapshot = om.snapshot_state()

    # CRASH: Process dies and restarts with clean memory
    rebooted_om = OrderManager(risk_guard=guard)
    assert rebooted_om.get_order(order.order_id) is None

    # RECOVER: Hydrate from snapshot
    rebooted_om.recover_state(crash_snapshot)
    recovered = rebooted_om.get_order(order.order_id)
    assert recovered is not None
    assert recovered.order_id == order.order_id

    # Verify post-crash duplicate signal rejection
    dup_res = await rebooted_om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)
    assert dup_res.order_id == order.order_id


@pytest.mark.asyncio
async def test_chain_drill_5_stale_data_fat_finger(order_path_fixture):
    """
    FAILURE DRILL 5: Stale / Wild Price Tick (Fat Finger).
    Price deviates 5% from LTP. OrderManager blocks before broker dispatch.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    mock_gateway = MagicMock(spec=BrokerGateway)
    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})

    # Signal price is 2650 when LTP is 2500 (6% deviation > 2.5% platform limit)
    proposal.signal.entry_price = 2650.0

    with pytest.raises(RiskGuardViolationError) as exc_info:
        await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)

    assert "fat-finger check failed" in str(exc_info.value).lower()
    mock_gateway.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_chain_drill_6_partial_fill(order_path_fixture):
    """
    FAILURE DRILL 6: Partial Fill through real chain.
    Broker fills only 20 shares out of 50 requested.
    OrderManager adjusts protective stop placement to cover exactly the filled 20 shares.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    mock_gateway = MagicMock(spec=BrokerGateway)
    now = datetime.now(timezone.utc)
    partial_fill_order = ExecutionOrder(
        order_id="ord_partial_fill_01",
        idempotency_key=proposal.idempotency_key,
        user_id=proposal.user_id,
        broker=BrokerType.PAPER,
        symbol=proposal.signal.symbol,
        side=proposal.signal.side,
        order_type=OrderType.MARKET,
        quantity=50,
        price=2500.0,
        stop_loss=2480.0,
        target=2540.0,
        status=OrderStatus.PARTIAL_FILL,
        filled_quantity=20,  # Only 20 filled
        average_fill_price=2500.0,
        created_at=now,
        updated_at=now,
    )
    mock_gateway.place_order = AsyncMock(return_value=partial_fill_order)
    mock_gateway.place_stop_order = AsyncMock()

    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})
    res = await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)

    assert res.status == OrderStatus.PARTIAL_FILL
    assert res.filled_quantity == 20

    # Rule 7: Protective stop must be placed for exactly the 20 filled shares!
    mock_gateway.place_stop_order.assert_called_once_with(
        user_id=proposal.user_id,
        symbol="RELIANCE",
        side=OrderSide.SELL,
        quantity=20,
        stop_price=2480.0,
        parent_order_id="ord_partial_fill_01",
    )


@pytest.mark.asyncio
async def test_chain_drill_7_stop_placement_failure_emergency_flatten(order_path_fixture):
    """
    FAILURE DRILL 7: Protective-Stop Placement Failure through real chain.
    Entry fills, but broker rejects the protective stop.
    OrderManager immediately triggers an emergency flatten market order to neutralize exposure.
    """
    guard, ks, wd, user_settings, proposal, market_time = order_path_fixture

    mock_gateway = MagicMock(spec=BrokerGateway)
    now = datetime.now(timezone.utc)
    entry_fill = ExecutionOrder(
        order_id="ord_entry_filled",
        idempotency_key=proposal.idempotency_key,
        user_id=proposal.user_id,
        broker=BrokerType.PAPER,
        symbol=proposal.signal.symbol,
        side=proposal.signal.side,
        order_type=OrderType.MARKET,
        quantity=50,
        price=2500.0,
        stop_loss=2480.0,
        target=2540.0,
        status=OrderStatus.FILLED,
        filled_quantity=50,
        average_fill_price=2500.0,
        created_at=now,
        updated_at=now,
    )
    mock_gateway.place_order = AsyncMock(return_value=entry_fill)
    # Broker rejects stop order
    mock_gateway.place_stop_order = AsyncMock(side_effect=RuntimeError("RMS: Stop-Loss Margin Disallowed"))
    mock_gateway.flatten_position = AsyncMock()

    om = OrderManager(risk_guard=guard, gateways={BrokerType.PAPER: mock_gateway})

    with pytest.raises(StopPlacementFailureError) as exc_info:
        await om.submit_order(proposal, user_settings, current_ltp=2500.0, current_time=market_time)

    assert "Protective stop placement failed" in str(exc_info.value)
    # Proof: Emergency flatten order executed on opposite side (SELL) for 50 shares
    mock_gateway.flatten_position.assert_called_once_with(
        user_id=proposal.user_id,
        symbol="RELIANCE",
        side=OrderSide.SELL,
        quantity=50,
        reason="STOP_LOSS_FAILED: RMS: Stop-Loss Margin Disallowed",
    )
