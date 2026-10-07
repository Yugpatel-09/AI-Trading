import time
from typing import Dict, Optional, Tuple

import redis as syncredis
import redis.asyncio as aioredis

from services.api.app.core.config import settings
from services.api.app.core.logging import logger


class RedisStateManager:
    """
    Redis volatile state manager for rate limits, lockouts, kill-switch flags,
    idempotency keys, and intraday per-user risk state.

    Enforces Non-Negotiable Rules with Redis backing:
    - Real reads from Redis when connected (no stale _mem_* bypass).
    - Fail-closed refusal to start in staging/production if Redis is unreachable.
    - Full support for both async (FastAPI routes) and sync (RiskGuard/SessionManager) access.
    """
    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_client: Optional[aioredis.Redis] = None,
        sync_redis_client: Optional[syncredis.Redis] = None,
    ):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[aioredis.Redis] = redis_client
        self._sync_redis: Optional[syncredis.Redis] = sync_redis_client
        self._is_connected: bool = bool(redis_client or sync_redis_client)

        # In-memory storage fallback used strictly in test or development when Redis is disconnected
        self._mem_counters: Dict[str, list] = {}
        self._mem_lockouts: Dict[str, float] = {}
        self._mem_kill_switch_global: Tuple[bool, str] = (False, "")
        self._mem_kill_switch_user: Dict[str, Tuple[bool, str]] = {}
        self._mem_idempotency_keys: Dict[str, float] = {}

        # In-memory per-user risk state fallback for dev/test
        self._mem_risk_trade_count: Dict[str, int] = {}
        self._mem_risk_pnl: Dict[str, float] = {}
        self._mem_risk_consecutive_losses: Dict[str, int] = {}
        self._mem_risk_open_positions: Dict[str, int] = {}
        self._mem_risk_session_paused: Dict[str, Tuple[bool, str]] = {}

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self) -> None:
        """Attempt connection to Redis server (async and sync)."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
            await self._redis.ping()

            self._sync_redis = syncredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
            self._sync_redis.ping()

            self._is_connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            self._is_connected = False
            self._redis = None
            self._sync_redis = None
            if settings.ENVIRONMENT not in ("development", "test"):
                raise RuntimeError(
                    f"Fatal: Redis daemon unreachable at {self.redis_url} in environment '{settings.ENVIRONMENT}'. "
                    "Startup aborted per Non-Negotiable Rule."
                ) from e
            logger.info(f"Redis daemon not reachable ({e}). Using in-memory fallback in {settings.ENVIRONMENT} mode.")

    def connect_sync(self) -> None:
        """Synchronously connect to Redis (for standalone test or worker processes)."""
        try:
            self._sync_redis = syncredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
            self._sync_redis.ping()
            self._is_connected = True
        except Exception as e:
            self._is_connected = False
            self._sync_redis = None
            if settings.ENVIRONMENT not in ("development", "test"):
                raise RuntimeError(
                    f"Fatal: Redis daemon unreachable at {self.redis_url} in environment '{settings.ENVIRONMENT}'. "
                    "Startup aborted per Non-Negotiable Rule."
                ) from e

    async def disconnect(self) -> None:
        if self._redis and self._is_connected:
            await self._redis.aclose()
        if self._sync_redis and self._is_connected:
            self._sync_redis.close()
        self._is_connected = False

    # -------------------------------------------------------------------------
    # Rate Limiting (Sliding Window Sorted Set)
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
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error during rate limit check in production: {e}") from e
                logger.warning(f"Redis rate limit error ({e}), falling back to memory in test/dev.")

        # In-memory fallback allowed only in test/development
        timestamps = self._mem_counters.get(key, [])
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]
        if len(valid_timestamps) >= max_requests:
            self._mem_counters[key] = valid_timestamps
            return False
        valid_timestamps.append(now)
        self._mem_counters[key] = valid_timestamps
        return True

    def check_rate_limit_sync(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds

        if self._is_connected and self._sync_redis:
            try:
                pipe = self._sync_redis.pipeline()
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, window_seconds + 5)
                _, _, count, _ = pipe.execute()
                return count <= max_requests
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error during sync rate limit check in production: {e}") from e

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
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording lockout in production: {e}") from e

        self._mem_lockouts[key] = time.time() + duration_seconds

    def record_lockout_sync(self, key: str, duration_seconds: int) -> None:
        if self._is_connected and self._sync_redis:
            try:
                self._sync_redis.set(f"lockout:{key}", "1", ex=duration_seconds)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording lockout in production: {e}") from e

        self._mem_lockouts[key] = time.time() + duration_seconds

    async def is_locked_out(self, key: str) -> bool:
        """Check if key is currently under lockout. Reads directly from Redis when connected."""
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get(f"lockout:{key}")
                return val is not None
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking lockout in production: {e}") from e

        expiry = self._mem_lockouts.get(key, 0.0)
        return time.time() < expiry

    def is_locked_out_sync(self, key: str) -> bool:
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(f"lockout:{key}")
                return val is not None
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking lockout in production: {e}") from e

        expiry = self._mem_lockouts.get(key, 0.0)
        return time.time() < expiry

    # -------------------------------------------------------------------------
    # Kill Switches (Global and Per-User)
    # -------------------------------------------------------------------------
    async def set_global_kill_switch(self, active: bool, reason: str = "") -> None:
        if self._is_connected and self._redis:
            try:
                if active:
                    await self._redis.set("kill_switch:global", reason or "1")
                else:
                    await self._redis.delete("kill_switch:global")
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting kill switch in production: {e}") from e

        self._mem_kill_switch_global = (active, reason)

    def set_global_kill_switch_sync(self, active: bool, reason: str = "") -> None:
        if self._is_connected and self._sync_redis:
            try:
                if active:
                    self._sync_redis.set("kill_switch:global", reason or "1")
                else:
                    self._sync_redis.delete("kill_switch:global")
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting kill switch in production: {e}") from e

        self._mem_kill_switch_global = (active, reason)

    async def is_global_kill_switch_active(self) -> Tuple[bool, str]:
        """Reads directly from Redis when connected."""
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get("kill_switch:global")
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking kill switch in production: {e}") from e

        return self._mem_kill_switch_global

    def is_global_kill_switch_active_sync(self) -> Tuple[bool, str]:
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get("kill_switch:global")
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking kill switch in production: {e}") from e

        return self._mem_kill_switch_global

    async def set_user_kill_switch(self, user_id: str, active: bool, reason: str = "") -> None:
        key = f"kill_switch:user:{user_id}"
        if self._is_connected and self._redis:
            try:
                if active:
                    await self._redis.set(key, reason or "1")
                else:
                    await self._redis.delete(key)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting user kill switch in production: {e}") from e

        self._mem_kill_switch_user[user_id] = (active, reason)

    def set_user_kill_switch_sync(self, user_id: str, active: bool, reason: str = "") -> None:
        key = f"kill_switch:user:{user_id}"
        if self._is_connected and self._sync_redis:
            try:
                if active:
                    self._sync_redis.set(key, reason or "1")
                else:
                    self._sync_redis.delete(key)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting user kill switch in production: {e}") from e

        self._mem_kill_switch_user[user_id] = (active, reason)

    async def is_user_kill_switch_active(self, user_id: str) -> Tuple[bool, str]:
        """Reads directly from Redis when connected."""
        key = f"kill_switch:user:{user_id}"
        if self._is_connected and self._redis:
            try:
                val = await self._redis.get(key)
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking user kill switch in production: {e}") from e

        return self._mem_kill_switch_user.get(user_id, (False, ""))

    def is_user_kill_switch_active_sync(self, user_id: str) -> Tuple[bool, str]:
        key = f"kill_switch:user:{user_id}"
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(key)
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking user kill switch in production: {e}") from e

        return self._mem_kill_switch_user.get(user_id, (False, ""))

    # -------------------------------------------------------------------------
    # Idempotency Key Tracking
    # -------------------------------------------------------------------------
    async def record_idempotency_key(self, key: str, ttl_seconds: int = 86400) -> None:
        """Mark idempotency key as recorded in Redis."""
        if self._is_connected and self._redis:
            try:
                await self._redis.set(f"idemp:{key}", "1", ex=ttl_seconds)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording idempotency key in production: {e}") from e

        self._mem_idempotency_keys[key] = time.time() + ttl_seconds

    def record_idempotency_key_sync(self, key: str, ttl_seconds: int = 86400) -> None:
        if self._is_connected and self._sync_redis:
            try:
                self._sync_redis.set(f"idemp:{key}", "1", ex=ttl_seconds)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording idempotency key in production: {e}") from e

        self._mem_idempotency_keys[key] = time.time() + ttl_seconds

    async def is_idempotency_key_present(self, key: str) -> bool:
        """Checks directly in Redis if idempotency key exists."""
        if self._is_connected and self._redis:
            try:
                exists = await self._redis.exists(f"idemp:{key}")
                return bool(exists)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking idempotency key in production: {e}") from e

        now = time.time()
        expiry = self._mem_idempotency_keys.get(key, 0.0)
        return now < expiry

    def is_idempotency_key_present_sync(self, key: str) -> bool:
        if self._is_connected and self._sync_redis:
            try:
                exists = self._sync_redis.exists(f"idemp:{key}")
                return bool(exists)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking idempotency key in production: {e}") from e

        now = time.time()
        expiry = self._mem_idempotency_keys.get(key, 0.0)
        return now < expiry

    async def check_and_record_idempotency_key(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Atomic check-and-record. Returns True if key was NEW, False if ALREADY USED."""
        if self._is_connected and self._redis:
            try:
                is_set = await self._redis.set(f"idemp:{key}", "1", nx=True, ex=ttl_seconds)
                return bool(is_set)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error in check_and_record_idempotency_key in production: {e}") from e

        now = time.time()
        expiry = self._mem_idempotency_keys.get(key, 0.0)
        if now < expiry:
            return False
        self._mem_idempotency_keys[key] = now + ttl_seconds
        return True

    def check_and_record_idempotency_key_sync(self, key: str, ttl_seconds: int = 86400) -> bool:
        if self._is_connected and self._sync_redis:
            try:
                is_set = self._sync_redis.set(f"idemp:{key}", "1", nx=True, ex=ttl_seconds)
                return bool(is_set)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error in sync check_and_record_idempotency_key in production: {e}") from e

        now = time.time()
        expiry = self._mem_idempotency_keys.get(key, 0.0)
        if now < expiry:
            return False
        self._mem_idempotency_keys[key] = now + ttl_seconds
        return True

    # -------------------------------------------------------------------------
    # Intraday Per-User Risk State (FIX-6)
    # Keyed by risk:{user_id}:{date_str}:{metric} with 48h TTL
    # -------------------------------------------------------------------------
    def _risk_key(self, user_id: str, date_str: str, metric: str) -> str:
        return f"risk:{user_id}:{date_str}:{metric}"

    def record_risk_trade_execution_sync(self, user_id: str, date_str: str) -> int:
        """Increment daily executed trade count for user and trading date."""
        key = self._risk_key(user_id, date_str, "trades")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.incr(key)
                self._sync_redis.expire(key, 172800)
                return int(val)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording trade execution in production: {e}") from e

        mem_key = f"{user_id}:{date_str}"
        new_val = self._mem_risk_trade_count.get(mem_key, 0) + 1
        self._mem_risk_trade_count[mem_key] = new_val
        return new_val

    def get_risk_trade_count_sync(self, user_id: str, date_str: str) -> int:
        key = self._risk_key(user_id, date_str, "trades")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(key)
                return int(val) if val is not None else 0
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error getting trade count in production: {e}") from e

        return self._mem_risk_trade_count.get(f"{user_id}:{date_str}", 0)

    def record_risk_trade_result_sync(self, user_id: str, date_str: str, net_pnl: float) -> Tuple[float, int]:
        """Update daily PnL and consecutive losses."""
        pnl_key = self._risk_key(user_id, date_str, "pnl")
        loss_key = self._risk_key(user_id, date_str, "consecutive_losses")

        if self._is_connected and self._sync_redis:
            try:
                new_pnl = float(self._sync_redis.incrbyfloat(pnl_key, net_pnl))
                self._sync_redis.expire(pnl_key, 172800)

                if net_pnl < 0:
                    new_losses = int(self._sync_redis.incr(loss_key))
                    self._sync_redis.expire(loss_key, 172800)
                else:
                    self._sync_redis.set(loss_key, "0", ex=172800)
                    new_losses = 0

                return (round(new_pnl, 2), new_losses)
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error recording trade result in production: {e}") from e

        mem_key = f"{user_id}:{date_str}"
        cur_pnl = self._mem_risk_pnl.get(mem_key, 0.0) + net_pnl
        self._mem_risk_pnl[mem_key] = round(cur_pnl, 2)
        if net_pnl < 0:
            cur_losses = self._mem_risk_consecutive_losses.get(mem_key, 0) + 1
            self._mem_risk_consecutive_losses[mem_key] = cur_losses
        else:
            self._mem_risk_consecutive_losses[mem_key] = 0
            cur_losses = 0

        return (round(cur_pnl, 2), cur_losses)

    def get_risk_daily_pnl_sync(self, user_id: str, date_str: str) -> float:
        pnl_key = self._risk_key(user_id, date_str, "pnl")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(pnl_key)
                return round(float(val), 2) if val is not None else 0.0
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error getting daily PnL in production: {e}") from e

        return self._mem_risk_pnl.get(f"{user_id}:{date_str}", 0.0)

    def get_risk_consecutive_losses_sync(self, user_id: str, date_str: str) -> int:
        loss_key = self._risk_key(user_id, date_str, "consecutive_losses")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(loss_key)
                return int(val) if val is not None else 0
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error getting consecutive losses in production: {e}") from e

        return self._mem_risk_consecutive_losses.get(f"{user_id}:{date_str}", 0)

    def set_risk_open_positions_sync(self, user_id: str, date_str: str, count: int) -> None:
        key = self._risk_key(user_id, date_str, "open_positions")
        if self._is_connected and self._sync_redis:
            try:
                self._sync_redis.set(key, str(max(0, count)), ex=172800)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting open positions in production: {e}") from e

        self._mem_risk_open_positions[f"{user_id}:{date_str}"] = max(0, count)

    def get_risk_open_positions_sync(self, user_id: str, date_str: str) -> int:
        key = self._risk_key(user_id, date_str, "open_positions")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(key)
                return int(val) if val is not None else 0
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error getting open positions in production: {e}") from e

        return self._mem_risk_open_positions.get(f"{user_id}:{date_str}", 0)

    def set_risk_session_paused_sync(self, user_id: str, date_str: str, paused: bool, reason: str = "") -> None:
        key = self._risk_key(user_id, date_str, "paused")
        if self._is_connected and self._sync_redis:
            try:
                if paused:
                    self._sync_redis.set(key, reason or "1", ex=172800)
                else:
                    self._sync_redis.delete(key)
                return
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error setting pause flag in production: {e}") from e

        self._mem_risk_session_paused[f"{user_id}:{date_str}"] = (paused, reason)

    def is_risk_session_paused_sync(self, user_id: str, date_str: str) -> Tuple[bool, str]:
        key = self._risk_key(user_id, date_str, "paused")
        if self._is_connected and self._sync_redis:
            try:
                val = self._sync_redis.get(key)
                if val is not None:
                    return (True, str(val))
                return (False, "")
            except Exception as e:
                if settings.ENVIRONMENT not in ("development", "test"):
                    raise RuntimeError(f"Redis error checking pause flag in production: {e}") from e

        return self._mem_risk_session_paused.get(f"{user_id}:{date_str}", (False, ""))

    def reset_in_memory(self) -> None:
        """Clear memory structures for clean test runs."""
        self._mem_counters.clear()
        self._mem_lockouts.clear()
        self._mem_kill_switch_global = (False, "")
        self._mem_kill_switch_user.clear()
        self._mem_idempotency_keys.clear()
        self._mem_risk_trade_count.clear()
        self._mem_risk_pnl.clear()
        self._mem_risk_consecutive_losses.clear()
        self._mem_risk_open_positions.clear()
        self._mem_risk_session_paused.clear()


# Global Redis state manager instance
redis_manager = RedisStateManager()
