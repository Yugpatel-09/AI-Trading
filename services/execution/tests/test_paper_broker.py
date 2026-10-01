import pytest
from datetime import datetime, timezone
from tradeforge_shared.enums import TradingMode, OrderSide, StrategyType, MarketRegime, OrderStatus
from tradeforge_shared.schemas import Signal, OrderProposal
from services.execution.gateway.paper_broker import PaperBroker

@pytest.mark.asyncio
async def test_paper_broker_order_placement_and_fill():
    broker = PaperBroker(initial_capital=200000.0)
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

    order = await broker.place_order(proposal, approved_quantity=50)
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 50
    assert order.average_fill_price is not None
    assert order.average_fill_price > 0

    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "NIFTY"
