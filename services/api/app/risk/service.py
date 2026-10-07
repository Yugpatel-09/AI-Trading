from services.api.app.core.redis_client import redis_manager
from services.risk_guard.guard import RiskGuard
from services.risk_guard.kill_switch import KillSwitch
from services.risk_guard.watchdog import FeedWatchdog

# Global singleton instances for API process lifecycle backed by Redis
global_kill_switch = KillSwitch(redis_manager=redis_manager)
global_watchdog = FeedWatchdog()
global_risk_guard = RiskGuard(
    kill_switch=global_kill_switch,
    watchdog=global_watchdog,
    redis_manager=redis_manager,
)
