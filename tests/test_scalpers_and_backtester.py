from tradeforge_shared.schemas import Candle

from scripts.seed_data import generate_candles
from services.backtester.engine import Backtester
from services.engine.strategies.scalper_1m import Scalper1M
from services.engine.strategies.scalper_5m import Scalper5M


def test_backtester_runs_scalper_with_indian_costs():
    candles = generate_candles("RELIANCE", base_price=2500.0, count=100, timeframe="1m")
    scalper = Scalper1M(target_pct=0.003, stop_atr_mult=0.8)
    backtester = Backtester()

    results = backtester.run(
        strategy=scalper,
        candles=candles,
        initial_capital=100000.0,
        risk_per_trade_inr=1000.0,
    )

    assert "total_trades" in results
    assert "win_rate_pct" in results
    assert "total_statutory_taxes_inr" in results
    assert "net_profit_after_costs_inr" in results
    assert results["strategy"] == "SCALPER_1M"

def test_backtester_5m_scalper():
    candles = generate_candles("NIFTY", base_price=22000.0, count=80, timeframe="5m")
    scalper = Scalper5M()
    backtester = Backtester()

    results = backtester.run(
        strategy=scalper,
        candles=candles,
        initial_capital=200000.0,
        risk_per_trade_inr=1500.0,
    )

    assert results["symbol"] == "NIFTY"
    assert results["strategy"] == "SCALPER_5M"


def test_backtester_delivers_distinct_multi_timeframe_series_no_lookahead():
    """
    WP-D Verification Test:
    Proves each strategy receives the correct timeframe series (real 1m, 5m, 10m, 15m),
    not the same list three times, and with zero lookahead bias.
    """
    from datetime import datetime, timedelta

    from tradeforge_shared.enums import StrategyType

    from services.engine.data_feed.resampler import IST
    from services.engine.strategies.base import BaseStrategy, StrategyContext

    captured_contexts: list[StrategyContext] = []

    class InspectorStrategy(BaseStrategy):
        def __init__(self):
            super().__init__(StrategyType.SCALPER_1M)

        def on_candle(self, context: StrategyContext):
            captured_contexts.append(context)
            return None

    # Generate 90 1m candles for regular session starting 09:15 IST
    base_time = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    candles_1m = []
    for i in range(90):
        t = base_time + timedelta(minutes=i)
        candles_1m.append(
            Candle(
                symbol="INFY",
                timeframe="1m",
                timestamp=t,
                open=1500.0 + i * 0.1,
                high=1501.0 + i * 0.1,
                low=1499.0 + i * 0.1,
                close=1500.5 + i * 0.1,
                volume=1000,
                vwap=1500.0,
            )
        )

    inspector = InspectorStrategy()
    backtester = Backtester()
    backtester.run(strategy=inspector, candles=candles_1m)

    assert len(captured_contexts) > 0

    # Inspect context around minute 60 (10:15 IST)
    # i=60 corresponds to candle at 10:15
    ctx_60 = captured_contexts[40]  # Loop started at start_idx=20, so idx 40 corresponds to i=60
    current_t = ctx_60.current_candle.timestamp

    # 1. Series must NOT be identical in length or reference
    assert len(ctx_60.candle_history_1m) > len(ctx_60.candle_history_5m)
    assert len(ctx_60.candle_history_5m) > len(ctx_60.candle_history_10m)
    assert len(ctx_60.candle_history_10m) >= len(ctx_60.candle_history_15m)

    # 2. Timeframes must match their containers
    if ctx_60.candle_history_5m:
        assert all(c.timeframe == "5m" for c in ctx_60.candle_history_5m)
    if ctx_60.candle_history_10m:
        assert all(c.timeframe == "10m" for c in ctx_60.candle_history_10m)
    if ctx_60.candle_history_15m:
        assert all(c.timeframe == "15m" for c in ctx_60.candle_history_15m)

    # 3. Zero lookahead: Every closed 5m bar must have completed before or at current_t
    for c in ctx_60.candle_history_5m:
        assert c.timestamp + timedelta(minutes=5) <= current_t

    # 4. Opening range was populated from FeatureStore (cutoff at 09:30, so at 10:15 it is set)
    assert ctx_60.opening_range_high is not None
    assert ctx_60.opening_range_low is not None
    assert ctx_60.opening_range_high >= ctx_60.opening_range_low


def test_backtester_runs_10m_orb_with_feature_store_opening_range():
    """Verify Scalper10MORB runs in backtester using FeatureStore's opening range."""
    from datetime import datetime, timedelta

    from services.engine.data_feed.resampler import IST
    from services.engine.strategies.scalper_10m_orb import Scalper10MORB

    # Generate 150 1m candles starting 09:15 IST
    base_time = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    candles = []
    # Opening 20 mins: 1500 - 1505 range
    for i in range(25):
        t = base_time + timedelta(minutes=i)
        candles.append(
            Candle(
                symbol="HDFCBANK",
                timeframe="1m",
                timestamp=t,
                open=1500.0,
                high=1505.0,
                low=1498.0,
                close=1502.0,
                volume=1000,
                vwap=1501.0,
            )
        )
    # Breakout at minute 40 (10:00 IST) above 1505
    for i in range(25, 80):
        t = base_time + timedelta(minutes=i)
        candles.append(
            Candle(
                symbol="HDFCBANK",
                timeframe="1m",
                timestamp=t,
                open=1506.0 + i * 0.1,
                high=1515.0 + i * 0.1,
                low=1504.0,
                close=1510.0 + i * 0.1,
                volume=3000,
                vwap=1508.0,
            )
        )

    scalper = Scalper10MORB(target_pct=0.005, stop_atr_mult=1.0)
    backtester = Backtester()
    results = backtester.run(strategy=scalper, candles=candles)

    assert results["symbol"] == "HDFCBANK"
    assert results["strategy"] == "SCALPER_10M_ORB"
    assert "win_rate_pct" in results

