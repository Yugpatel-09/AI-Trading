from datetime import datetime, timezone


class FeedWatchdog:
    """
    Monitors market data freshness and feed latency.
    Blueprint Rule: If data is stale for more than 5 seconds (5,000ms),
    strategies halt and an alert fires.
    """
    def __init__(self, max_staleness_ms: int = 5000):
        self.max_staleness_ms = max_staleness_ms
        self._last_tick_time: dict[str, datetime] = {}

    def record_heartbeat(self, symbol: str, timestamp: datetime | None = None, current_time: datetime | None = None):
        """Record latest tick/candle reception timestamp."""
        self._last_tick_time[symbol] = timestamp or current_time or datetime.now(timezone.utc)

    def is_feed_fresh(self, symbol: str, current_time: datetime | None = None) -> tuple[bool, int]:
        """
        Check if feed for a symbol is within allowable latency.
        Returns: (is_fresh: bool, delay_ms: int)
        """
        if symbol not in self._last_tick_time:
            return False, 999999

        now = current_time or datetime.now(timezone.utc)
        delta_ms = int((now - self._last_tick_time[symbol]).total_seconds() * 1000)
        is_fresh = delta_ms <= self.max_staleness_ms
        return is_fresh, delta_ms
