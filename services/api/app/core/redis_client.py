import time
from typing import Dict, Optional, Tuple

import redis.asyncio as aioredis

from services.api.app.core.config import settings
from services.api.app.core.logging import logger


class RedisStateManager:
    """
    Redis volatile state manager for rate limits, lockouts, kill-switch flags, and idempotency.
    Enforces Non-Negotiable Rules with Redis backing, providing thread-safe fallback in test/dev.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[aioredis.Redis] = None
        self._is_connected: bool = False

        # In-memory fast storage fallback when Redis daemon is not running
        self._mem_counters: Dict[str, list] = {}
        self._mem_lockouts: Dict[str, float] = {}
        self._mem_kill_switch_global: Tuple[bool, str] = (False, "")
        self._mem_kill_switch_user: Dict[str, Tuple[bool, str]] = {}
        self._mem_idempotency_keys: Dict[str, float] = {}

    async def connect(self) -> None:
        """Attempt connection to Redis server."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
            await self._redis.ping()
            self._is_connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            self._is_connected = False
            self._redis = None
            logger.info(f"Redis daemon not reachable ({e}). Using in-memory volatile store fallback.")

    async def disconnect(self) -> None:
        if self._redis and self._is_connected:
            await self._redis.aclose()
            self._is_connected = False

    # -------------------------------------------------------------------------
    # Rate Limiting (Sliding Window)
    # -------------------------------------------------------------------------
    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Sliding window rate limit.
        Returns True if request is ALLOWED, False if RATE LIMITED (exceeded limit).
        """
        now = time.time()
        cutoff = now - window_seconds

        if self._is_connected and self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, window_seconds + 5)
                _, _, count, _ = await pipe.execute()
                return count <= max_requests
            except Exception as e:
                logger.warning(f"Redis rate limit error ({e}), falling back to memory.")

        # In-memory fallback
        timestamps = self._mem_counters.get(key, [])
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]
        if len(valid_timestamps) >= max_requests:
            self._mem_counters[key] = valid_timestamps
            return False
        valid_timestamps.append(now)
        self._mem_counters[key] = valid_timestamps
        return True

    # -------------------------------------------------------------------------
    # Lockouts (Brute-Force & 2FA Protection)
    # -------------------------------------------------------------------------
    async def record_lockout(self, key: str, duration_seconds: int) -> None:
        """Lock out a key (IP or user) for specified duration."""
        if self._is_connected and self._redis:
            try:
                await self._redis.set(f"lockout:{key}", "1", ex=duration_seconds)
                return
            except Exception as e:
                logger.warning(f"Redis lockout record error ({e}).")

        self._mem_lockouts[key] = time.time() + duration_seconds

    async def is_locked_out(self, key: str) -> bool:
        """Check if key is currently under lockout."""
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get(f"lockout:{key}")
                return val is not None
            except Exception as e:
                logger.warning(f"Redis lockout check error ({e}).")

        expiry = self._mem_lockouts.get(key, 0.0)
        return time.time() < expiry

    # -------------------------------------------------------------------------
    # Kill Switches
    # -------------------------------------------------------------------------
    async def set_global_kill_switch(self, active: bool, reason: str = "") -> None:
        if self._is_connected and self._redis:
            try:
                if active:
                    await self._redis.set("kill_switch:global", reason or "1")
                else:
                    await self._redis.delete("kill_switch:global")
            except Exception as e:
                logger.warning(f"Redis set global kill switch error ({e}).")

        self._mem_kill_switch_global = (active, reason)

    async def is_global_kill_switch_active(self) -> Tuple[bool, str]:
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get("kill_switch:global")
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                logger.warning(f"Redis check global kill switch error ({e}).")

        return self._mem_kill_switch_global

    async def set_user_kill_switch(self, user_id: str, active: bool, reason: str = "") -> None:
        if self._is_connected and self._redis:
            try:
                key = f"kill_switch:user:{user_id}"
                if active:
                    await self._redis.set(key, reason or "1")
                else:
                    await self._redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis set user kill switch error ({e}).")

        self._mem_kill_switch_user[user_id] = (active, reason)

    async def is_user_kill_switch_active(self, user_id: str) -> Tuple[bool, str]:
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get(f"kill_switch:user:{user_id}")
                if val is not None:
                    return (True, str(val))
            except Exception as e:
                logger.warning(f"Redis check user kill switch error ({e}).")

        return self._mem_kill_switch_user.get(user_id, (False, ""))

    # -------------------------------------------------------------------------
    # Idempotency Key Tracking
    # -------------------------------------------------------------------------
    async def check_and_record_idempotency_key(self, key: str, ttl_seconds: int = 86400) -> bool:
        """
        Record idempotency key if not present.
        Returns True if key was NEW and successfully set.
        Returns False if key was ALREADY USED (duplicate detected).
        """
        if self._is_connected and self._redis:
            try:
                # SET key 1 NX EX ttl
                is_set = await self._redis.set(f"idemp:{key}", "1", nx=True, ex=ttl_seconds)
                return bool(is_set)
            except Exception as e:
                logger.warning(f"Redis idempotency error ({e}).")

        now = time.time()
        expiry = self._mem_idempotency_keys.get(key, 0.0)
        if now < expiry:
            return False  # Already present and valid
        self._mem_idempotency_keys[key] = now + ttl_seconds
        return True

    def reset_in_memory(self) -> None:
        """Clear memory structures for clean test runs."""
        self._mem_counters.clear()
        self._mem_lockouts.clear()
        self._mem_kill_switch_global = (False, "")
        self._mem_kill_switch_user.clear()
        self._mem_idempotency_keys.clear()


# Global Redis state manager instance
redis_manager = RedisStateManager()
