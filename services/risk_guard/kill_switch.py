import asyncio
from datetime import datetime, timezone
from typing import Any, Optional


class KillSwitch:
    """
    Global and user-specific Emergency Circuit Breaker.
    When activated:
    - Rejects all subsequent inbound order proposals.
    - Signals order manager to cancel open limit orders.
    - Dispatches square-off requests for active market positions.
    Backing: Supports RedisStateManager for distributed volatile state with thread-safe memory fallback.
    """
    def __init__(self, redis_manager: Optional[Any] = None):
        self._global_active: bool = False
        self._activated_at: Optional[datetime] = None
        self._activation_reason: Optional[str] = None
        self._user_switches: dict[str, bool] = {}
        self.redis_manager = redis_manager

    @property
    def is_global_active(self) -> bool:
        if self._global_active:
            return True
        if self.redis_manager:
            active, _ = self.redis_manager._mem_kill_switch_global
            return active
        return False

    def is_active_for_user(self, user_id: str) -> bool:
        if self.is_global_active:
            return True
        if self._user_switches.get(user_id, False):
            return True
        if self.redis_manager:
            active, _ = self.redis_manager._mem_kill_switch_user.get(user_id, (False, ""))
            return active
        return False

    def activate_global(self, reason: str = "Manual Emergency Halt"):
        self._global_active = True
        self._activated_at = datetime.now(timezone.utc)
        self._activation_reason = reason
        if self.redis_manager:
            self.redis_manager._mem_kill_switch_global = (True, reason)
            if self.redis_manager._is_connected and self.redis_manager._redis:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.redis_manager.set_global_kill_switch(True, reason))
                    else:
                        loop.run_until_complete(self.redis_manager.set_global_kill_switch(True, reason))
                except Exception:
                    pass

    def deactivate_global(self):
        self._global_active = False
        self._activated_at = None
        self._activation_reason = None
        if self.redis_manager:
            self.redis_manager._mem_kill_switch_global = (False, "")
            if self.redis_manager._is_connected and self.redis_manager._redis:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.redis_manager.set_global_kill_switch(False, ""))
                    else:
                        loop.run_until_complete(self.redis_manager.set_global_kill_switch(False, ""))
                except Exception:
                    pass

    def activate_user(self, user_id: str, reason: str = "User Emergency Stop"):
        self._user_switches[user_id] = True
        if self.redis_manager:
            self.redis_manager._mem_kill_switch_user[user_id] = (True, reason)
            if self.redis_manager._is_connected and self.redis_manager._redis:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.redis_manager.set_user_kill_switch(user_id, True, reason))
                    else:
                        loop.run_until_complete(self.redis_manager.set_user_kill_switch(user_id, True, reason))
                except Exception:
                    pass

    def deactivate_user(self, user_id: str):
        self._user_switches.pop(user_id, None)
        if self.redis_manager:
            self.redis_manager._mem_kill_switch_user.pop(user_id, None)
            if self.redis_manager._is_connected and self.redis_manager._redis:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.redis_manager.set_user_kill_switch(user_id, False, ""))
                    else:
                        loop.run_until_complete(self.redis_manager.set_user_kill_switch(user_id, False, ""))
                except Exception:
                    pass

    def status(self) -> dict:
        halts = list(self._user_switches.keys())
        if self.redis_manager:
            for uid, (act, _) in self.redis_manager._mem_kill_switch_user.items():
                if act and uid not in halts:
                    halts.append(uid)
        return {
            "global_kill_switch_active": self.is_global_active,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "reason": self._activation_reason,
            "active_user_halts": halts,
        }
