"""
TradeForge Cost-Aware Intraday Backtesting Engine.
Executes the exact same strategy code that runs in paper and live trading.
Models full Indian statutory costs (STT, GST, Stamp, Turnover, SEBI fees) and slippage.
Delivers genuine multi-timeframe candle series (1m, 5m, 10m, 15m) without lookahead bias.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from tradeforge_shared.costs import IndianCostBreakdown, IndianCostCalculator
from tradeforge_shared.enums import OrderSide
from tradeforge_shared.schemas import Candle, Signal

from services.engine.data_feed.resampler import resample_candles
from services.engine.features.store import FeatureStore
from services.engine.strategies.base import BaseStrategy, StrategyContext


class BacktestTradeResult:
    def __init__(
        self,
        signal: Signal,
        entry_time: datetime,
        exit_time: datetime,
        entry_price: float,
        exit_price: float,
        quantity: int,
        exit_reason: str,
        cost_breakdown: IndianCostBreakdown,
    ):
        self.signal = signal
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.quantity = quantity
        self.exit_reason = exit_reason
        self.cost_breakdown = cost_breakdown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.signal.symbol,
            "side": self.signal.side.value if hasattr(self.signal.side, "value") else str(self.signal.side),
            "entry_time": self.entry_time.isoformat() if hasattr(self.entry_time, "isoformat") else str(self.entry_time),
            "exit_time": self.exit_time.isoformat() if hasattr(self.exit_time, "isoformat") else str(self.exit_time),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "exit_reason": self.exit_reason,
            "gross_pnl": self.cost_breakdown.gross_pnl,
            "total_costs": self.cost_breakdown.total_costs,
            "net_pnl": self.cost_breakdown.net_pnl,
        }


class Backtester:
    """
    Cost-Aware Intraday Backtesting Engine.
    Executes the exact same strategy code that runs in live trading.
    Models real Indian statutory costs (STT, GST, Stamp, Turnover, SEBI) and slippage.
    """
    def __init__(self, cost_calculator: Optional[IndianCostCalculator] = None):
        self.cost_calc = cost_calculator or IndianCostCalculator(default_slippage_bps=5.0)

    def run(
        self,
        strategy: BaseStrategy,
        candles: List[Candle],
        initial_capital: float = 100000.0,
        risk_per_trade_inr: float = 1000.0,
    ) -> Dict[str, Any]:
        if len(candles) < 20:
            return {"error": "Insufficient candle data for backtesting (min 20 candles required)"}

        symbol = candles[0].symbol
        base_timeframe = candles[0].timeframe
        trades: List[BacktestTradeResult] = []
        equity_curve: List[float] = [initial_capital]
        current_equity = initial_capital

        active_trade: Optional[Dict[str, Any]] = None

        # 1. Compute multi-timeframe series from input data without lookahead bias
        candles_1m: List[Candle] = []
        candles_5m: List[Candle] = []
        candles_10m: List[Candle] = []
        candles_15m: List[Candle] = []

        if base_timeframe == "1m":
            candles_1m = candles
            candles_5m = resample_candles(candles, target_timeframe="5m", complete_only=True)
            candles_10m = resample_candles(candles, target_timeframe="10m", complete_only=True)
            candles_15m = resample_candles(candles, target_timeframe="15m", complete_only=True)
        elif base_timeframe == "5m":
            candles_5m = candles
            candles_10m = resample_candles(candles, target_timeframe="10m", complete_only=True)
            candles_15m = resample_candles(candles, target_timeframe="15m", complete_only=True)
        elif base_timeframe == "10m":
            candles_10m = candles
        elif base_timeframe == "15m":
            candles_15m = candles

        # Pre-compute features from the shared FeatureStore
        df_features = FeatureStore.compute_features_df(candles)

        # Pre-compute closed candles index pointers for zero-lookahead lookup
        # A higher timeframe candle starting at S with length M is closed at S + M
        def get_closed_subseries(series: List[Candle], current_time: datetime, duration_minutes: int) -> List[Candle]:
            cutoff = current_time - timedelta(minutes=0)
            return [c for c in series if c.timestamp + timedelta(minutes=duration_minutes) <= cutoff]

        start_idx = min(20, len(candles) - 1)
        for i in range(start_idx, len(candles)):
            current_bar = candles[i]
            cur_time = current_bar.timestamp

            # 2. Manage active position if one exists
            if active_trade:
                entry_price = active_trade["entry_price"]
                stop_loss = active_trade["stop_loss"]
                target = active_trade["target"]
                qty = active_trade["quantity"]
                trade_side = active_trade["side"]
                bars_held = active_trade["bars_held"] + 1
                active_trade["bars_held"] = bars_held

                exit_price = None
                exit_reason = None

                if trade_side == OrderSide.BUY:
                    # Long Position: Stop below entry, Target above entry
                    if current_bar.low <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS_HIT"
                    elif current_bar.high >= target:
                        exit_price = target
                        exit_reason = "TARGET_HIT"
                    elif bars_held >= active_trade["time_stop_bars"]:
                        exit_price = current_bar.close
                        exit_reason = "TIME_STOP_EXPIRED"

                    if exit_price is not None:
                        costs = self.cost_calc.calculate_round_trip(
                            buy_price=entry_price,
                            sell_price=exit_price,
                            quantity=qty,
                        )
                else:
                    # Short Position: Stop above entry, Target below entry
                    if current_bar.high >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS_HIT"
                    elif current_bar.low <= target:
                        exit_price = target
                        exit_reason = "TARGET_HIT"
                    elif bars_held >= active_trade["time_stop_bars"]:
                        exit_price = current_bar.close
                        exit_reason = "TIME_STOP_EXPIRED"

                    if exit_price is not None:
                        costs = self.cost_calc.calculate_round_trip(
                            buy_price=exit_price,
                            sell_price=entry_price,
                            quantity=qty,
                        )

                if exit_price is not None:
                    trade_res = BacktestTradeResult(
                        signal=active_trade["signal"],
                        entry_time=active_trade["entry_time"],
                        exit_time=current_bar.timestamp,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=qty,
                        exit_reason=exit_reason,
                        cost_breakdown=costs,
                    )
                    trades.append(trade_res)
                    current_equity += costs.net_pnl
                    equity_curve.append(current_equity)
                    active_trade = None
                continue

            # 3. Build time-accurate multi-timeframe history
            if base_timeframe == "1m":
                hist_1m = candles_1m[:i]
                hist_5m = get_closed_subseries(candles_5m, cur_time, 5)
                hist_10m = get_closed_subseries(candles_10m, cur_time, 10)
                hist_15m = get_closed_subseries(candles_15m, cur_time, 15)
            elif base_timeframe == "5m":
                hist_1m = []
                hist_5m = candles_5m[:i]
                hist_10m = get_closed_subseries(candles_10m, cur_time, 10)
                hist_15m = get_closed_subseries(candles_15m, cur_time, 15)
            elif base_timeframe == "10m":
                hist_1m = []
                hist_5m = []
                hist_10m = candles_10m[:i]
                hist_15m = get_closed_subseries(candles_15m, cur_time, 15)
            else:
                hist_1m = []
                hist_5m = []
                hist_10m = []
                hist_15m = candles[:i]

            # 4. Extract features from the unified feature store
            feat_row = df_features.iloc[i] if i < len(df_features) else None
            vwap = (
                float(feat_row["vwap"])
                if feat_row is not None and not pd.isna(feat_row["vwap"])
                else (current_bar.vwap or current_bar.close)
            )
            daily_open = (
                float(feat_row["daily_open"])
                if feat_row is not None and not pd.isna(feat_row["daily_open"])
                else candles[0].open
            )
            or_h = (
                float(feat_row["opening_range_high"])
                if feat_row is not None and not pd.isna(feat_row["opening_range_high"])
                else None
            )
            or_l = (
                float(feat_row["opening_range_low"])
                if feat_row is not None and not pd.isna(feat_row["opening_range_low"])
                else None
            )

            context = StrategyContext(
                symbol=symbol,
                current_candle=current_bar,
                candle_history_1m=hist_1m,
                candle_history_5m=hist_5m,
                candle_history_10m=hist_10m,
                candle_history_15m=hist_15m,
                vwap=vwap,
                daily_open=daily_open,
                opening_range_high=or_h,
                opening_range_low=or_l,
                features=feat_row.to_dict() if feat_row is not None else {},
            )

            signal = strategy.on_candle(context)
            if signal and signal.stop_loss:
                stop_distance = abs(signal.entry_price - signal.stop_loss)
                if stop_distance > 0:
                    qty = max(1, int(risk_per_trade_inr / stop_distance))
                    # Pre-trade cost check: Expected gain must beat estimated statutory costs
                    if signal.side == OrderSide.BUY:
                        estimated_costs = self.cost_calc.calculate_round_trip(
                            buy_price=signal.entry_price,
                            sell_price=signal.target,
                            quantity=qty,
                        )
                    else:
                        estimated_costs = self.cost_calc.calculate_round_trip(
                            buy_price=signal.target,
                            sell_price=signal.entry_price,
                            quantity=qty,
                        )

                    # Filter: setup rejected if net profit is <= 0 after taxes
                    if estimated_costs.net_pnl > 0:
                        active_trade = {
                            "signal": signal,
                            "side": signal.side,
                            "entry_price": signal.entry_price,
                            "stop_loss": signal.stop_loss,
                            "target": signal.target,
                            "quantity": qty,
                            "entry_time": current_bar.timestamp,
                            "time_stop_bars": 15,
                            "bars_held": 0,
                        }

        # Calculate summary statistics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.cost_breakdown.net_pnl > 0]
        losing_trades = [t for t in trades if t.cost_breakdown.net_pnl <= 0]
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t.cost_breakdown.gross_pnl for t in trades)
        total_taxes_and_costs = sum(t.cost_breakdown.total_costs for t in trades)
        net_profit = sum(t.cost_breakdown.net_pnl for t in trades)

        # Drawdown calculation
        peak = initial_capital
        max_drawdown = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_drawdown:
                max_drawdown = dd
        max_dd_pct = (max_drawdown / peak * 100) if peak > 0 else 0.0

        return {
            "symbol": symbol,
            "strategy": strategy.strategy_type.value,
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate_pct": round(win_rate, 2),
            "initial_capital": initial_capital,
            "final_equity": round(current_equity, 2),
            "gross_profit_inr": round(gross_profit, 2),
            "total_statutory_taxes_inr": round(total_taxes_and_costs, 2),
            "net_profit_after_costs_inr": round(net_profit, 2),
            "max_drawdown_inr": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "trades": [t.to_dict() for t in trades[:25]],
        }
