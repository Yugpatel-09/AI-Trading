from datetime import datetime, timezone

from tradeforge_shared.enums import BrokerType, OrderSide

from services.execution.reconciliation.reconciler import (
    MismatchType,
    PositionRecord,
    ReconciliationEngine,
    TradeRecord,
)


def test_reconciliation_perfect_match():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine()

    internal_trades = [
        TradeRecord(trade_id="t1", order_id="ord_1", symbol="NIFTY", side=OrderSide.BUY, quantity=50, price=22000.0, timestamp=now),
        TradeRecord(trade_id="t2", order_id="ord_2", symbol="RELIANCE", side=OrderSide.BUY, quantity=20, price=2500.0, timestamp=now),
    ]
    broker_trades = [
        TradeRecord(trade_id="bt1", order_id="ord_1", symbol="NIFTY", side=OrderSide.BUY, quantity=50, price=22000.0, timestamp=now),
        TradeRecord(trade_id="bt2", order_id="ord_2", symbol="RELIANCE", side=OrderSide.BUY, quantity=20, price=2500.0, timestamp=now),
    ]

    report = engine.reconcile(
        user_id="usr_01",
        broker=BrokerType.PAPER,
        internal_trades=internal_trades,
        broker_trades=broker_trades,
    )
    assert report.matched is True
    assert len(report.discrepancies) == 0
    assert "SUCCESS" in report.summary


def test_reconciliation_detects_mismatches():
    now = datetime.now(timezone.utc)
    engine = ReconciliationEngine(price_tolerance_pct=0.001)

    internal_trades = [
        # Quantity mismatch: internal 50 vs broker 30
        TradeRecord(trade_id="t1", order_id="ord_qty", symbol="NIFTY", side=OrderSide.BUY, quantity=50, price=22000.0, timestamp=now),
        # Missing on broker
        TradeRecord(trade_id="t2", order_id="ord_missing_broker", symbol="TCS", side=OrderSide.BUY, quantity=10, price=3800.0, timestamp=now),
        # Price mismatch: 2500 vs 2550
        TradeRecord(trade_id="t3", order_id="ord_price", symbol="RELIANCE", side=OrderSide.BUY, quantity=20, price=2500.0, timestamp=now),
    ]

    broker_trades = [
        TradeRecord(trade_id="bt1", order_id="ord_qty", symbol="NIFTY", side=OrderSide.BUY, quantity=30, price=22000.0, timestamp=now),
        TradeRecord(trade_id="bt3", order_id="ord_price", symbol="RELIANCE", side=OrderSide.BUY, quantity=20, price=2550.0, timestamp=now),
        # Missing on internal (rogue broker trade)
        TradeRecord(trade_id="bt_rogue", order_id="ord_rogue", symbol="INFY", side=OrderSide.BUY, quantity=15, price=1800.0, timestamp=now),
    ]

    internal_positions = [PositionRecord(symbol="NIFTY", net_quantity=0, average_price=0.0)]
    broker_positions = [PositionRecord(symbol="NIFTY", net_quantity=20, average_price=22000.0)]

    report = engine.reconcile(
        user_id="usr_01",
        broker=BrokerType.ZERODHA,
        internal_trades=internal_trades,
        broker_trades=broker_trades,
        internal_positions=internal_positions,
        broker_positions=broker_positions,
    )

    assert report.matched is False
    assert len(report.discrepancies) == 5

    mismatch_types = {d.mismatch_type for d in report.discrepancies}
    assert MismatchType.QUANTITY_MISMATCH in mismatch_types
    assert MismatchType.MISSING_BROKER_TRADE in mismatch_types
    assert MismatchType.PRICE_MISMATCH in mismatch_types
    assert MismatchType.MISSING_INTERNAL_TRADE in mismatch_types
    assert MismatchType.POSITION_MISMATCH in mismatch_types
