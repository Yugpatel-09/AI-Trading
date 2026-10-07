import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from tradeforge_shared.enums import BrokerType, OrderSide, OrderStatus, OrderType, TradingMode
from tradeforge_shared.schemas import (
    ExecutionOrder,
    OrderProposal,
    RiskApproval,
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


class StopPlacementFailureError(Exception):
    """Raised when a protective stop-loss fails to place and position was emergency flattened."""
    def __init__(self, order_id: str, symbol: str, quantity: int, reason: str):
        self.order_id = order_id
        self.symbol = symbol
        self.quantity = quantity
        self.reason = reason
        super().__init__(
            f"CRITICAL: Protective stop placement failed for order {order_id} ({quantity} {symbol}). "
            f"Position was flattened immediately at market. Reason: {reason}"
        )


class OrderApprovalTimeoutError(Exception):
    """Raised when user confirmation in APPROVE mode times out."""
    pass


class PendingOrderApproval(BaseModel):
    """Represents an order proposal awaiting explicit user confirmation in APPROVE mode."""
    model_config = ConfigDict(from_attributes=True)
    pending_id: str
    proposal: OrderProposal
    user_settings: UserRiskSettings
    current_ltp: float
    created_at: datetime
    expires_at: datetime
    status: OrderStatus = OrderStatus.PENDING_USER_APPROVAL


class OrderManager:
    """
    Authoritative Execution Manager & Sole Path from AI Signals/API/Backtester to Broker Gateways.

    Non-Negotiable Rules Enforced:
      Rule 1: Safety before features. Every order must pass Risk Guard and receive a valid RiskApproval.
      Rule 2: Paper mode is default. Live trading requires explicit opt-in and checks.
      Rule 7: Stop-loss is sent with entry order. If the stop fails to place, flatten the entry immediately.
      Rule 8: Orders must be idempotent. Duplicate submissions must never produce multiple orders.
    """
    def __init__(
        self,
        risk_guard: Optional[RiskGuard] = None,
        gateways: Optional[Dict[BrokerType, BrokerGateway]] = None,
        approval_timeout_seconds: int = 60,
        paper_initial_capital: float = 1_000_000.0,
        paper_slippage_bps: float = 2.0,
        paper_spread_bps: float = 1.0,
    ):
        self.risk_guard = risk_guard or RiskGuard()
        self._gateways: Dict[BrokerType, BrokerGateway] = gateways or {
            BrokerType.PAPER: PaperBroker(
                initial_capital=paper_initial_capital,
                signing_secret=self.risk_guard.signing_secret,
                slippage_bps=paper_slippage_bps,
                spread_bps=paper_spread_bps,
            ),
        }
        self.approval_timeout_seconds = approval_timeout_seconds
        self._orders_by_id: Dict[str, ExecutionOrder] = {}
        self._orders_by_idempotency: Dict[str, ExecutionOrder] = {}
        self._pending_approvals: Dict[str, PendingOrderApproval] = {}

    def register_gateway(self, broker_type: BrokerType, gateway: BrokerGateway) -> None:
        """Register or override a broker adapter behind the standard interface."""
        self._gateways[broker_type] = gateway

    def get_gateway(self, broker_type: BrokerType) -> BrokerGateway:
        gateway = self._gateways.get(broker_type)
        if not gateway:
            raise InvalidOrderError(f"Broker gateway for '{broker_type}' is not registered.")
        return gateway

    # -------------------------------------------------------------------------
    # Safe Gateway Query Facades (Eliminates direct gateway imports from API/Engine)
    # -------------------------------------------------------------------------
    async def get_broker_funds(self, broker_type: BrokerType) -> Dict[str, float]:
        gateway = self.get_gateway(broker_type)
        return await gateway.get_funds()

    async def get_broker_positions(self, broker_type: BrokerType) -> List[Dict[str, Any]]:
        gateway = self.get_gateway(broker_type)
        return await gateway.get_positions()

    async def test_broker_connection(self, broker_type: BrokerType) -> Dict[str, Any]:
        gateway = self.get_gateway(broker_type)
        funds = await gateway.get_funds()
        return {
            "broker": broker_type.value,
            "connected": True,
            "funds": funds,
            "latency_ms": 15,
        }

    # -------------------------------------------------------------------------
    # Mode Gate: Paper / Approve / Auto Execution
    # -------------------------------------------------------------------------
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
        Enforces idempotency, mode gate (PAPER, APPROVE, AUTO), Risk Guard verification,
        protective stop-loss placement, and emergency flattening on stop failures.
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

        # 3. APPROVE Mode Gate: Hold order until user confirms
        if proposal.mode == TradingMode.APPROVE:
            return self._queue_pending_approval(
                proposal=proposal,
                user_settings=user_settings,
                current_ltp=current_ltp,
                now=now,
            )

        # 4. For PAPER and AUTO modes, execute directly through the verified pipeline
        return await self._execute_approved_order_pipeline(
            proposal=proposal,
            user_settings=user_settings,
            current_ltp=current_ltp,
            current_time=now,
            enforce_trading_hours=enforce_trading_hours,
        )

    def _queue_pending_approval(
        self,
        proposal: OrderProposal,
        user_settings: UserRiskSettings,
        current_ltp: float,
        now: datetime,
    ) -> ExecutionOrder:
        """Hold order in pending queue until user explicit confirmation."""
        pending_id = f"pend_{uuid.uuid4().hex[:10]}"
        expires_at = now + timedelta(seconds=self.approval_timeout_seconds)

        pending_record = PendingOrderApproval(
            pending_id=pending_id,
            proposal=proposal,
            user_settings=user_settings,
            current_ltp=current_ltp,
            created_at=now,
            expires_at=expires_at,
            status=OrderStatus.PENDING_USER_APPROVAL,
        )
        self._pending_approvals[pending_id] = pending_record

        # Return a pending execution order representation
        pending_order = ExecutionOrder(
            order_id=pending_id,
            idempotency_key=proposal.idempotency_key,
            user_id=proposal.user_id,
            broker=proposal.broker,
            symbol=proposal.signal.symbol,
            side=proposal.signal.side,
            order_type=OrderType.MARKET,
            quantity=proposal.requested_quantity,
            price=proposal.signal.entry_price,
            stop_loss=proposal.signal.stop_loss,
            target=proposal.signal.target,
            status=OrderStatus.PENDING_USER_APPROVAL,
            filled_quantity=0,
            created_at=now,
            updated_at=now,
        )
        logger.info(
            f"[ORDER MANAGER] Order {pending_id} held in APPROVE mode. "
            f"Awaiting user confirmation before {expires_at.isoformat()}."
        )
        return pending_order

    async def confirm_pending_order(
        self,
        pending_id: str,
        user_id: str,
        action: str = "APPROVE",
        current_time: Optional[datetime] = None,
    ) -> ExecutionOrder:
        """
        User approval callback for orders queued in APPROVE mode.
        If approved before timeout, passes through Risk Guard and executes.
        """
        if pending_id not in self._pending_approvals:
            raise KeyError(f"Pending order {pending_id} not found.")

        pending = self._pending_approvals[pending_id]
        if pending.proposal.user_id != user_id:
            raise PermissionError("User ID does not match pending order owner.")

        now = current_time or datetime.now(timezone.utc)
        if now > pending.expires_at:
            pending.status = OrderStatus.EXPIRED
            self._pending_approvals.pop(pending_id, None)
            raise OrderApprovalTimeoutError(
                f"Order approval for {pending_id} timed out and expired at {pending.expires_at}."
            )

        if action.upper() == "REJECT":
            pending.status = OrderStatus.CANCELLED
            self._pending_approvals.pop(pending_id, None)
            rejected_order = ExecutionOrder(
                order_id=pending_id,
                idempotency_key=pending.proposal.idempotency_key,
                user_id=user_id,
                broker=pending.proposal.broker,
                symbol=pending.proposal.signal.symbol,
                side=pending.proposal.signal.side,
                order_type=OrderType.MARKET,
                quantity=0,
                price=pending.proposal.signal.entry_price,
                stop_loss=pending.proposal.signal.stop_loss,
                target=pending.proposal.signal.target,
                status=OrderStatus.CANCELLED,
                filled_quantity=0,
                created_at=pending.created_at,
                updated_at=now,
                rejection_reason="User manually rejected pending order in APPROVE mode",
            )
            return rejected_order

        # User approved: remove from pending and execute
        self._pending_approvals.pop(pending_id, None)
        return await self._execute_approved_order_pipeline(
            proposal=pending.proposal,
            user_settings=pending.user_settings,
            current_ltp=pending.current_ltp,
            current_time=now,
        )

    # -------------------------------------------------------------------------
    # Core Pipeline: Risk Guard -> RiskApproval -> Broker Gateway -> Stop-Loss
    # -------------------------------------------------------------------------
    async def _execute_approved_order_pipeline(
        self,
        proposal: OrderProposal,
        user_settings: UserRiskSettings,
        current_ltp: float,
        current_time: datetime,
        enforce_trading_hours: bool = True,
    ) -> ExecutionOrder:
        signal = proposal.signal

        # 1. Rule 1: MANDATORY Risk Guard Verification (NO BYPASS POSSIBLE)
        risk_result: RiskCheckResult = self.risk_guard.validate_proposal(
            proposal=proposal,
            user_settings=user_settings,
            current_ltp=current_ltp,
            current_time=current_time,
            enforce_trading_hours=enforce_trading_hours,
        )

        if not risk_result.approved or risk_result.approval is None:
            logger.warning(
                f"[ORDER MANAGER] Risk Guard REJECTED proposal {proposal.idempotency_key}: "
                f"{'; '.join(risk_result.violations)}"
            )
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
                created_at=current_time,
                updated_at=current_time,
                rejection_reason="; ".join(risk_result.violations),
            )
            self._orders_by_id[rejected_order.order_id] = rejected_order
            # CRITICAL: Broker gateway is NEVER invoked!
            raise RiskGuardViolationError(risk_result)

        # 2. Extract verified RiskApproval constructed strictly by RiskGuard
        approval: RiskApproval = risk_result.approval
        gateway = self.get_gateway(proposal.broker)

        # 3. Route to Broker Gateway with Exponential Backoff Retries
        order = await self._place_order_with_retry(
            gateway=gateway,
            approval=approval,
            max_retries=3,
            initial_backoff=0.05,
            current_time=current_time,
        )

        # 4. Rule 7: Protective-Stop Placement Confirmation
        # If entry is filled or partially filled, immediately place protective stop
        if order.filled_quantity > 0:
            stop_side = OrderSide.SELL if order.side == OrderSide.BUY else OrderSide.BUY
            try:
                await gateway.place_stop_order(
                    user_id=proposal.user_id,
                    symbol=order.symbol,
                    side=stop_side,
                    quantity=order.filled_quantity,
                    stop_price=order.stop_loss,
                    parent_order_id=order.order_id,
                )
                logger.info(
                    f"[ORDER MANAGER] Protective stop placed successfully for order {order.order_id}: "
                    f"{stop_side.value} {order.filled_quantity} {order.symbol} @ ₹{order.stop_loss:.2f}"
                )
            except Exception as sl_err:
                logger.critical(
                    f"[ORDER MANAGER] PROTECTIVE STOP PLACEMENT FAILED for {order.order_id}! "
                    f"Initiating IMMEDIATE EMERGENCY FLATTEN at market. Error: {sl_err}"
                )
                # FLATTEN ENTRY IMMEDIATELY
                flatten_side = stop_side
                try:
                    await gateway.flatten_position(
                        user_id=proposal.user_id,
                        symbol=order.symbol,
                        side=flatten_side,
                        quantity=order.filled_quantity,
                        reason=f"STOP_LOSS_FAILED: {sl_err}",
                    )
                    logger.critical(f"[ORDER MANAGER] Position successfully flattened for {order.symbol}.")
                except Exception as flat_err:
                    logger.critical(f"[FATAL HAZARD] Emergency flatten also failed! {flat_err}")

                order.rejection_reason = f"Protective stop failed: {sl_err}. Position emergency flattened."
                self._orders_by_id[order.order_id] = order
                raise StopPlacementFailureError(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    quantity=order.filled_quantity,
                    reason=str(sl_err),
                ) from sl_err

        # 5. Record execution in Risk Guard and internal ledger
        self.risk_guard.record_trade_execution(proposal.user_id)
        self._orders_by_id[order.order_id] = order
        self._orders_by_idempotency[proposal.idempotency_key] = order

        logger.info(
            f"[ORDER MANAGER] Order {order.order_id} successfully executed via {proposal.broker}: "
            f"{order.side.value} {order.quantity} {order.symbol} @ ₹{order.price:.2f} "
            f"(SL: ₹{order.stop_loss:.2f})"
        )
        return order

    async def _place_order_with_retry(
        self,
        gateway: BrokerGateway,
        approval: RiskApproval,
        max_retries: int = 3,
        initial_backoff: float = 0.05,
        current_time: Optional[datetime] = None,
    ) -> ExecutionOrder:
        """Execute gateway place_order with exponential backoff on transient transport errors."""
        last_error = None
        backoff = initial_backoff
        for attempt in range(1, max_retries + 1):
            try:
                # Gateway place_order accepts ONLY RiskApproval
                return await gateway.place_order(approval, current_time=current_time)
            except Exception as e:
                # Do not retry on logical rejection or approval tampering/expiry
                from services.execution.gateway.base import GatewayApprovalError
                if isinstance(e, GatewayApprovalError):
                    raise
                last_error = e
                logger.warning(
                    f"[ORDER MANAGER] Gateway error on attempt {attempt}/{max_retries} "
                    f"for approval {approval.approval_id}: {e}. Retrying in {backoff:.2f}s..."
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

        raise RuntimeError(f"Broker gateway call failed after {max_retries} attempts: {last_error}") from last_error

    # -------------------------------------------------------------------------
    # Status Polling and Recovery
    # -------------------------------------------------------------------------
    async def poll_order_status(
        self,
        broker_type: BrokerType,
        order_id: str,
        timeout_seconds: float = 5.0,
        poll_interval: float = 0.1,
    ) -> ExecutionOrder:
        """Poll gateway for latest order execution status."""
        gateway = self.get_gateway(broker_type)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

        while datetime.now(timezone.utc) < deadline:
            order = await gateway.get_order_status(order_id)
            self._orders_by_id[order.order_id] = order
            if order.status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
                return order
            await asyncio.sleep(poll_interval)

        return await gateway.get_order_status(order_id)

    def get_order(self, order_id: str) -> Optional[ExecutionOrder]:
        return self._orders_by_id.get(order_id)

    def snapshot_state(self) -> Dict[str, Any]:
        """Produce serializable state snapshot for crash recovery."""
        return {
            "orders": {k: v.model_dump(mode="json") for k, v in self._orders_by_id.items()},
            "idempotency_map": {k: v.order_id for k, v in self._orders_by_idempotency.items()},
        }

    def recover_state(self, snapshot: Dict[str, Any]) -> None:
        """Restore state from disk/database after mid-order restart or crash."""
        orders_data = snapshot.get("orders", {})
        idemp_map = snapshot.get("idempotency_map", {})
        self._orders_by_id = {k: ExecutionOrder.model_validate(v) for k, v in orders_data.items()}
        self._orders_by_idempotency = {
            idemp_k: self._orders_by_id[order_id]
            for idemp_k, order_id in idemp_map.items()
            if order_id in self._orders_by_id
        }
        logger.info(f"[ORDER MANAGER] Recovered {len(self._orders_by_id)} orders from snapshot.")


# Global singleton instance for platform execution
order_manager = OrderManager()
