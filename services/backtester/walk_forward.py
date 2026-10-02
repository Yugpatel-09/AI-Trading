"""
TradeForge Walk-Forward Validation Engine.
Splits historical datasets into rolling out-of-sample evaluation windows to verify
that intraday strategies generalize without curve-fitting.
"""

from typing import Any, Callable, Dict, List, Optional

from tradeforge_shared.schemas import Candle

from services.backtester.engine import Backtester
from services.engine.strategies.base import BaseStrategy


class WalkForwardValidator:
    """
    Rolling Walk-Forward Engine.
    Executes sequential out-of-sample validation windows.
    """

    def __init__(
        self,
        backtester: Optional[Backtester] = None,
        n_splits: int = 3,
        out_of_sample_ratio: float = 0.3,
    ):
        self.backtester = backtester or Backtester()
        self.n_splits = max(2, n_splits)
        self.out_of_sample_ratio = out_of_sample_ratio

    def run_walk_forward(
        self,
        strategy_factory: Callable[[], BaseStrategy],
        candles: List[Candle],
        initial_capital: float = 100000.0,
        risk_per_trade_inr: float = 1000.0,
    ) -> Dict[str, Any]:
        """
        Execute walk-forward out-of-sample validation across sequential rolling partitions.
        """
        n = len(candles)
        if n < 60:
            return {"error": "Insufficient candle data for walk-forward validation (min 60 required)"}

        # Divide into n_splits sequential chronological chunks
        chunk_size = n // self.n_splits
        split_reports: List[Dict[str, Any]] = []

        total_oos_net_pnl = 0.0
        total_oos_trades = 0
        total_oos_wins = 0

        for i in range(self.n_splits):
            start_i = i * chunk_size
            end_i = (i + 1) * chunk_size if i < self.n_splits - 1 else n
            split_candles = candles[start_i:end_i]

            split_n = len(split_candles)
            train_len = int(split_n * (1.0 - self.out_of_sample_ratio))
            test_candles = split_candles[train_len:]

            if len(test_candles) < 15:
                continue

            # Instantiate a fresh strategy instance for the out-of-sample window
            strategy = strategy_factory()
            test_res = self.backtester.run(
                strategy=strategy,
                candles=test_candles,
                initial_capital=initial_capital,
                risk_per_trade_inr=risk_per_trade_inr,
            )

            trades_cnt = test_res.get("total_trades", 0)
            net_pnl = test_res.get("net_profit_after_costs_inr", 0.0)
            wins_cnt = test_res.get("winning_trades", 0)

            total_oos_net_pnl += net_pnl
            total_oos_trades += trades_cnt
            total_oos_wins += wins_cnt

            split_reports.append({
                "split_index": i + 1,
                "start_timestamp": test_candles[0].timestamp.isoformat(),
                "end_timestamp": test_candles[-1].timestamp.isoformat(),
                "test_candles_count": len(test_candles),
                "trades": trades_cnt,
                "net_profit_after_costs_inr": net_pnl,
                "win_rate_pct": test_res.get("win_rate_pct", 0.0),
                "profit_factor": test_res.get("profit_factor", 0.0),
                "max_drawdown_pct": test_res.get("max_drawdown_pct", 0.0),
            })

        overall_win_rate = (total_oos_wins / total_oos_trades * 100.0) if total_oos_trades > 0 else 0.0

        return {
            "validation_mode": "WALK_FORWARD",
            "n_splits": len(split_reports),
            "out_of_sample_ratio": self.out_of_sample_ratio,
            "total_out_of_sample_trades": total_oos_trades,
            "total_out_of_sample_net_pnl": round(total_oos_net_pnl, 2),
            "overall_out_of_sample_win_rate": round(overall_win_rate, 2),
            "window_results": split_reports,
        }
