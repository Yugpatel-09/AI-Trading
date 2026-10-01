from typing import List, Dict, Any, Optional
from datetime import datetime
from tradeforge_shared.schemas import Candle, Signal
from tradeforge_shared.costs import IndianCostCalculator, IndianCostBreakdown
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
        if len(candles) < 25:
            return {"error": "Insufficient candle data for backtesting (min 25 candles required)"}

        symbol = candles[0].symbol
        trades: List[BacktestTradeResult] = []
        equity_curve: List[float] = [initial_capital]
        current_equity = initial_capital

        active_trade: Optional[Dict[str, Any]] = None
        opening_range_high = max(c.high for c in candles[:3]) if len(candles) >= 3 else None
        opening_range_low = min(c.low for c in candles[:3]) if len(candles) >= 3 else None

        for i in range(20, len(candles)):
            current_bar = candles[i]
            history = candles[:i]

            # 1. Manage active position if one exists
            if active_trade:
                entry_price = active_trade["entry_price"]
                stop_loss = active_trade["stop_loss"]
                target = active_trade["target"]
                qty = active_trade["quantity"]
                bars_held = active_trade["bars_held"] + 1
                active_trade["bars_held"] = bars_held

                exit_price = None
                exit_reason = None

                # Check Stop-Loss hit
                if current_bar.low <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "STOP_LOSS_HIT"
                # Check Target hit
                elif current_bar.high >= target:
                    exit_price = target
                    exit_reason = "TARGET_HIT"
                # Time Stop exit (e.g. 15 bars)
                elif bars_held >= active_trade["time_stop_bars"]:
                    exit_price = current_bar.close
                    exit_reason = "TIME_STOP_EXPIRED"

                if exit_price is not None:
                    # Calculate Indian statutory costs
                    costs = self.cost_calc.calculate_round_trip(
                        buy_price=entry_price,
                        sell_price=exit_price,
                        quantity=qty,
                    )
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

            # 2. Evaluate entry signal using identical strategy logic
            context = StrategyContext(
                symbol=symbol,
                current_candle=current_bar,
                candle_history_1m=history,
                candle_history_5m=history,
                candle_history_10m=history,
                vwap=current_bar.vwap or current_bar.close,
                daily_open=candles[0].open,
                opening_range_high=opening_range_high,
                opening_range_low=opening_range_low,
            )

            signal = strategy.on_candle(context)
            if signal and signal.stop_loss:
                stop_distance = abs(signal.entry_price - signal.stop_loss)
                if stop_distance > 0:
                    qty = max(1, int(risk_per_trade_inr / stop_distance))
                    # Pre-trade cost check: Expected gain must beat estimated statutory costs
                    estimated_costs = self.cost_calc.calculate_round_trip(
                        buy_price=signal.entry_price,
                        sell_price=signal.target,
                        quantity=qty,
                    )
                    # Filter: setup rejected if net profit is <= 0 after taxes
                    if estimated_costs.net_pnl > 0:
                        active_trade = {
                            "signal": signal,
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
            "trades": [t.to_dict() for t in trades[:25]], # First 25 trades
        }
