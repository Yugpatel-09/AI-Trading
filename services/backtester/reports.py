"""
TradeForge Institutional Backtest Reporting Engine.
Calculates net performance after Indian statutory costs, maximum drawdown,
profit factor, payoff ratio, per-month results (INCLUDING losing months),
and raises explicit OVERFITTING WARNINGS when metrics appear unrealistically high.
"""

from typing import Any, Dict, List, Optional


class BacktestReport:
    """
    Comprehensive backtest analytics report.
    """

    def __init__(
        self,
        symbol: str,
        strategy_name: str,
        initial_capital: float,
        trades: List[Any],
        equity_curve: List[float],
    ):
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.initial_capital = initial_capital
        self.trades = trades
        self.equity_curve = equity_curve

    def generate_report(self) -> Dict[str, Any]:
        total_trades = len(self.trades)
        if total_trades == 0:
            return {
                "symbol": self.symbol,
                "strategy": self.strategy_name,
                "total_trades": 0,
                "initial_capital": self.initial_capital,
                "final_equity": self.initial_capital,
                "gross_profit_inr": 0.0,
                "total_statutory_taxes_inr": 0.0,
                "net_profit_after_costs_inr": 0.0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "average_win_inr": 0.0,
                "average_loss_inr": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_inr": 0.0,
                "max_drawdown_pct": 0.0,
                "monthly_breakdown": {},
                "overfitting_warning": None,
                "trades": [],
            }

        winning_trades = [t for t in self.trades if t.cost_breakdown.net_pnl > 0]
        losing_trades = [t for t in self.trades if t.cost_breakdown.net_pnl <= 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades) * 100.0

        gross_profit = sum(t.cost_breakdown.gross_pnl for t in self.trades)
        total_costs = sum(t.cost_breakdown.total_costs for t in self.trades)
        net_profit = sum(t.cost_breakdown.net_pnl for t in self.trades)

        final_equity = self.initial_capital + net_profit

        # Average Win & Average Loss
        total_gains = sum(t.cost_breakdown.net_pnl for t in winning_trades)
        total_losses = abs(sum(t.cost_breakdown.net_pnl for t in losing_trades))

        avg_win = (total_gains / win_count) if win_count > 0 else 0.0
        avg_loss = (total_losses / loss_count) if loss_count > 0 else 0.0
        profit_factor = (total_gains / total_losses) if total_losses > 0 else (99.0 if total_gains > 0 else 0.0)

        # Max Drawdown Calculation
        peak = self.initial_capital
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = (max_dd / peak * 100.0) if peak > 0 else 0.0

        # Monthly Breakdown (Strictly includes losing months)
        monthly_data: Dict[str, Dict[str, Any]] = {}
        for t in self.trades:
            # Entry timestamp month key: YYYY-MM
            entry_dt = t.entry_time
            m_key = entry_dt.strftime("%Y-%m") if hasattr(entry_dt, "strftime") else str(entry_dt)[:7]
            if m_key not in monthly_data:
                monthly_data[m_key] = {
                    "month": m_key,
                    "trade_count": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "gross_pnl": 0.0,
                    "total_costs": 0.0,
                    "net_pnl": 0.0,
                }
            m_stats = monthly_data[m_key]
            m_stats["trade_count"] += 1
            if t.cost_breakdown.net_pnl > 0:
                m_stats["winning_trades"] += 1
            else:
                m_stats["losing_trades"] += 1
            m_stats["gross_pnl"] += t.cost_breakdown.gross_pnl
            m_stats["total_costs"] += t.cost_breakdown.total_costs
            m_stats["net_pnl"] += t.cost_breakdown.net_pnl

        # Round monthly values and calculate win rate
        for m_key, m_stats in monthly_data.items():
            cnt = m_stats["trade_count"]
            m_stats["win_rate_pct"] = round((m_stats["winning_trades"] / cnt) * 100.0, 2) if cnt > 0 else 0.0
            m_stats["gross_pnl"] = round(m_stats["gross_pnl"], 2)
            m_stats["total_costs"] = round(m_stats["total_costs"], 2)
            m_stats["net_pnl"] = round(m_stats["net_pnl"], 2)

        # Overfitting Warning Evaluation
        overfitting_warning: Optional[str] = None
        losing_months_count = sum(1 for m in monthly_data.values() if m["net_pnl"] < 0)

        # Criteria for suspicion of overfitting / curve-fitting:
        # 1. Win rate > 85% on significant sample (>= 20 trades)
        # 2. Profit factor > 5.0 on significant sample
        # 3. Zero losing months across >= 3 active months
        if total_trades >= 20 and win_rate > 85.0:
            overfitting_warning = (
                f"OVERFITTING WARNING: Win rate of {win_rate:.1f}% is unrealistically high for intraday NSE equity. "
                f"High probability of curve-fitting, lookahead bias, or unmodeled adverse selection."
            )
        elif total_trades >= 20 and profit_factor > 5.0:
            overfitting_warning = (
                f"OVERFITTING WARNING: Profit factor of {profit_factor:.2f} exceeds realistic institutional benchmarks. "
                f"Verify slippage parameters and execution assumptions."
            )
        elif len(monthly_data) >= 3 and losing_months_count == 0 and total_trades >= 30:
            overfitting_warning = (
                "OVERFITTING WARNING: Zero losing months detected across 3+ months of backtest. "
                "Intraday strategies invariably experience losing regimes; results may not generalize out-of-sample."
            )

        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "gross_profit_inr": round(gross_profit, 2),
            "total_statutory_taxes_inr": round(total_costs, 2),
            "net_profit_after_costs_inr": round(net_profit, 2),
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "average_win_inr": round(avg_win, 2),
            "average_loss_inr": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_inr": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "monthly_breakdown": monthly_data,
            "overfitting_warning": overfitting_warning,
            "trades": [t.to_dict() for t in self.trades[:50]],
        }
