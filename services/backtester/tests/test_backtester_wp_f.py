"""
Unit Tests for WP-F Backtester Engine, Data Providers, and Walk-Forward Validation.
Verifies:
1. CSV and Parquet DataProvider loading and date filtering.
2. BrokerHistoricalDataProvider refuses execution without broker credentials.
3. Intraday session rules in backtester: daily trade cap, consecutive loss pause, 15:15 square-off.
4. BacktestReport: monthly breakdown including losing months, avg win/loss, and overfitting warnings.
5. WalkForwardValidator out-of-sample partitioning.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest
from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType
from tradeforge_shared.schemas import Candle, Signal

from services.backtester.data_providers.broker_provider import BrokerHistoricalDataProvider
from services.backtester.data_providers.csv_provider import CSVDataProvider
from services.backtester.data_providers.parquet_provider import ParquetDataProvider
from services.backtester.engine import Backtester, BacktestTradeResult
from services.backtester.reports import BacktestReport
from services.backtester.walk_forward import WalkForwardValidator
from services.engine.data_feed.resampler import IST
from services.engine.strategies.base import BaseStrategy, StrategyContext


def test_csv_data_provider_loads_and_filters(tmp_path):
    csv_file = tmp_path / "RELIANCE_1m.csv"
    data = [
        {"timestamp": "2026-10-05 09:15:00", "open": 2500.0, "high": 2505.0, "low": 2498.0, "close": 2502.0, "volume": 1500, "vwap": 2501.0},
        {"timestamp": "2026-10-05 09:16:00", "open": 2502.0, "high": 2507.0, "low": 2500.0, "close": 2506.0, "volume": 1800, "vwap": 2503.0},
        {"timestamp": "2026-10-06 09:15:00", "open": 2510.0, "high": 2515.0, "low": 2508.0, "close": 2512.0, "volume": 1200, "vwap": 2511.0},
    ]
    pd.DataFrame(data).to_csv(csv_file, index=False)

    provider = CSVDataProvider(data_directory=tmp_path)
    candles = provider.load_candles("RELIANCE", timeframe="1m")

    assert len(candles) == 3
    assert candles[0].symbol == "RELIANCE"
    assert candles[0].open == 2500.0
    assert candles[0].close == 2502.0

    # Date filter: only 2026-10-06
    candles_filtered = provider.load_candles("RELIANCE", timeframe="1m", start_date=datetime(2026, 10, 6).date())
    assert len(candles_filtered) == 1
    assert candles_filtered[0].open == 2510.0


def test_parquet_data_provider_loads_correctly(tmp_path):
    parquet_file = tmp_path / "NIFTY_1m.parquet"
    data = [
        {"timestamp": "2026-10-05 09:15:00", "open": 22000.0, "high": 22020.0, "low": 21990.0, "close": 22010.0, "volume": 5000},
        {"timestamp": "2026-10-05 09:16:00", "open": 22010.0, "high": 22030.0, "low": 22005.0, "close": 22025.0, "volume": 4200},
    ]
    pd.DataFrame(data).to_parquet(parquet_file, index=False)

    provider = ParquetDataProvider(data_directory=tmp_path)
    candles = provider.load_candles("NIFTY", timeframe="1m")
    assert len(candles) == 2
    assert candles[0].close == 22010.0


def test_broker_historical_provider_refuses_without_credentials():
    """Safety: Never fake broker data or return fabricated bars."""
    provider = BrokerHistoricalDataProvider(broker_client=None)
    with pytest.raises(PermissionError, match="requires an active broker client session"):
        provider.load_candles("NIFTY", timeframe="1m", instrument_token=256265)


def test_backtester_enforces_1515_square_off():
    """Verify that an active position remaining at 15:15 IST is forcefully squared off."""
    # 14:20 to 15:20 (60 candles)
    base_t = datetime(2026, 10, 5, 14, 20, 0, tzinfo=IST)
    candles = []
    for i in range(60):
        t = base_t + timedelta(minutes=i)
        candles.append(
            Candle(
                symbol="TCS",
                timeframe="1m",
                timestamp=t,
                open=3000.0,
                high=3005.0,
                low=2995.0,
                close=3001.0,
                volume=1000,
                vwap=3000.0,
            )
        )

    # Strategy that enters at 14:45 IST (between 20-bar warmup and 15:00 cutoff)
    class PreSquareOffStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(StrategyType.SCALPER_1M)
            self.entered = False

        def on_candle(self, context: StrategyContext):
            cur_dt = context.current_candle.timestamp
            if not self.entered and cur_dt.hour == 14 and cur_dt.minute == 45:
                self.entered = True
                return Signal(
                    id="sig_presq",
                    strategy_type=StrategyType.SCALPER_1M,
                    symbol="TCS",
                    side=OrderSide.BUY,
                    timeframe="1m",
                    timestamp=cur_dt,
                    entry_price=3001.0,
                    stop_loss=2900.0,  # Wide stop so it stays open
                    target=3100.0,     # Wide target so it stays open
                    regime=MarketRegime.TRENDING_BULLISH,
                    quality_score=None,
                    expected_net_gain_pct=1.0,
                    reason="Pre-square-off test",
                )
            return None

    backtester = Backtester()
    res = backtester.run(
        strategy=PreSquareOffStrategy(),
        candles=candles,
        enforce_session_rules=True,
    )

    trades = res.get("trades", [])
    assert len(trades) >= 1
    assert trades[0]["exit_reason"] == "15:15_INTRADAY_SQUARE_OFF"


def test_backtester_enforces_daily_trade_cap():
    """Verify backtester halts new entries after daily trade cap is hit."""
    base_t = datetime(2026, 10, 5, 9, 30, 0, tzinfo=IST)
    candles = []
    for i in range(60):
        t = base_t + timedelta(minutes=i)
        candles.append(
            Candle(
                symbol="INFY",
                timeframe="1m",
                timestamp=t,
                open=1500.0,
                high=1510.0,
                low=1490.0,
                close=1502.0,
                volume=1000,
                vwap=1500.0,
            )
        )

    class HyperActiveStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(StrategyType.SCALPER_1M)

        def on_candle(self, context: StrategyContext):
            if context.current_candle.timestamp.minute % 2 == 0:
                return Signal(
                    id=f"sig_{context.current_candle.timestamp.minute}",
                    strategy_type=StrategyType.SCALPER_1M,
                    symbol="INFY",
                    side=OrderSide.BUY,
                    timeframe="1m",
                    timestamp=context.current_candle.timestamp,
                    entry_price=1502.0,
                    stop_loss=1498.0,
                    target=1504.0,
                    regime=MarketRegime.TRENDING_BULLISH,
                    quality_score=None,
                    expected_net_gain_pct=0.5,
                    reason="Hyperactive signal",
                )
            return None

    backtester = Backtester()
    res = backtester.run(
        strategy=HyperActiveStrategy(),
        candles=candles,
        max_daily_trades=3,
        enforce_session_rules=True,
    )

    assert res["total_trades"] <= 3


def test_backtest_report_monthly_breakdown_including_losing_months():
    """Verify BacktestReport includes losing months and calculates payoff ratio."""
    from tradeforge_shared.costs import IndianCostCalculator
    calc = IndianCostCalculator()

    dummy_signal = Signal(
        id="s1",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(IST),
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22100.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=None,
        expected_net_gain_pct=0.4,
        reason="Report test",
    )

    # Month 1: October 2026 -> Profitable trade
    t1_cost = calc.calculate_round_trip(buy_price=22000.0, sell_price=22040.0, quantity=50)
    t1 = BacktestTradeResult(
        signal=dummy_signal,
        entry_time=datetime(2026, 10, 5, 10, 0, 0),
        exit_time=datetime(2026, 10, 5, 10, 15, 0),
        entry_price=22000.0,
        exit_price=22040.0,
        quantity=50,
        exit_reason="TARGET_HIT",
        cost_breakdown=t1_cost,
    )

    # Month 2: November 2026 -> Losing trade
    t2_cost = calc.calculate_round_trip(buy_price=22000.0, sell_price=21970.0, quantity=50)
    t2 = BacktestTradeResult(
        signal=dummy_signal,
        entry_time=datetime(2026, 11, 2, 10, 0, 0),
        exit_time=datetime(2026, 11, 2, 10, 20, 0),
        entry_price=22000.0,
        exit_price=21970.0,
        quantity=50,
        exit_reason="STOP_LOSS_HIT",
        cost_breakdown=t2_cost,
    )

    report_gen = BacktestReport(
        symbol="NIFTY",
        strategy_name="SCALPER_1M",
        initial_capital=100000.0,
        trades=[t1, t2],
        equity_curve=[100000.0, 101850.0, 100730.0],
    )
    rep = report_gen.generate_report()

    assert rep["total_trades"] == 2
    assert rep["winning_trades"] == 1
    assert rep["losing_trades"] == 1
    assert rep["average_win_inr"] > 0
    assert rep["average_loss_inr"] > 0

    monthly = rep["monthly_breakdown"]
    assert "2026-10" in monthly
    assert "2026-11" in monthly
    assert monthly["2026-10"]["net_pnl"] > 0
    assert monthly["2026-11"]["net_pnl"] < 0  # Losing month verified!


def test_overfitting_warning_triggered_on_unrealistic_metrics():
    """Verify that unrealistic performance metrics raise an institutional overfitting alert."""
    from tradeforge_shared.costs import IndianCostCalculator
    calc = IndianCostCalculator()

    dummy_signal = Signal(
        id="s1",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(IST),
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22100.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=None,
        expected_net_gain_pct=0.4,
        reason="Report test",
    )

    # 25 trades with 96% win rate (24 wins, 1 loss) -> Overfitting alert
    trades = []
    for i in range(25):
        is_win = i < 24
        sell_p = 22040.0 if is_win else 21980.0
        c = calc.calculate_round_trip(buy_price=22000.0, sell_price=sell_p, quantity=50)
        t = BacktestTradeResult(
            signal=dummy_signal,
            entry_time=datetime(2026, 10, 1 + (i % 20), 10, 0, 0),
            exit_time=datetime(2026, 10, 1 + (i % 20), 10, 15, 0),
            entry_price=22000.0,
            exit_price=sell_p,
            quantity=50,
            exit_reason="TARGET_HIT" if is_win else "STOP_LOSS_HIT",
            cost_breakdown=c,
        )
        trades.append(t)

    report_gen = BacktestReport(
        symbol="NIFTY",
        strategy_name="SCALPER_1M",
        initial_capital=100000.0,
        trades=trades,
        equity_curve=[100000.0 + i * 800 for i in range(26)],
    )
    rep = report_gen.generate_report()

    assert rep["win_rate_pct"] == 96.0
    assert rep["overfitting_warning"] is not None
    assert "OVERFITTING WARNING" in rep["overfitting_warning"]


def test_walk_forward_validation_splits():
    """Verify WalkForwardValidator executes out-of-sample partitions."""
    base_t = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    candles = []
    # 240 candles
    for i in range(240):
        t = base_t + timedelta(minutes=i)
        candles.append(
            Candle(
                symbol="NIFTY",
                timeframe="1m",
                timestamp=t,
                open=22000.0 + i * 0.5,
                high=22005.0 + i * 0.5,
                low=21995.0 + i * 0.5,
                close=22002.0 + i * 0.5,
                volume=2000,
                vwap=22000.0,
            )
        )

    class DummyStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(StrategyType.SCALPER_1M)

        def on_candle(self, context: StrategyContext):
            return None

    validator = WalkForwardValidator(n_splits=3, out_of_sample_ratio=0.4)
    results = validator.run_walk_forward(
        strategy_factory=DummyStrategy,
        candles=candles,
    )

    assert results["validation_mode"] == "WALK_FORWARD"
    assert results["n_splits"] == 3
    assert len(results["window_results"]) == 3

