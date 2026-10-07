"""
Feed Health Monitor and Alerting Service.

Monitors real-time market data stream health across all active instruments.
Enforces:
1. Per-symbol last-tick timestamp tracking.
2. STALE status detection when lag exceeds max_staleness_ms (default 5,000ms).
3. Direct synchronization with RiskGuard FeedWatchdog to halt new order entries.
4. Alerts dispatched to notification channels (Email / Telegram interface).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, Optional

from pydantic import BaseModel

from services.api.app.core.logging import logger
from services.risk_guard.watchdog import FeedWatchdog


class FeedStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"


class SymbolHealth(BaseModel):
    symbol: str
    status: FeedStatus
    last_tick_at: Optional[datetime] = None
    delay_ms: int = 0
    ticks_received: int = 0


class FeedHealthMonitor:
    """
    Supervises data feed liveness and coordinates automatic pre-trade risk halts.
    """

    def __init__(
        self,
        watchdog: Optional[FeedWatchdog] = None,
        max_staleness_ms: int = 5000,
        alert_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.max_staleness_ms = max_staleness_ms
        self.watchdog = watchdog or FeedWatchdog(max_staleness_ms=max_staleness_ms)
        self.alert_callback = alert_callback
        self._symbols: Dict[str, SymbolHealth] = {}
        self._stale_alerted: Dict[str, bool] = {}

    def register_symbol(self, symbol: str):
        sym = symbol.upper().strip()
        if sym not in self._symbols:
            self._symbols[sym] = SymbolHealth(
                symbol=sym,
                status=FeedStatus.DISCONNECTED,
            )
            self._stale_alerted[sym] = False

    def record_tick(self, symbol: str, tick_time: Optional[datetime] = None):
        """Update heartbeat upon tick arrival."""
        sym = symbol.upper().strip()
        self.register_symbol(sym)
        now = datetime.now(timezone.utc)
        t_time = tick_time or now

        # Sync with RiskGuard watchdog
        self.watchdog.record_heartbeat(sym, timestamp=t_time)

        h = self._symbols[sym]
        h.last_tick_at = t_time
        h.ticks_received += 1
        h.status = FeedStatus.HEALTHY
        h.delay_ms = int((now - t_time).total_seconds() * 1000)

        # Clear alert flag if healthy again
        if self._stale_alerted.get(sym, False):
            logger.info(f"[FEED HEALTH] Feed recovered for {sym}. Status: HEALTHY.")
            self._stale_alerted[sym] = False

    def evaluate_health(self, current_time: Optional[datetime] = None) -> Dict[str, SymbolHealth]:
        """Check all registered symbols against staleness thresholds."""
        now = current_time or datetime.now(timezone.utc)

        for sym, h in self._symbols.items():
            if not h.last_tick_at:
                h.status = FeedStatus.DISCONNECTED
                h.delay_ms = 999999
                continue

            delta_ms = int((now - h.last_tick_at).total_seconds() * 1000)
            h.delay_ms = max(0, delta_ms)

            if delta_ms > self.max_staleness_ms:
                h.status = FeedStatus.STALE
                if not self._stale_alerted.get(sym, False):
                    msg = (
                        f"CRITICAL: Market data feed STALE for {sym}! "
                        f"Lag: {delta_ms}ms > {self.max_staleness_ms}ms threshold. "
                        "RiskGuard auto-rejecting new trade entries."
                    )
                    logger.error(f"[FEED HEALTH] {msg}")
                    self._stale_alerted[sym] = True
                    if self.alert_callback:
                        self.alert_callback(sym, msg)
            elif delta_ms > (self.max_staleness_ms // 2):
                h.status = FeedStatus.DEGRADED
            else:
                h.status = FeedStatus.HEALTHY

        return dict(self._symbols)

    def is_symbol_healthy(self, symbol: str, current_time: Optional[datetime] = None) -> bool:
        """Returns True if the feed is fresh and safe for strategy execution."""
        sym = symbol.upper().strip()
        if sym not in self._symbols:
            return False
        self.evaluate_health(current_time=current_time)
        return self._symbols[sym].status == FeedStatus.HEALTHY


# Global singleton instance
feed_health_monitor = FeedHealthMonitor()
