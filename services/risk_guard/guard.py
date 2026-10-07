import asyncio
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from tradeforge_shared.enums import BrokerType, OrderType, TradingMode
from tradeforge_shared.schemas import (
    OrderProposal,
    RiskApproval,
    RiskCheckResult,
    UserRiskSettings,
)

from services.risk_guard.kill_switch import KillSwitch
from services.risk_guard.session_manager import SessionManager
from services.risk_guard.watchdog import FeedWatchdog


class RiskGuard:
    """
    Independent Pre-Trade Risk Verification Engine.
    Non-negotiable Rule 1: Every order must pass the Risk Guard.
    No code path may place an order without passing these checks.
    """
    def __init__(
        self,
        kill_switch: Optional[KillSwitch] = None,
        watchdog: Optional[FeedWatchdog] = None,
        signing_secret: Optional[str] = None,
        session_manager: Optional[SessionManager] = None,
        redis_manager: Optional[Any] = None,
    ):
        self.kill_switch = kill_switch or KillSwitch()
        self.watchdog = watchdog or FeedWatchdog()
        self.session_manager = session_manager or SessionManager()
        self.redis_manager = redis_manager

        # FIX-3: RiskGuard must refuse to sign approvals without an explicit signing key outside tests. No default key anywhere.
        env = os.getenv("ENVIRONMENT", "").lower()
        key = signing_secret or os.getenv("SECRET_KEY")
        if env not in ["test", "testing"]:
            if not key or key in (
                "dev_secret_key_needs_replacement_in_production_32chars",
                "tradeforge_risk_guard_hmac_signing_key_default_32b",
            ):
                raise RuntimeError(
                    "RiskGuard refuses to initialize without an explicit, secure signing key outside tests."
                )
        else:
            if not key:
                raise RuntimeError(
                    "RiskGuard refuses to initialize without an explicit signing key."
                )
        self.signing_secret = key
        self._processed_idempotency_keys: Set[str] = set()
        self._user_daily_pnl: Dict[str, float] = {}
        self._user_open_positions: Dict[str, int] = {}
        self._user_consecutive_losses: Dict[str, int] = {}
        self._user_daily_trade_count: Dict[str, int] = {}

        # Platform-level invariants (cannot be overridden by user)
        self.blocked_symbols: Set[str] = {
            "IDEA", "YESBANK", "SUZLON", "RCOM", "JPPOWER" # Examples of penny/illiquid/high-ASM names
        }
        self.max_order_value_inr: float = 1_000_000.0  # ₹10 Lakhs max per order
        self.max_price_deviation_pct: float = 0.025     # 2.5% fat finger circuit threshold

    def validate_proposal(
        self,
        proposal: OrderProposal,
        user_settings: UserRiskSettings,
        current_ltp: float,
        current_time: Optional[datetime] = None,
        enforce_trading_hours: bool = True,
    ) -> RiskCheckResult:
        """
        Execute exhaustive pre-trade verification.
        Returns RiskCheckResult indicating approval or list of violations.
        """
        violations = []
        user_id = proposal.user_id
        signal = proposal.signal
        now = current_time or datetime.now(timezone.utc)

        # 1. Kill Switch Check
        if self.kill_switch.is_active_for_user(user_id):
            violations.append("Kill switch is active. Trading is halted.")

        # 2. Watchdog data feed check (Market data feed must be fresh and within max staleness)
        is_fresh, delay_ms = self.watchdog.is_feed_fresh(signal.symbol, current_time=now)
        if not is_fresh:
            violations.append(
                f"Market data feed is stale or unavailable for {signal.symbol} "
                f"({delay_ms}ms > {self.watchdog.max_staleness_ms}ms). Trading halted."
            )

        # 3. Market Hours & 15:15 IST Square-Off Check (Delegated to SessionManager)
        if enforce_trading_hours:
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            now_ist = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(ist_tz)
            current_time_str = now_ist.strftime("%H:%M:%S")

            if self.session_manager.is_square_off_time(now):
                violations.append(
                    f"Intraday square-off cutoff reached: No new entries allowed after 15:15:00 IST (Current IST: {current_time_str})."
                )
            elif current_time_str < user_settings.trading_start_time_ist:
                violations.append(
                    f"Trading blocked: Current time {current_time_str} IST is before strategy start window {user_settings.trading_start_time_ist} IST."
                )
            elif current_time_str > user_settings.trading_end_time_ist:
                violations.append(
                    f"Trading blocked: Current time {current_time_str} IST is after strategy cutoff window {user_settings.trading_end_time_ist} IST."
                )

        # 4. Idempotency Check (Rule 8: Duplicate submissions must be impossible)
        # Note: Idempotency key is recorded strictly ONLY after an order is approved.
        is_duplicate = proposal.idempotency_key in self._processed_idempotency_keys
        if not is_duplicate and self.redis_manager:
            now_ts = time.time()
            exp = self.redis_manager._mem_idempotency_keys.get(proposal.idempotency_key, 0.0)
            if now_ts < exp:
                is_duplicate = True
        if is_duplicate:
            violations.append(f"Duplicate order submission rejected (Key: {proposal.idempotency_key})")

        # 5. Daily Trade Cap Check (Enforced via SessionManager)
        current_trade_count = self.session_manager.get_trade_count(user_id)
        if current_trade_count >= user_settings.max_daily_trades:
            violations.append(
                f"Daily trade limit reached: {current_trade_count}/{user_settings.max_daily_trades} trades executed today."
            )

        # 6. Paper mode enforcement (Rule 2: Paper mode is default)
        if proposal.mode == TradingMode.AUTO and user_settings.mode != TradingMode.AUTO:
            violations.append("Live Auto mode is not enabled for this user. 2FA verification required.")

        # 7. Mandatory Protective Stop Check (Rule 7)
        if not signal.stop_loss or signal.stop_loss <= 0:
            violations.append("Protective stop-loss is missing or invalid. Orders without stops are blocked.")

        stop_distance = abs(signal.entry_price - signal.stop_loss)
        if stop_distance <= 0:
            violations.append("Stop-loss price is identical to entry price.")

        # 8. Fat-finger Price Band Check
        price_deviation = abs(signal.entry_price - current_ltp) / current_ltp
        if price_deviation > self.max_price_deviation_pct:
            violations.append(
                f"Fat-finger check failed: Entry price deviates {price_deviation*100:.2f}% from LTP ({current_ltp})"
            )

        # 9. Instrument Whitelist & Blocklist
        if signal.symbol in self.blocked_symbols:
            violations.append(f"Symbol {signal.symbol} is on platform risk blocklist.")

        if user_settings.allowed_instruments and signal.symbol not in user_settings.allowed_instruments:
            violations.append(f"Symbol {signal.symbol} is not in user allowed instruments list.")

        # 10. Consecutive Loss Auto-Stop (Enforced via SessionManager)
        current_losses = self.session_manager.get_consecutive_losses(user_id)
        if current_losses >= user_settings.auto_stop_after_consecutive_losses:
            violations.append(
                f"Auto-stop triggered: {current_losses} consecutive losses reached for today."
            )

        # 11. Max Open Positions Check
        current_positions = self._user_open_positions.get(user_id, 0)
        if current_positions >= user_settings.max_open_positions:
            violations.append(
                f"Max open positions limit ({user_settings.max_open_positions}) reached."
            )

        # 12. Sizing & Loss per Trade Check
        # Rupee Risk = quantity * stop_distance
        calculated_risk = proposal.requested_quantity * stop_distance
        order_turnover = proposal.requested_quantity * signal.entry_price

        if order_turnover > self.max_order_value_inr:
            violations.append(
                f"Order turnover ₹{order_turnover:,.2f} exceeds platform ceiling of ₹{self.max_order_value_inr:,.2f}."
            )

        # Adjust quantity if requested risk exceeds per-trade limit
        adjusted_quantity = proposal.requested_quantity
        if calculated_risk > user_settings.max_loss_per_trade_inr:
            # Downsize quantity so risk fits within limit
            max_allowed_qty = int(user_settings.max_loss_per_trade_inr / stop_distance)
            if max_allowed_qty < 1:
                violations.append(
                    f"Stop distance ₹{stop_distance:.2f} exceeds max loss limit ₹{user_settings.max_loss_per_trade_inr:.2f} even for 1 share."
                )
            else:
                adjusted_quantity = max_allowed_qty
                calculated_risk = adjusted_quantity * stop_distance

        # 13. Daily Loss Limit Check
        current_daily_pnl = self._user_daily_pnl.get(user_id, 0.0)
        if current_daily_pnl <= -user_settings.max_daily_loss_inr:
            violations.append(
                f"Daily loss limit ₹{user_settings.max_daily_loss_inr:.2f} already breached today (Current P&L: ₹{current_daily_pnl:.2f})."
            )

        approved = len(violations) == 0
        approval: Optional[RiskApproval] = None
        if approved:
            # Rule 8: Record idempotency key strictly after order is approved
            self._processed_idempotency_keys.add(proposal.idempotency_key)
            if self.redis_manager:
                self.redis_manager._mem_idempotency_keys[proposal.idempotency_key] = time.time() + 86400
                if self.redis_manager._is_connected and self.redis_manager._redis:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self.redis_manager.check_and_record_idempotency_key(proposal.idempotency_key))
                        else:
                            loop.run_until_complete(self.redis_manager.check_and_record_idempotency_key(proposal.idempotency_key))
                    except Exception:
                        pass

            # Construct tamper-evident RiskApproval signed exclusively by RiskGuard
            canonical_proposal_data = (
                f"{proposal.user_id}:{proposal.broker.value}:{proposal.mode.value}:"
                f"{signal.symbol}:{signal.side.value}:{proposal.requested_quantity}:"
                f"{signal.entry_price:.4f}:{signal.stop_loss:.4f}:{signal.target:.4f}:"
                f"{proposal.idempotency_key}"
            )
            proposal_hash = hashlib.sha256(canonical_proposal_data.encode("utf-8")).hexdigest()
            approval_id = f"apr_{uuid.uuid4().hex[:12]}"
            expires_at = now + timedelta(seconds=30)

            approval = RiskApproval(
                approval_id=approval_id,
                proposal_hash=proposal_hash,
                user_id=proposal.user_id,
                broker=proposal.broker,
                symbol=signal.symbol,
                side=signal.side,
                order_type=OrderType.MARKET,
                approved_quantity=adjusted_quantity,
                price=signal.entry_price,
                stop_loss=signal.stop_loss,
                target=signal.target,
                idempotency_key=proposal.idempotency_key,
                mode=proposal.mode,
                created_at=now,
                expires_at=expires_at,
                signature="",
            )
            approval.signature = hmac.new(
                self.signing_secret.encode("utf-8"),
                approval.canonical_payload().encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

        reason = "Risk checks passed successfully" if approved else "; ".join(violations)

        return RiskCheckResult(
            approved=approved,
            reason=reason,
            adjusted_quantity=adjusted_quantity if approved else 0,
            calculated_risk_inr=calculated_risk if approved else 0.0,
            violations=violations,
            approval=approval,
        )

    def record_trade_execution(self, user_id: str):
        """Increment daily executed trade count."""
        self.session_manager.record_trade(user_id)
        self._user_daily_trade_count[user_id] = self.session_manager.get_trade_count(user_id)

    def record_trade_completion(self, user_id: str, net_pnl: float):
        """Update user intraday ledger after trade closure."""
        self.session_manager.record_trade_result(user_id, net_pnl)
        self._user_daily_pnl[user_id] = self.session_manager.get_daily_pnl(user_id)
        self._user_consecutive_losses[user_id] = self.session_manager.get_consecutive_losses(user_id)

    def update_open_positions(self, user_id: str, count: int):
        self._user_open_positions[user_id] = max(0, count)

    def generate_square_off_orders(
        self,
        user_id: str,
        open_positions: List[Dict[str, Any]],
        broker: BrokerType = BrokerType.PAPER,
        mode: TradingMode = TradingMode.PAPER,
        current_time: Optional[datetime] = None,
    ) -> List[OrderProposal]:
        """Generate closing orders for all open intraday positions."""
        return self.session_manager.generate_square_off_proposals(
            user_id=user_id,
            open_positions=open_positions,
            broker=broker,
            mode=mode,
            current_time=current_time,
        )
