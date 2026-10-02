from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_shared.enums import BrokerType, OrderSide, OrderStatus, OrderType
from tradeforge_shared.schemas import ExecutionOrder

from services.api.app.db.models import (
    ExecutionOrderModel,
    FillModel,
    PositionModel,
    TradeModel,
)


class OrderRepository:
    """Repository managing Orders, Fills, Positions, and Trades persistent storage."""
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_order(self, order: ExecutionOrder) -> ExecutionOrderModel:
        stmt = select(ExecutionOrderModel).where(ExecutionOrderModel.order_id == order.order_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record:
            record.status = order.status.value
            record.filled_quantity = order.filled_quantity
            record.average_fill_price = order.average_fill_price
            record.rejection_reason = order.rejection_reason
            record.updated_at = now
        else:
            record = ExecutionOrderModel(
                order_id=order.order_id,
                idempotency_key=order.idempotency_key,
                user_id=order.user_id,
                broker=order.broker.value,
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                stop_loss=order.stop_loss,
                target=order.target,
                status=order.status.value,
                filled_quantity=order.filled_quantity,
                average_fill_price=order.average_fill_price,
                rejection_reason=order.rejection_reason,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
            self.session.add(record)

        await self.session.flush()
        return record

    async def get_by_id(self, order_id: str) -> Optional[ExecutionOrder]:
        stmt = select(ExecutionOrderModel).where(ExecutionOrderModel.order_id == order_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return self._to_schema(record)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ExecutionOrder]:
        stmt = select(ExecutionOrderModel).where(ExecutionOrderModel.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return self._to_schema(record)

    async def list_orders(self, user_id: str, limit: int = 50) -> List[ExecutionOrder]:
        stmt = (
            select(ExecutionOrderModel)
            .where(ExecutionOrderModel.user_id == user_id)
            .order_by(ExecutionOrderModel.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [self._to_schema(r) for r in res.scalars().all()]

    def _to_schema(self, record: ExecutionOrderModel) -> ExecutionOrder:
        return ExecutionOrder(
            order_id=record.order_id,
            idempotency_key=record.idempotency_key,
            user_id=record.user_id,
            broker=BrokerType(record.broker),
            symbol=record.symbol,
            side=OrderSide(record.side),
            order_type=OrderType(record.order_type),
            quantity=record.quantity,
            price=record.price,
            stop_loss=record.stop_loss,
            target=record.target,
            status=OrderStatus(record.status),
            filled_quantity=record.filled_quantity,
            average_fill_price=record.average_fill_price,
            rejection_reason=record.rejection_reason,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    # -------------------------------------------------------------------------
    # Fills, Positions, and Trades
    # -------------------------------------------------------------------------
    async def record_fill(
        self,
        order_id: str,
        user_id: str,
        symbol: str,
        side: OrderSide,
        filled_quantity: int,
        fill_price: float,
        fee_amount: float = 0.0,
    ) -> FillModel:
        fill = FillModel(
            order_id=order_id,
            user_id=user_id,
            symbol=symbol,
            side=side.value,
            filled_quantity=filled_quantity,
            fill_price=fill_price,
            fee_amount=fee_amount,
        )
        self.session.add(fill)
        await self.session.flush()
        return fill

    async def update_position(
        self,
        user_id: str,
        broker: BrokerType,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: float,
        stop_loss: float,
        target: float,
    ) -> PositionModel:
        stmt = (
            select(PositionModel)
            .where(PositionModel.user_id == user_id)
            .where(PositionModel.symbol == symbol)
            .where(PositionModel.is_open.is_(True))
        )
        res = await self.session.execute(stmt)
        pos = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if pos:
            pos.quantity = quantity
            pos.stop_loss = stop_loss
            pos.target = target
            if quantity == 0:
                pos.is_open = False
                pos.closed_at = now
        else:
            pos = PositionModel(
                user_id=user_id,
                broker=broker.value,
                symbol=symbol,
                quantity=quantity,
                side=side.value,
                entry_price=price,
                stop_loss=stop_loss,
                target=target,
                is_open=True,
                opened_at=now,
            )
            self.session.add(pos)

        await self.session.flush()
        return pos

    async def get_open_positions(self, user_id: str) -> List[Dict[str, Any]]:
        stmt = (
            select(PositionModel)
            .where(PositionModel.user_id == user_id)
            .where(PositionModel.is_open.is_(True))
        )
        res = await self.session.execute(stmt)
        return [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "side": p.side,
                "entry_price": p.entry_price,
                "stop_loss": p.stop_loss,
                "target": p.target,
                "opened_at": p.opened_at.isoformat(),
            }
            for p in res.scalars().all()
        ]

    async def record_trade(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        entry_price: float,
        exit_price: float,
        gross_pnl: float,
        net_pnl: float,
        total_costs: float,
        entry_time: datetime,
        exit_time: datetime,
    ) -> TradeModel:
        trade = TradeModel(
            user_id=user_id,
            order_id=order_id,
            symbol=symbol,
            side=side.value,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            total_costs=total_costs,
            entry_time=entry_time,
            exit_time=exit_time,
        )
        self.session.add(trade)
        await self.session.flush()
        return trade
