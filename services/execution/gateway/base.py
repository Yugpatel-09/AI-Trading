import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from tradeforge_shared.schemas import ExecutionOrder, RiskApproval


class GatewayApprovalError(Exception):
    """Base exception for RiskApproval verification failures at the broker gateway boundary."""
    pass


class MissingApprovalError(GatewayApprovalError):
    """Raised when an order submission attempts to bypass RiskApproval."""
    pass


class TamperedApprovalError(GatewayApprovalError):
    """Raised when the cryptographic HMAC signature of RiskApproval is invalid."""
    pass


class ExpiredApprovalError(GatewayApprovalError):
    """Raised when RiskApproval TTL (30s) has expired."""
    pass


class ReusedApprovalError(GatewayApprovalError):
    """Raised when an approval token is submitted more than once (replay attack)."""
    pass


class BrokerGateway(ABC):
    """
    Abstract broker gateway interface.
    All broker adapters (Paper, Zerodha, Upstox, Angel One) implement this contract.
    Non-Negotiable Rule 1: place_order accepts ONLY a RiskApproval, never a raw proposal.
    Rejects missing, tampered, expired or reused approvals.
    """
    def __init__(self, signing_secret: Optional[str] = None):
        self.signing_secret = signing_secret or os.getenv("SECRET_KEY", "tradeforge_risk_guard_hmac_signing_key_default_32b")
        self._used_approval_ids: Set[str] = set()

    def verify_approval(self, approval: Any, current_time: Optional[datetime] = None) -> None:
        """
        Verify that the submission contains a genuine, unexpired, un-reused RiskApproval.
        Raises specific GatewayApprovalError subclass on violation.
        """
        if approval is None or not isinstance(approval, RiskApproval):
            raise MissingApprovalError(
                "BrokerGateway rejects raw proposal submission. Orders must be authorized by RiskApproval."
            )

        if not approval.verify_signature(self.signing_secret):
            raise TamperedApprovalError(
                f"Tampered or forged RiskApproval detected (approval_id: {approval.approval_id}). Signature invalid."
            )

        if approval.is_expired(current_time=current_time):
            raise ExpiredApprovalError(
                f"RiskApproval {approval.approval_id} expired at {approval.expires_at} (short TTL exceeded)."
            )

        if approval.approval_id in self._used_approval_ids:
            raise ReusedApprovalError(
                f"RiskApproval {approval.approval_id} has already been executed. Replay submissions rejected."
            )

        # Mark as used immediately to prevent replay
        self._used_approval_ids.add(approval.approval_id)

    @abstractmethod
    async def place_order(
        self,
        approval: RiskApproval,
        current_time: Optional[datetime] = None,
    ) -> ExecutionOrder:
        """Submit an approved order. Accepts ONLY RiskApproval."""
        pass

    @abstractmethod
    async def place_stop_order(
        self,
        user_id: str,
        symbol: str,
        side: Any,
        quantity: int,
        stop_price: float,
        parent_order_id: str,
    ) -> ExecutionOrder:
        """Submit protective stop-loss order linked to entry position."""
        pass

    @abstractmethod
    async def flatten_position(
        self,
        user_id: str,
        symbol: str,
        side: Any,
        quantity: int,
        reason: str = "EMERGENCY_FLATTEN",
    ) -> ExecutionOrder:
        """Immediately exit position at market (e.g. if protective stop fails)."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> ExecutionOrder:
        """Fetch current status and fills for an order."""
        pass

    @abstractmethod
    async def get_funds(self) -> Dict[str, float]:
        """Fetch available margin and balance."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        pass
