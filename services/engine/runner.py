"""
TradeForge Trading Loop Runner Service.
Processes continuous market candle streams, updates the shared institutional FeatureStore,
evaluates strategies, routes proposals through Risk Guard to OrderManager/PaperBroker,
and persists orders, fills, positions, and closed trades to the database repository.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tradeforge_shared.costs import IndianCostCalculator
from tradeforge_shared.enums import (
    BrokerType,
    OrderSide,
    OrderStatus,
    TradingMode,
)
from tradeforge_shared.schemas import Candle, ExecutionOrder, OrderProposal, UserRiskSettings

from services.api.app.core.logging import logger
from services.api.app.db.repositories.audit_repo import AuditRepository
from services.api.app.db.repositories.order_repo import OrderRepository
from services.engine.data_feed.resampler import resample_candles
from services.engine.features.store import FeatureStore
from services.engine.strategies.base import BaseStrategy, StrategyContext
from services.execution.order_manager import OrderManager
from services.risk_guard.guard import RiskGuard


class MarketDataProvider(ABC):
    """Abstract interface for streaming market candles."""
    @abstractmethod
    async def stream_candles(self, symbol: str) -> AsyncGenerator[Candle, None]:
        """Yield sequential candles in chronological order."""
        pass


class HistoricalReplayProvider(MarketDataProvider):
    """
    High-fidelity replay provider for historical or synthetic candles.
    Enables realistic, tick-by-tick / candle-by-candle verification without lookahead bias.
    """
    def __init__(self, candles: List[Candle]):
        self.candles = sorted(candles, key=lambda c: c.timestamp)

    async def stream_candles(self, symbol: str) -> AsyncGenerator[Candle, None]:
        target_sym = symbol.upper().strip()
        for c in self.candles:
            if c.symbol.upper().strip() == target_sym:
                yield c


class TradingLoopRunner:
    """
    Autonomous Trading Loop Runner Service.
    Connects:
      Data Provider -> Feature Store -> Strategies -> Risk Guard -> OrderManager -> Broker -> DB Repositories.
    """
    def __init__(
        self,
        provider: MarketDataProvider,
        strategies: List[BaseStrategy],
        user_settings: UserRiskSettings,
        session_factory: async_sessionmaker[AsyncSession],
        order_manager: Optional[OrderManager] = None,
        risk_guard: Optional[RiskGuard] = None,
        symbol: str = "NIFTY",
        broker: BrokerType = BrokerType.PAPER,
        mode: TradingMode = TradingMode.PAPER,
        lot_size: int = 25,
        slippage_bps: float = 2.0,
        spread_bps: float = 1.0,
    ):
        self.provider = provider
        self.strategies = strategies
        self.user_settings = user_settings
        self.session_factory = session_factory
        self.symbol = symbol.upper().strip()
        self.broker = broker
        self.mode = mode
        self.lot_size = lot_size
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps

        # Execution and risk components
        self.risk_guard = risk_guard or RiskGuard()
        self.order_manager = order_manager or OrderManager(
            risk_guard=self.risk_guard,
            paper_initial_capital=user_settings.capital_allocated_inr,
            paper_slippage_bps=slippage_bps,
            paper_spread_bps=spread_bps,
        )

        self.cost_calculator = IndianCostCalculator()

        # In-memory execution state
        self.candles_1m: List[Candle] = []
        self.active_position: Optional[Dict[str, Any]] = None
        self.executed_orders: List[ExecutionOrder] = []
        self.executed_trades: List[Dict[str, Any]] = []

    async def run(self) -> Dict[str, Any]:
        """
        Execute the trading loop for all candles emitted by the data provider.
        Returns execution statistics and persists all state to the database.
        """
        logger.info(f"Starting TradingLoopRunner for {self.symbol} in {self.mode.value} mode...")

        async for candle_1m in self.provider.stream_candles(self.symbol):
            # 1. Feed Watchdog heartbeat to prevent stale feed risk trips
            self.risk_guard.watchdog.record_heartbeat(self.symbol, current_time=candle_1m.timestamp)

            # 2. Maintain 1-minute buffer and compute multi-timeframe resampled candles
            self.candles_1m.append(candle_1m)

            candles_5m = resample_candles(self.candles_1m, "5m") if len(self.candles_1m) >= 5 else []
            candles_10m = resample_candles(self.candles_1m, "10m") if len(self.candles_1m) >= 10 else []
            candles_15m = resample_candles(self.candles_1m, "15m") if len(self.candles_1m) >= 15 else []

            # 3. Institutional Feature Store computation
            features_df = FeatureStore.compute_features_df(self.candles_1m)
            latest_features = features_df.iloc[-1].to_dict() if not features_df.empty else {}

            vwap = float(latest_features.get("vwap", candle_1m.vwap or candle_1m.close))
            daily_open = float(self.candles_1m[0].open)
            or_high = latest_features.get("opening_range_high")
            or_low = latest_features.get("opening_range_low")

            # 4. Check exit for existing open position (Stop Loss, Target, or Intraday Cutoff 15:15 IST)
            if self.active_position is not None:
                await self._evaluate_position_exit(candle_1m)

            # 5. Check strategy entry setups if no active position
            if self.active_position is None:
                context = StrategyContext(
                    symbol=self.symbol,
                    current_candle=candle_1m,
                    candle_history_1m=self.candles_1m,
                    candle_history_5m=candles_5m,
                    candle_history_10m=candles_10m,
                    candle_history_15m=candles_15m,
                    vwap=vwap,
                    daily_open=daily_open,
                    opening_range_high=or_high,
                    opening_range_low=or_low,
                    features=latest_features,
                )

                await self._evaluate_strategy_signals(context, candle_1m)

        # End of session summary
        total_gross = sum(t["gross_pnl"] for t in self.executed_trades)
        total_net = sum(t["net_pnl"] for t in self.executed_trades)
        total_costs = sum(t["total_costs"] for t in self.executed_trades)

        summary = {
            "symbol": self.symbol,
            "candles_processed": len(self.candles_1m),
            "orders_placed": len(self.executed_orders),
            "trades_completed": len(self.executed_trades),
            "gross_pnl": round(total_gross, 2),
            "net_pnl": round(total_net, 2),
            "total_costs": round(total_costs, 2),
        }
        logger.info(f"TradingLoopRunner finished: {summary}")
        return summary

    async def _evaluate_position_exit(self, candle: Candle) -> None:
        """Evaluate protective stop-loss, profit target, or session square-off cutoff."""
        pos = self.active_position
        if not pos:
            return

        side = pos["side"]
        qty = pos["quantity"]
        entry_price = pos["entry_price"]
        stop_loss = pos["stop_loss"]
        target = pos["target"]
        entry_time = pos["entry_time"]
        order_id = pos["order_id"]

        is_square_off = self.risk_guard.session_manager.is_square_off_time(candle.timestamp)

        exit_triggered = False
        exit_price = candle.close
        reason = ""

        if side == OrderSide.BUY:
            if candle.low <= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                reason = "STOP_LOSS_HIT"
            elif candle.high >= target:
                exit_triggered = True
                exit_price = target
                reason = "TARGET_HIT"
            elif is_square_off:
                exit_triggered = True
                exit_price = candle.close
                reason = "SESSION_SQUARE_OFF_CUTOFF"

            if exit_triggered:
                breakdown = self.cost_calculator.calculate_round_trip(
                    buy_price=entry_price,
                    sell_price=exit_price,
                    quantity=qty,
                    slippage_bps=self.slippage_bps,
                )
        else:  # OrderSide.SELL (Short)
            if candle.high >= stop_loss:
                exit_triggered = True
                exit_price = stop_loss
                reason = "STOP_LOSS_HIT"
            elif candle.low <= target:
                exit_triggered = True
                exit_price = target
                reason = "TARGET_HIT"
            elif is_square_off:
                exit_triggered = True
                exit_price = candle.close
                reason = "SESSION_SQUARE_OFF_CUTOFF"

            if exit_triggered:
                breakdown = self.cost_calculator.calculate_round_trip(
                    buy_price=exit_price,
                    sell_price=entry_price,
                    quantity=qty,
                    slippage_bps=self.slippage_bps,
                )

        if exit_triggered:
            trade_record = {
                "user_id": self.user_settings.user_id,
                "order_id": order_id,
                "symbol": self.symbol,
                "side": side,
                "quantity": qty,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_pnl": breakdown.gross_pnl,
                "net_pnl": breakdown.net_pnl,
                "total_costs": breakdown.total_costs,
                "entry_time": entry_time,
                "exit_time": candle.timestamp,
                "reason": reason,
            }
            self.executed_trades.append(trade_record)

            # Persist to database repository
            async with self.session_factory() as session:
                o_repo = OrderRepository(session)
                a_repo = AuditRepository(session)

                # Close position
                await o_repo.update_position(
                    user_id=self.user_settings.user_id,
                    broker=self.broker,
                    symbol=self.symbol,
                    side=side,
                    quantity=0,
                    price=exit_price,
                    stop_loss=0.0,
                    target=0.0,
                )

                # Record trade
                await o_repo.record_trade(
                    user_id=self.user_settings.user_id,
                    order_id=order_id,
                    symbol=self.symbol,
                    side=side,
                    quantity=qty,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    gross_pnl=round(breakdown.gross_pnl, 2),
                    net_pnl=round(breakdown.net_pnl, 2),
                    total_costs=round(breakdown.total_costs, 2),
                    entry_time=entry_time,
                    exit_time=candle.timestamp,
                )

                # Append-only audit log entry
                await a_repo.log_action(
                    action="POSITION_CLOSED",
                    resource=f"trade/{order_id}",
                    details={
                        "symbol": self.symbol,
                        "exit_price": exit_price,
                        "net_pnl": breakdown.net_pnl,
                        "reason": reason,
                    },
                    user_id=self.user_settings.user_id,
                )
                await session.commit()

            # Update Risk Guard intraday ledger
            self.risk_guard.record_trade_completion(self.user_settings.user_id, breakdown.net_pnl)
            self.risk_guard.update_open_positions(self.user_settings.user_id, 0)
            self.active_position = None

    async def _evaluate_strategy_signals(self, context: StrategyContext, candle: Candle) -> None:
        """Evaluate strategies and route any actionable signal through OrderManager."""
        for strategy in self.strategies:
            signal = strategy.on_candle(context)
            if not signal:
                continue

            # Construct Proposal
            proposal = OrderProposal(
                user_id=self.user_settings.user_id,
                broker=self.broker,
                mode=self.mode,
                signal=signal,
                requested_quantity=self.lot_size,
                idempotency_key=f"run_{self.symbol}_{candle.timestamp.isoformat()}_{strategy.strategy_type.value}",
            )

            try:
                # Sole path to execution: must pass Risk Guard and OrderManager
                order = await self.order_manager.submit_order(
                    proposal=proposal,
                    user_settings=self.user_settings,
                    current_ltp=candle.close,
                    current_time=candle.timestamp,
                    enforce_trading_hours=True,
                )

                if order.status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILL):
                    self.executed_orders.append(order)
                    fill_price = order.average_fill_price or signal.entry_price

                    # Persist Order, Fill, and Position to DB repository
                    async with self.session_factory() as session:
                        o_repo = OrderRepository(session)
                        a_repo = AuditRepository(session)

                        await o_repo.save_order(order)
                        await o_repo.record_fill(
                            order_id=order.order_id,
                            user_id=self.user_settings.user_id,
                            symbol=self.symbol,
                            side=signal.side,
                            filled_quantity=order.filled_quantity,
                            fill_price=fill_price,
                            fee_amount=0.0,
                        )
                        await o_repo.update_position(
                            user_id=self.user_settings.user_id,
                            broker=self.broker,
                            symbol=self.symbol,
                            side=signal.side,
                            quantity=order.filled_quantity,
                            price=fill_price,
                            stop_loss=signal.stop_loss,
                            target=signal.target,
                        )
                        await a_repo.log_action(
                            action="ORDER_EXECUTED",
                            resource=f"orders/{order.order_id}",
                            details={
                                "symbol": self.symbol,
                                "side": signal.side.value,
                                "quantity": order.filled_quantity,
                                "fill_price": fill_price,
                                "strategy": strategy.strategy_type.value,
                            },
                            user_id=self.user_settings.user_id,
                        )
                        await session.commit()

                    # Track position in runner and RiskGuard
                    self.active_position = {
                        "order_id": order.order_id,
                        "side": signal.side,
                        "quantity": order.filled_quantity,
                        "entry_price": fill_price,
                        "stop_loss": signal.stop_loss,
                        "target": signal.target,
                        "entry_time": candle.timestamp,
                    }
                    self.risk_guard.record_trade_execution(self.user_settings.user_id)
                    self.risk_guard.update_open_positions(self.user_settings.user_id, 1)

                    # Only one trade entry per candle timestamp
                    break

            except Exception as e:
                logger.warning(f"Strategy signal submission rejected or blocked by risk guard: {e}")
