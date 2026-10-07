"""
TradeForge Shared Intraday Session Manager.
Enforces institutional trading session rules in ONE unified place:
1. No-entry window after market open: Blocks new entries before 09:20:00 IST.
2. No-entry cutoff: Blocks new entries after 15:00:00 IST.
3. 15:15:00 IST square-off: Triggers automatic squaring-off of all intraday positions.
4. Daily trade cap: Halts trading when user hits max daily trades ceiling.
5. Consecutive loss pause: Pauses trading after 3 consecutive losses.

Backing: Per-user state (daily P&L, consecutive losses, daily trade count, session pause flags)
is persisted in Redis when connected, ensuring risk state survives process restarts.
"""

import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from tradeforge_shared.enums import (
    BrokerType,
    MarketRegime,
    OrderSide,
    StrategyType,
    TradingMode,
)
from tradeforge_shared.schemas import OrderProposal, Signal, UserRiskSettings

IST = timezone(timedelta(hours=5, minutes=30))
NO_ENTRY_BEFORE_TIME = time(9, 20, 0)
NO_ENTRY_AFTER_TIME = time(15, 0, 0)
SQUARE_OFF_CUTOFF_TIME = time(15, 15, 0)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        if 9 <= dt.hour <= 16:
            return dt.replace(tzinfo=IST)
        return dt.replace(tzinfo=timezone.utc).astimezone(IST)
    return dt.astimezone(IST)


class SessionManager:
    """
    Unified Session and Day-Risk Manager.
    Enforced by Risk Guard across backtest, paper, and live trading.
    Persists state to Redis when connected, keyed by user and trading date.
    """

    def __init__(self, redis_manager: Optional[Any] = None):
        self.redis_manager = redis_manager
        self._user_daily_trade_count: Dict[str, int] = {}
        self._user_consecutive_losses: Dict[str, int] = {}
        self._user_daily_pnl: Dict[str, float] = {}
        self._user_session_paused: Dict[str, Tuple[bool, str]] = {}

    def get_trading_date(self, current_time: Optional[datetime] = None) -> str:
        """Returns IST date string YYYY-MM-DD representing active trading session."""
        now = current_time or datetime.now(timezone.utc)
        return to_ist(now).strftime("%Y-%m-%d")

    def get_trade_count(self, user_id: str, current_time: Optional[datetime] = None) -> int:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            return self.redis_manager.get_risk_trade_count_sync(user_id, date_str)
        mem_key = f"{user_id}:{date_str}"
        return self._user_daily_trade_count.get(mem_key, self._user_daily_trade_count.get(user_id, 0))

    def get_consecutive_losses(self, user_id: str, current_time: Optional[datetime] = None) -> int:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            return self.redis_manager.get_risk_consecutive_losses_sync(user_id, date_str)
        mem_key = f"{user_id}:{date_str}"
        return self._user_consecutive_losses.get(mem_key, self._user_consecutive_losses.get(user_id, 0))

    def get_daily_pnl(self, user_id: str, current_time: Optional[datetime] = None) -> float:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            return self.redis_manager.get_risk_daily_pnl_sync(user_id, date_str)
        mem_key = f"{user_id}:{date_str}"
        return self._user_daily_pnl.get(mem_key, self._user_daily_pnl.get(user_id, 0.0))

    def record_trade(self, user_id: str, current_time: Optional[datetime] = None) -> None:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.record_risk_trade_execution_sync(user_id, date_str)
        else:
            mem_key = f"{user_id}:{date_str}"
            self._user_daily_trade_count[mem_key] = self._user_daily_trade_count.get(mem_key, 0) + 1
            self._user_daily_trade_count[user_id] = self._user_daily_trade_count[mem_key]

    def record_trade_result(self, user_id: str, net_pnl: float, current_time: Optional[datetime] = None) -> None:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.record_risk_trade_result_sync(user_id, date_str, net_pnl)
        else:
            mem_key = f"{user_id}:{date_str}"
            cur_pnl = self._user_daily_pnl.get(mem_key, 0.0) + net_pnl
            self._user_daily_pnl[mem_key] = round(cur_pnl, 2)
            self._user_daily_pnl[user_id] = self._user_daily_pnl[mem_key]

            if net_pnl < 0:
                cur_losses = self._user_consecutive_losses.get(mem_key, 0) + 1
                self._user_consecutive_losses[mem_key] = cur_losses
                self._user_consecutive_losses[user_id] = cur_losses
            else:
                self._user_consecutive_losses[mem_key] = 0
                self._user_consecutive_losses[user_id] = 0

    def pause_session(self, user_id: str, reason: str = "", current_time: Optional[datetime] = None) -> None:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            self.redis_manager.set_risk_session_paused_sync(user_id, date_str, True, reason)
        else:
            self._user_session_paused[f"{user_id}:{date_str}"] = (True, reason)
            self._user_session_paused[user_id] = (True, reason)

    def is_session_paused(self, user_id: str, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        date_str = self.get_trading_date(current_time)
        if self.redis_manager and self.redis_manager.is_connected:
            return self.redis_manager.is_risk_session_paused_sync(user_id, date_str)
        mem_key = f"{user_id}:{date_str}"
        return self._user_session_paused.get(mem_key, self._user_session_paused.get(user_id, (False, "")))

    def is_square_off_time(self, current_time: Optional[datetime] = None) -> bool:
        """Returns True if current time is at or after 15:15:00 IST."""
        now = current_time or datetime.now(timezone.utc)
        ist_time = to_ist(now).time()
        return ist_time >= SQUARE_OFF_CUTOFF_TIME

    def check_entry_allowed(
        self,
        user_id: str,
        user_settings: UserRiskSettings,
        current_time: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate session rules for new entries:
        1. No entries before 09:20 IST.
        2. No entries after 15:00 IST.
        3. Strict rejection after 15:15 IST (square-off period).
        4. Session pause check.
        5. Daily trade cap check.
        6. Consecutive loss pause check.
        """
        now = current_time or datetime.now(timezone.utc)
        ist_now = to_ist(now)
        cur_time = ist_now.time()

        # 1. No entries before 09:20 IST (first 5 minutes after 09:15 open)
        if cur_time < NO_ENTRY_BEFORE_TIME:
            return (
                False,
                f"Trading blocked: Current time {cur_time.strftime('%H:%M:%S')} IST is before strategy start window 09:20:00 IST.",
            )

        # 2. Strict square-off at or after 15:15 IST
        if cur_time >= SQUARE_OFF_CUTOFF_TIME:
            return (
                False,
                f"Intraday square-off cutoff reached: No new entries allowed after 15:15:00 IST (Current IST: {cur_time.strftime('%H:%M:%S')}).",
            )

        # 3. No new entries after 15:00 IST
        if cur_time >= NO_ENTRY_AFTER_TIME:
            return (
                False,
                f"Trading blocked: Current time {cur_time.strftime('%H:%M:%S')} IST is after strategy cutoff window 15:00:00 IST.",
            )

        # 4. Check if session was paused
        is_paused, pause_reason = self.is_session_paused(user_id, current_time=now)
        if is_paused:
            return (
                False,
                f"Trading session paused: {pause_reason or 'Risk pause active'}",
            )

        # 5. Daily trade cap (reads from Redis when connected)
        current_trades = self.get_trade_count(user_id, current_time=now)
        if current_trades >= user_settings.max_daily_trades:
            return (
                False,
                f"Daily trade limit reached: {current_trades}/{user_settings.max_daily_trades} trades executed today.",
            )

        # 6. Consecutive loss auto-stop (3 consecutive losses, reads from Redis when connected)
        current_losses = self.get_consecutive_losses(user_id, current_time=now)
        if current_losses >= user_settings.auto_stop_after_consecutive_losses:
            return (
                False,
                f"Auto-stop triggered: {current_losses} consecutive losses reached for today.",
            )

        return True, None

    def generate_square_off_proposals(
        self,
        user_id: str,
        open_positions: List[Dict[str, Any]],
        broker: BrokerType = BrokerType.PAPER,
        mode: TradingMode = TradingMode.PAPER,
        current_time: Optional[datetime] = None,
    ) -> List[OrderProposal]:
        """Generate market order proposals to square-off all open intraday positions."""
        now = current_time or datetime.now(timezone.utc)
        proposals: List[OrderProposal] = []

        for pos in open_positions:
            qty = pos.get("quantity", 0)
            if qty <= 0:
                continue

            symbol = pos["symbol"]
            pos_side = pos["side"]
            flatten_side = OrderSide.SELL if (pos_side == OrderSide.BUY or str(pos_side).upper() == "BUY") else OrderSide.BUY
            current_price = pos.get("current_price", pos.get("entry_price", 100.0))

            dummy_signal = Signal(
                id=f"sig_sq_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.SCALPER_1M,
                symbol=symbol,
                side=flatten_side,
                timeframe="1m",
                timestamp=now,
                entry_price=current_price,
                stop_loss=current_price * 1.05 if flatten_side == OrderSide.SELL else current_price * 0.95,
                target=current_price,
                regime=pos.get("regime", MarketRegime.RANGE_BOUND),
                quality_score=None,
                expected_net_gain_pct=0.0,
                reason="Automatic 15:15 IST intraday session square-off order",
            )

            proposal = OrderProposal(
                user_id=user_id,
                broker=broker,
                mode=mode,
                signal=dummy_signal,
                requested_quantity=qty,
                idempotency_key=f"sqoff_{user_id}_{symbol}_{uuid.uuid4().hex[:8]}",
            )
            proposals.append(proposal)

        return proposals

    def reset_daily_stats(self, user_id: Optional[str] = None) -> None:
        """Reset intraday statistics at market open (in-memory dev/test only)."""
        if user_id:
            self._user_daily_trade_count.pop(user_id, None)
            self._user_consecutive_losses.pop(user_id, None)
            self._user_daily_pnl.pop(user_id, None)
            self._user_session_paused.pop(user_id, None)
        else:
            self._user_daily_trade_count.clear()
            self._user_consecutive_losses.clear()
            self._user_daily_pnl.clear()
            self._user_session_paused.clear()
