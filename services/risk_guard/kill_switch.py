from datetime import datetime, timezone
from typing import Optional

class KillSwitch:
    """
    Global and user-specific Emergency Circuit Breaker.
    When activated:
    - Rejects all subsequent inbound order proposals.
    - Signals order manager to cancel open limit orders.
    - Dispatches square-off requests for active market positions.
    """
    def __init__(self):
        self._global_active: bool = False
        self._activated_at: Optional[datetime] = None
        self._activation_reason: Optional[str] = None
        self._user_switches: dict[str, bool] = {}

    @property
    def is_global_active(self) -> bool:
        return self._global_active

    def is_active_for_user(self, user_id: str) -> bool:
        return self._global_active or self._user_switches.get(user_id, False)

    def activate_global(self, reason: str = "Manual Emergency Halt"):
        self._global_active = True
        self._activated_at = datetime.now(timezone.utc)
        self._activation_reason = reason

    def deactivate_global(self):
        self._global_active = False
        self._activated_at = None
        self._activation_reason = None

    def activate_user(self, user_id: str, reason: str = "User Emergency Stop"):
        self._user_switches[user_id] = True

    def deactivate_user(self, user_id: str):
        self._user_switches.pop(user_id, None)

    def status(self) -> dict:
        return {
            "global_kill_switch_active": self._global_active,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "reason": self._activation_reason,
            "active_user_halts": list(self._user_switches.keys()),
        }
