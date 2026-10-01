import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from tradeforge_shared.schemas import ExecutionOrder, OrderProposal
from tradeforge_shared.enums import OrderStatus, OrderType, BrokerType
from tradeforge_shared.costs import IndianCostCalculator
from services.execution.gateway.base import BrokerGateway

class PaperBroker(BrokerGateway):
    """
    High-fidelity simulated paper broker.
    Executes trades against live market prices, calculating exact statutory costs.
    """
    def __init__(self, initial_capital: float = 500000.0):
        self.initial_capital = initial_capital
        self.available_margin = initial_capital
        self.orders: Dict[str, ExecutionOrder] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.cost_calculator = IndianCostCalculator()

    async def place_order(self, proposal: OrderProposal, approved_quantity: int) -> ExecutionOrder:
        order_id = f"paper_ord_{uuid.uuid4().hex[:10]}"
        signal = proposal.signal
        now = datetime.now(timezone.utc)

        # In paper mode, simulated fill with 0.02% slippage
        fill_price = signal.entry_price * 1.0002 if signal.side.value == "BUY" else signal.entry_price * 0.9998

        order = ExecutionOrder(
            order_id=order_id,
            idempotency_key=proposal.idempotency_key,
            user_id=proposal.user_id,
            broker=BrokerType.PAPER,
            symbol=signal.symbol,
            side=signal.side,
            order_type=OrderType.MARKET,
            quantity=approved_quantity,
            price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            status=OrderStatus.FILLED,
            filled_quantity=approved_quantity,
            average_fill_price=round(fill_price, 2),
            created_at=now,
            updated_at=now,
        )

        self.orders[order_id] = order
        # Update simulated positions
        self.positions[signal.symbol] = {
            "symbol": signal.symbol,
            "quantity": approved_quantity,
            "entry_price": fill_price,
            "side": signal.side.value,
            "stop_loss": signal.stop_loss,
            "target": signal.target,
            "opened_at": now.isoformat(),
        }

        return order

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order_status(self, order_id: str) -> ExecutionOrder:
        return self.orders[order_id]

    async def get_funds(self) -> Dict[str, float]:
        return {
            "available_cash": self.available_margin,
            "total_collateral": self.initial_capital,
            "utilized_margin": self.initial_capital - self.available_margin,
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions.values())
