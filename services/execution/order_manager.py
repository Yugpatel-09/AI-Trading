from datetime import datetime, timezone
from typing import Dict, Optional

from tradeforge_shared.enums import BrokerType, OrderStatus, OrderType
from tradeforge_shared.schemas import (
    ExecutionOrder,
    OrderProposal,
    RiskCheckResult,
    UserRiskSettings,
)

from services.api.app.core.logging import logger
from services.execution.gateway.base import BrokerGateway
from services.execution.gateway.paper_broker import PaperBroker
from services.risk_guard.guard import RiskGuard


class RiskGuardViolationError(Exception):
    """Raised when an order proposal fails Risk Guard pre-trade validation."""
    def __init__(self, result: RiskCheckResult):
        self.result = result
        self.violations = result.violations
        super().__init__(f"Order blocked by Risk Guard: {'; '.join(result.violations)}")


class InvalidOrderError(Exception):
    """Raised when an order proposal violates non-negotiable structural requirements."""
    pass


class OrderManager:
    """
    Authoritative Execution Manager & Sole Path from AI Signals to Broker Gateways.
    Enforces Non-Negotiable Rules:
      Rule 1: Safety before features. Every order must pass Risk Guard. No code path can bypass it.
      Rule 7: Stop-loss is sent with the entry order. No entry without a protective stop.
      Rule 8: Orders must be idempotent. Duplicate submissions must never produce multiple orders.
    """
    def __init__(
        self,
        risk_guard: Optional[RiskGuard] = None,
        gateways: Optional[Dict[BrokerType, BrokerGateway]] = None,
    ):
        self.risk_guard = risk_guard or RiskGuard()
        self._gateways: Dict[BrokerType, BrokerGateway] = gateways or {
            BrokerType.PAPER: PaperBroker(),
        }
        self._orders_by_id: Dict[str, ExecutionOrder] = {}
        self._orders_by_idempotency: Dict[str, ExecutionOrder] = {}

    def register_gateway(self, broker_type: BrokerType, gateway: BrokerGateway) -> None:
        """Register or override a broker adapter behind the standard interface."""
        self._gateways[broker_type] = gateway

    def get_gateway(self, broker_type: BrokerType) -> BrokerGateway:
        gateway = self._gateways.get(broker_type)
        if not gateway:
            raise InvalidOrderError(f"Broker gateway for '{broker_type}' is not registered.")
        return gateway

    async def submit_order(
        self,
        proposal: OrderProposal,
        user_settings: UserRiskSettings,
        current_ltp: float,
        current_time: Optional[datetime] = None,
        enforce_trading_hours: bool = True,
    ) -> ExecutionOrder:
        """
        The ONLY valid path to submit an order to a broker.
        1. Checks idempotency.
        2. Validates mandatory stop-loss with entry order.
        3. Enforces Risk Guard pre-trade checks (NO BYPASS POSSIBLE).
        4. Transmits entry and stop-loss together to the broker.
        5. Updates Risk Guard trade ledger.
        """
        signal = proposal.signal
        now = current_time or datetime.now(timezone.utc)

        # 1. Idempotency Check: if this key was already successfully executed, return cached order
        if proposal.idempotency_key in self._orders_by_idempotency:
            logger.warning(
                f"[ORDER MANAGER] Duplicate submission detected for key: {proposal.idempotency_key}. "
                "Returning existing order without re-routing to broker."
            )
            return self._orders_by_idempotency[proposal.idempotency_key]

        # 2. Rule 7: Stop-loss is mandatory with entry order
        if not signal.stop_loss or signal.stop_loss <= 0 or signal.stop_loss == signal.entry_price:
            logger.error(
                f"[ORDER MANAGER] Order proposal {proposal.idempotency_key} rejected: "
                "Missing or invalid protective stop-loss."
            )
            raise InvalidOrderError("Protective stop-loss is mandatory with entry order.")

        # 3. Rule 1: MANDATORY Risk Guard Verification
        risk_result: RiskCheckResult = self.risk_guard.validate_proposal(
            proposal=proposal,
            user_settings=user_settings,
            current_ltp=current_ltp,
            current_time=now,
            enforce_trading_hours=enforce_trading_hours,
        )

        if not risk_result.approved:
            logger.warning(
                f"[ORDER MANAGER] Risk Guard REJECTED proposal {proposal.idempotency_key}: "
                f"{'; '.join(risk_result.violations)}"
            )
            # Create a rejected execution order record for audit
            rejected_order = ExecutionOrder(
                order_id=f"rej_{proposal.idempotency_key[:12]}",
                idempotency_key=proposal.idempotency_key,
                user_id=proposal.user_id,
                broker=proposal.broker,
                symbol=signal.symbol,
                side=signal.side,
                order_type=OrderType.MARKET,
                quantity=0,
                price=signal.entry_price,
                stop_loss=signal.stop_loss,
                target=signal.target,
                status=OrderStatus.RISK_REJECTED,
                filled_quantity=0,
                created_at=now,
                updated_at=now,
                rejection_reason="; ".join(risk_result.violations),
            )
            self._orders_by_id[rejected_order.order_id] = rejected_order
            # CRITICAL: Broker gateway is NEVER invoked!
            raise RiskGuardViolationError(risk_result)

        # 4. Sizing: Use Risk Guard approved/downscaled quantity
        approved_qty = risk_result.adjusted_quantity
        if approved_qty <= 0:
            raise InvalidOrderError("Risk Guard approved quantity is zero.")

        # 5. Route to Broker Gateway
        gateway = self.get_gateway(proposal.broker)
        order = await gateway.place_order(proposal, approved_qty)

        # 6. Record execution in Risk Guard and internal ledger
        self.risk_guard.record_trade_execution(proposal.user_id)
        self._orders_by_id[order.order_id] = order
        self._orders_by_idempotency[proposal.idempotency_key] = order

        logger.info(
            f"[ORDER MANAGER] Order {order.order_id} successfully executed via {proposal.broker}: "
            f"{order.side.value} {order.quantity} {order.symbol} @ ₹{order.price:.2f} "
            f"(SL: ₹{order.stop_loss:.2f})"
        )
        return order

    def get_order(self, order_id: str) -> Optional[ExecutionOrder]:
        return self._orders_by_id.get(order_id)
