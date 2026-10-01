from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from tradeforge_shared.enums import BrokerType, OrderSide


class MismatchType(str, Enum):
    MISSING_INTERNAL_TRADE = "MISSING_INTERNAL_TRADE"
    MISSING_BROKER_TRADE = "MISSING_BROKER_TRADE"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    POSITION_MISMATCH = "POSITION_MISMATCH"


class Discrepancy(BaseModel):
    """Specific mismatch detected between internal ledger and broker statement."""
    model_config = ConfigDict(from_attributes=True)
    mismatch_type: MismatchType
    symbol: str
    trade_or_order_id: str
    internal_value: Any
    broker_value: Any
    detail: str


class TradeRecord(BaseModel):
    """Normalized trade execution record for reconciliation."""
    model_config = ConfigDict(from_attributes=True)
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    timestamp: datetime


class PositionRecord(BaseModel):
    """Normalized position record for end-of-day reconciliation."""
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    net_quantity: int
    average_price: float


class ReconciliationReport(BaseModel):
    """Comprehensive nightly reconciliation audit report."""
    model_config = ConfigDict(from_attributes=True)
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str
    broker: BrokerType
    total_internal_trades: int
    total_broker_trades: int
    matched: bool
    discrepancies: List[Discrepancy] = Field(default_factory=list)
    summary: str


class ReconciliationEngine:
    """
    Nightly Reconciliation Engine.
    Cross-checks internal TradeForge database records against broker tradebooks and position statements.
    Flags any unmatched trades, quantity divergences, price slippage variances, or unclosed overnight positions.
    """
    def __init__(self, price_tolerance_pct: float = 0.005):
        self.price_tolerance_pct = price_tolerance_pct

    def reconcile(
        self,
        user_id: str,
        broker: BrokerType,
        internal_trades: List[TradeRecord],
        broker_trades: List[TradeRecord],
        internal_positions: Optional[List[PositionRecord]] = None,
        broker_positions: Optional[List[PositionRecord]] = None,
    ) -> ReconciliationReport:
        discrepancies: List[Discrepancy] = []

        internal_trade_map: Dict[str, TradeRecord] = {t.order_id: t for t in internal_trades}
        broker_trade_map: Dict[str, TradeRecord] = {t.order_id: t for t in broker_trades}

        # 1. Check for trades in internal ledger missing from broker
        for order_id, it in internal_trade_map.items():
            if order_id not in broker_trade_map:
                discrepancies.append(
                    Discrepancy(
                        mismatch_type=MismatchType.MISSING_BROKER_TRADE,
                        symbol=it.symbol,
                        trade_or_order_id=order_id,
                        internal_value=it.quantity,
                        broker_value=None,
                        detail=f"Trade {order_id} recorded in TradeForge ledger but absent from broker statement.",
                    )
                )
            else:
                bt = broker_trade_map[order_id]
                # Check quantity match
                if it.quantity != bt.quantity:
                    discrepancies.append(
                        Discrepancy(
                            mismatch_type=MismatchType.QUANTITY_MISMATCH,
                            symbol=it.symbol,
                            trade_or_order_id=order_id,
                            internal_value=it.quantity,
                            broker_value=bt.quantity,
                            detail=f"Quantity mismatch for {order_id}: internal={it.quantity}, broker={bt.quantity}.",
                        )
                    )
                # Check price divergence
                price_diff_pct = abs(it.price - bt.price) / it.price if it.price > 0 else 0
                if price_diff_pct > self.price_tolerance_pct:
                    discrepancies.append(
                        Discrepancy(
                            mismatch_type=MismatchType.PRICE_MISMATCH,
                            symbol=it.symbol,
                            trade_or_order_id=order_id,
                            internal_value=it.price,
                            broker_value=bt.price,
                            detail=f"Price mismatch for {order_id}: internal=₹{it.price:.2f}, broker=₹{bt.price:.2f} ({price_diff_pct*100:.2f}% diff).",
                        )
                    )

        # 2. Check for unexpected broker trades not initiated by TradeForge
        for order_id, bt in broker_trade_map.items():
            if order_id not in internal_trade_map:
                discrepancies.append(
                    Discrepancy(
                        mismatch_type=MismatchType.MISSING_INTERNAL_TRADE,
                        symbol=bt.symbol,
                        trade_or_order_id=order_id,
                        internal_value=None,
                        broker_value=bt.quantity,
                        detail=f"Unrecognized trade {order_id} present on broker statement but missing from TradeForge ledger.",
                    )
                )

        # 3. Position Reconciliation (All intraday positions must be squared off to 0)
        if internal_positions and broker_positions:
            int_pos_map = {p.symbol: p.net_quantity for p in internal_positions}
            brk_pos_map = {p.symbol: p.net_quantity for p in broker_positions}
            all_symbols = set(int_pos_map.keys()) | set(brk_pos_map.keys())

            for sym in all_symbols:
                iq = int_pos_map.get(sym, 0)
                bq = brk_pos_map.get(sym, 0)
                if iq != bq:
                    discrepancies.append(
                        Discrepancy(
                            mismatch_type=MismatchType.POSITION_MISMATCH,
                            symbol=sym,
                            trade_or_order_id="EOD_POSITION",
                            internal_value=iq,
                            broker_value=bq,
                            detail=f"End-of-day position mismatch for {sym}: internal={iq}, broker={bq}.",
                        )
                    )

        matched = len(discrepancies) == 0
        summary = (
            f"Reconciliation SUCCESS: {len(internal_trades)} internal trades matched against {len(broker_trades)} broker trades."
            if matched
            else f"Reconciliation ALERT: Found {len(discrepancies)} discrepancy items requiring manual review."
        )

        return ReconciliationReport(
            user_id=user_id,
            broker=broker,
            total_internal_trades=len(internal_trades),
            total_broker_trades=len(broker_trades),
            matched=matched,
            discrepancies=discrepancies,
            summary=summary,
        )
