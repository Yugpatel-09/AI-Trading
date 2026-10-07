from datetime import datetime, timezone
from typing import Any, Optional


class KillSwitch:
    """
    Global and user-specific Emergency Circuit Breaker.
    When activated:
    - Rejects all subsequent inbound order proposals.
    - Signals order manager to cancel open limit orders.
    - Dispatches square-off requests for active market positions.

    Backing: Reads and writes directly to Redis when connected, ensuring
    kill-switch halts survive process restarts and are immediately observed across
    all distributed engine and worker processes.
    """
    def __init__(self, redis_manager: Optional[Any] = None):
        self._global_active: bool = False
        self._activated_at: Optional[datetime] = None
        self._activation_reason: Optional[str] = None
        self._user_switches: dict[str, bool] = {}
        self.redis_manager = redis_manager

    @property
    def is_global_active(self) -> bool:
        """Reads directly from Redis when connected."""
        if self.redis_manager and self.redis_manager.is_connected:
            active, reason = self.redis_manager.is_global_kill_switch_active_sync()
            if active and not self._activation_reason:
                self._activation_reason = reason
            return active
        return self._global_active

    def is_active_for_user(self, user_id: str) -> bool:
        """Reads directly from Redis when connected."""
        if self.is_global_active:
            return True
        if self.redis_manager and self.redis_manager.is_connected:
            active, _ = self.redis_manager.is_user_kill_switch_active_sync(user_id)
            return active
        return self._user_switches.get(user_id, False)

    def activate_global(self, reason: str = "Manual Emergency Halt"):
        self._global_active = True
        self._activated_at = datetime.now(timezone.utc)
        self._activation_reason = reason
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.set_global_kill_switch_sync(True, reason)
        elif self.redis_manager:
            self.redis_manager._mem_kill_switch_global = (True, reason)

    def deactivate_global(self):
        self._global_active = False
        self._activated_at = None
        self._activation_reason = None
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.set_global_kill_switch_sync(False, "")
        elif self.redis_manager:
            self.redis_manager._mem_kill_switch_global = (False, "")

    def activate_user(self, user_id: str, reason: str = "User Emergency Stop"):
        self._user_switches[user_id] = True
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.set_user_kill_switch_sync(user_id, True, reason)
        elif self.redis_manager:
            self.redis_manager._mem_kill_switch_user[user_id] = (True, reason)

    def deactivate_user(self, user_id: str):
        self._user_switches.pop(user_id, None)
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.set_user_kill_switch_sync(user_id, False, "")
        elif self.redis_manager:
            self.redis_manager._mem_kill_switch_user.pop(user_id, None)

    def status(self) -> dict:
        halts = list(self._user_switches.keys())
        is_global = self.is_global_active
        reason = self._activation_reason

        if self.redis_manager and self.redis_manager.is_connected:
            act, g_reason = self.redis_manager.is_global_kill_switch_active_sync()
            if act:
                is_global = True
                reason = g_reason
        elif self.redis_manager:
            for uid, (act, _) in self.redis_manager._mem_kill_switch_user.items():
                if act and uid not in halts:
                    halts.append(uid)

        return {
            "global_kill_switch_active": is_global,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "reason": reason,
            "active_user_halts": halts,
        }
