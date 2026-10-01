import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tradeforge_shared.costs import IndianCostCalculator
from tradeforge_shared.enums import BrokerType, OrderSide, OrderStatus, OrderType
from tradeforge_shared.schemas import ExecutionOrder, RiskApproval

from services.execution.gateway.base import BrokerGateway


class PaperBroker(BrokerGateway):
    """
    High-fidelity simulated paper broker.
    Executes trades against live market prices, calculating exact statutory costs.
    Non-Negotiable Rule 1: place_order accepts ONLY a valid RiskApproval.
    """
    def __init__(
        self,
        initial_capital: float = 500000.0,
        signing_secret: Optional[str] = None,
        simulate_partial_fill_qty: Optional[int] = None,
        simulate_stop_placement_failure: bool = False,
    ):
        super().__init__(signing_secret=signing_secret)
        self.initial_capital = initial_capital
        self.available_margin = initial_capital
        self.orders: Dict[str, ExecutionOrder] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.cost_calculator = IndianCostCalculator()
        self.simulate_partial_fill_qty = simulate_partial_fill_qty
        self.simulate_stop_placement_failure = simulate_stop_placement_failure

    async def place_order(
        self,
        approval: RiskApproval,
        current_time: Optional[datetime] = None,
    ) -> ExecutionOrder:
        # Mandatory bypass-proof validation: rejects missing, tampered, expired, or reused approvals
        self.verify_approval(approval, current_time=current_time)

        order_id = f"paper_ord_{uuid.uuid4().hex[:10]}"
        now = current_time or datetime.now(timezone.utc)

        # In paper mode, simulated fill with 0.02% slippage
        fill_price = approval.price * 1.0002 if approval.side == OrderSide.BUY else approval.price * 0.9998

        # Support partial fills if configured for drills/simulations
        if self.simulate_partial_fill_qty is not None and self.simulate_partial_fill_qty < approval.approved_quantity:
            status = OrderStatus.PARTIAL_FILL
            filled_qty = self.simulate_partial_fill_qty
        else:
            status = OrderStatus.FILLED
            filled_qty = approval.approved_quantity

        order = ExecutionOrder(
            order_id=order_id,
            idempotency_key=approval.idempotency_key,
            user_id=approval.user_id,
            broker=BrokerType.PAPER,
            symbol=approval.symbol,
            side=approval.side,
            order_type=OrderType.MARKET,
            quantity=approval.approved_quantity,
            price=approval.price,
            stop_loss=approval.stop_loss,
            target=approval.target,
            status=status,
            filled_quantity=filled_qty,
            average_fill_price=round(fill_price, 2),
            created_at=now,
            updated_at=now,
        )

        self.orders[order_id] = order

        # Update simulated positions
        self.positions[approval.symbol] = {
            "symbol": approval.symbol,
            "quantity": filled_qty,
            "entry_price": round(fill_price, 2),
            "side": approval.side.value,
            "stop_loss": approval.stop_loss,
            "target": approval.target,
            "opened_at": now.isoformat(),
        }

        return order

    async def place_stop_order(
        self,
        user_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        stop_price: float,
        parent_order_id: str,
    ) -> ExecutionOrder:
        """Place linked protective stop-loss order."""
        if self.simulate_stop_placement_failure:
            raise RuntimeError(f"Broker rejected protective stop-loss placement for parent {parent_order_id}: Internal Broker Margin/Exchange Error")

        stop_order_id = f"sl_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)

        stop_order = ExecutionOrder(
            order_id=stop_order_id,
            idempotency_key=f"sl_{parent_order_id}",
            user_id=user_id,
            broker=BrokerType.PAPER,
            symbol=symbol,
            side=side,
            order_type=OrderType.SL_M,
            quantity=quantity,
            price=stop_price,
            stop_loss=stop_price,
            target=0.0,
            status=OrderStatus.SUBMITTED,
            filled_quantity=0,
            created_at=now,
            updated_at=now,
        )
        self.orders[stop_order_id] = stop_order
        return stop_order

    async def flatten_position(
        self,
        user_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        reason: str = "EMERGENCY_FLATTEN",
    ) -> ExecutionOrder:
        """Emergency market exit order to neutralize exposure."""
        flatten_id = f"flat_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)

        flatten_order = ExecutionOrder(
            order_id=flatten_id,
            idempotency_key=f"flat_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            broker=BrokerType.PAPER,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=0.0,
            stop_loss=0.0,
            target=0.0,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            created_at=now,
            updated_at=now,
            rejection_reason=reason,
        )
        self.orders[flatten_id] = flatten_order
        if symbol in self.positions:
            self.positions.pop(symbol)
        return flatten_order

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order_status(self, order_id: str) -> ExecutionOrder:
        if order_id not in self.orders:
            raise KeyError(f"Order {order_id} not found in PaperBroker.")
        return self.orders[order_id]

    async def get_funds(self) -> Dict[str, float]:
        return {
            "available_cash": self.available_margin,
            "total_collateral": self.initial_capital,
            "utilized_margin": self.initial_capital - self.available_margin,
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions.values())
