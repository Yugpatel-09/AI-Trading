from abc import ABC, abstractmethod
from typing import Any, Dict, List

from tradeforge_shared.schemas import ExecutionOrder, OrderProposal


class BrokerGateway(ABC):
    """
    Abstract broker gateway interface.
    All broker adapters (Paper, Zerodha, Upstox, Angel One) implement this contract.
    """
    @abstractmethod
    async def place_order(self, proposal: OrderProposal, approved_quantity: int) -> ExecutionOrder:
        """Submit an approved order."""
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
