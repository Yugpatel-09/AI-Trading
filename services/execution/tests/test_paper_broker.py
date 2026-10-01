import hashlib
import hmac
from datetime import datetime, timedelta, timezone

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
from tradeforge_shared.schemas import OrderProposal, RiskApproval, Signal

from services.execution.gateway.base import (
    ExpiredApprovalError,
    MissingApprovalError,
    ReusedApprovalError,
    TamperedApprovalError,
)
from services.execution.gateway.paper_broker import PaperBroker
from services.risk_guard.guard import RiskGuard


def create_sample_approval(
    secret: str = "test_signing_secret_key_32bytes_long!",
    expired: bool = False,
    idempotency_key: str = "paper_idem_01",
    quantity: int = 50,
) -> RiskApproval:
    now = datetime.now(timezone.utc)
    created_at = now - timedelta(seconds=60) if expired else now
    expires_at = now - timedelta(seconds=10) if expired else now + timedelta(seconds=30)

    approval = RiskApproval(
        approval_id="apr_test_paper_1",
        proposal_hash="hash_test_paper_proposal",
        user_id="usr_01",
        broker=BrokerType.PAPER,
        symbol="NIFTY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        approved_quantity=quantity,
        price=22000.0,
        stop_loss=21950.0,
        target=22080.0,
        idempotency_key=idempotency_key,
        mode=TradingMode.PAPER,
        created_at=created_at,
        expires_at=expires_at,
        signature="",
    )
    sig = hmac.new(
        secret.encode("utf-8"),
        approval.canonical_payload().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    approval.signature = sig
    return approval


@pytest.mark.asyncio
async def test_paper_broker_order_placement_with_valid_risk_approval():
    secret = "test_signing_secret_key_32bytes_long!"
    broker = PaperBroker(initial_capital=200000.0, signing_secret=secret)
    approval = create_sample_approval(secret=secret)

    order = await broker.place_order(approval)
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 50
    assert order.average_fill_price is not None
    assert order.average_fill_price > 0

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_paper_broker_rejects_raw_proposal_bypass():
    broker = PaperBroker()
    sig = Signal(
        id="sig_paper_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22080.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.78,
        expected_net_gain_pct=0.35,
        reason="NIFTY VWAP bounce",
    )
    proposal = OrderProposal(
        idempotency_key="paper_idem_01",
        user_id="usr_01",
        signal=sig,
        requested_quantity=50,
        mode=TradingMode.PAPER,
    )

    with pytest.raises(MissingApprovalError) as exc_info:
        await broker.place_order(proposal)  # Passing raw proposal instead of RiskApproval
    assert "rejects raw proposal" in str(exc_info.value)


@pytest.mark.asyncio
async def test_paper_broker_rejects_tampered_approval():
    secret = "test_signing_secret_key_32bytes_long!"
    broker = PaperBroker(signing_secret=secret)
    approval = create_sample_approval(secret=secret)

    # Tamper with quantity after signing (e.g. attacker changes 50 to 500)
    approval.approved_quantity = 500

    with pytest.raises(TamperedApprovalError) as exc_info:
        await broker.place_order(approval)
    assert "Tampered or forged" in str(exc_info.value)


@pytest.mark.asyncio
async def test_paper_broker_rejects_expired_approval():
    secret = "test_signing_secret_key_32bytes_long!"
    broker = PaperBroker(signing_secret=secret)
    expired_approval = create_sample_approval(secret=secret, expired=True)

    with pytest.raises(ExpiredApprovalError) as exc_info:
        await broker.place_order(expired_approval)
    assert "expired" in str(exc_info.value)


@pytest.mark.asyncio
async def test_paper_broker_rejects_reused_approval():
    secret = "test_signing_secret_key_32bytes_long!"
    broker = PaperBroker(signing_secret=secret)
    approval = create_sample_approval(secret=secret)

    # First execution succeeds
    order1 = await broker.place_order(approval)
    assert order1.status == OrderStatus.FILLED

    # Replay attempt fails
    with pytest.raises(ReusedApprovalError) as exc_info:
        await broker.place_order(approval)
    assert "already been executed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_only_risk_guard_constructs_valid_approval():
    """Verify that RiskGuard constructs a genuine approval accepted by PaperBroker."""
    secret = "shared_risk_signing_secret_32bytes_long!"
    guard = RiskGuard(signing_secret=secret)
    broker = PaperBroker(signing_secret=secret)

    sig = Signal(
        id="sig_paper_guard",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22080.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.8,
        expected_net_gain_pct=0.35,
        reason="Guard integration test",
    )
    from tradeforge_shared.schemas import UserRiskSettings
    user_settings = UserRiskSettings(
        user_id="usr_guard_test",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=2000.0,
        max_daily_loss_inr=5000.0,
    )
    guard.watchdog.record_heartbeat("NIFTY")
    proposal = OrderProposal(
        idempotency_key="guard_appr_idem_01",
        user_id=user_settings.user_id,
        signal=sig,
        requested_quantity=20,
        mode=TradingMode.PAPER,
    )
    result = guard.validate_proposal(proposal, user_settings, current_ltp=22000.0, enforce_trading_hours=False)
    assert result.approved is True
    assert result.approval is not None

    # Paper broker accepts the RiskGuard-signed approval
    order = await broker.place_order(result.approval)
    assert order.status == OrderStatus.FILLED
    assert order.quantity == 20
