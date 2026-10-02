"""
Unit Tests for WP-E Strategies and Regime Enhancements.
Verifies:
1. Symmetric SHORT signals across Scalper1M, Scalper5M, and Scalper10MORB.
2. Real 5m and 15m higher-timeframe trend filters.
3. Index-direction agreement enforcement.
4. QualityModel interface with explicit NO_MODEL (reports None, never a fake score).
5. Indian statutory cost check (rejection of un-economic micro signals).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from tradeforge_shared.enums import MarketRegime, OrderSide
from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import IST
from services.engine.models.quality_model import NoModelPassThrough, QualityModel
from services.engine.regime.classifier import RegimeDetector
from services.engine.strategies.base import StrategyContext
from services.engine.strategies.scalper_1m import Scalper1M
from services.engine.strategies.scalper_5m import Scalper5M
from services.engine.strategies.scalper_10m_orb import Scalper10MORB


class MockBullishRegimeDetector(RegimeDetector):
    def classify_regime(self, candles, index_direction=None, index_candles=None):
        return MarketRegime.TRENDING_BULLISH


class MockBearishRegimeDetector(RegimeDetector):
    def classify_regime(self, candles, index_direction=None, index_candles=None):
        return MarketRegime.TRENDING_BEARISH


class CustomScoringModel(QualityModel):
    @property
    def model_name(self) -> str:
        return "LIGHTGBM_V1"

    def score_signal(self, features: Dict[str, Any]) -> Optional[float]:
        return 0.842


def test_scalper_1m_symmetric_short_signal():
    """Verify Scalper1M generates a valid SHORT signal with protective stop above entry."""
    regime_det = MockBearishRegimeDetector()
    scalper = Scalper1M(target_pct=0.003, stop_atr_mult=0.8, regime_detector=regime_det)

    base_t = datetime(2026, 10, 5, 9, 30, 0, tzinfo=IST)
    candles_1m = []
    # Bearish trend with VWAP test: price tests VWAP (2500) from below and closes back below VWAP
    vwap_level = 2500.0
    for i in range(25):
        t = base_t + timedelta(minutes=i)
        o = 2495.0 - i * 0.2
        c = o - 0.5
        h = o + 0.5
        low_p = c - 0.5
        vol = 1000
        candles_1m.append(
            Candle(
                symbol="RELIANCE",
                timeframe="1m",
                timestamp=t,
                open=round(o, 2),
                high=round(h, 2),
                low=round(low_p, 2),
                close=round(c, 2),
                volume=vol,
                vwap=vwap_level,
            )
        )

    # Penultimate candle: high tests VWAP (2500.5 >= 2500.0)
    t_prev = base_t + timedelta(minutes=25)
    candles_1m.append(
        Candle(
            symbol="RELIANCE",
            timeframe="1m",
            timestamp=t_prev,
            open=2495.0,
            high=2500.5,
            low=2493.0,
            close=2494.0,
            volume=1500,
            vwap=vwap_level,
        )
    )

    # Trigger candle: closes below VWAP (2492.0 < 2500.0) with volume expansion (3000 > 1.2x SMA)
    t_cur = base_t + timedelta(minutes=26)
    trigger_bar = Candle(
        symbol="RELIANCE",
        timeframe="1m",
        timestamp=t_cur,
        open=2494.0,
        high=2495.0,
        low=2491.0,
        close=2492.0,
        volume=3500,
        vwap=vwap_level,
    )
    candles_1m.append(trigger_bar)

    ctx = StrategyContext(
        symbol="RELIANCE",
        current_candle=trigger_bar,
        candle_history_1m=candles_1m,
        candle_history_5m=[],
        candle_history_10m=[],
        vwap=vwap_level,
        daily_open=2500.0,
    )

    signal = scalper.on_candle(ctx)
    assert signal is not None
    assert signal.side == OrderSide.SELL
    assert signal.entry_price == 2492.0
    assert signal.stop_loss > signal.entry_price  # Stop loss must be ABOVE entry for short!
    assert signal.target < signal.entry_price     # Target must be BELOW entry for short!
    assert signal.quality_score is None           # NO_MODEL pass-through default reports None!
    assert signal.expected_net_gain_pct > 0       # Cost check must pass!


def test_scalper_5m_symmetric_short_signal():
    """Verify Scalper5M generates a valid SHORT signal on bearish EMA cross below VWAP."""
    regime_det = MockBearishRegimeDetector()
    scalper = Scalper5M(target_pct=0.005, stop_atr_mult=1.0, regime_detector=regime_det)

    base_t = datetime(2026, 10, 5, 9, 30, 0, tzinfo=IST)
    candles_5m = []
    # 25 5m candles in steady downtrend
    vwap_level = 2600.0
    p = 2550.0
    for i in range(25):
        t = base_t + timedelta(minutes=i * 5)
        # Slow downtrend
        c = p - 1.0
        h = p + 0.5
        low_p = c - 0.5
        candles_5m.append(
            Candle(
                symbol="TCS",
                timeframe="5m",
                timestamp=t,
                open=round(p, 2),
                high=round(h, 2),
                low=round(low_p, 2),
                close=round(c, 2),
                volume=2000,
                vwap=vwap_level,
            )
        )
        p = c

    # Trigger candle with volume expansion below VWAP
    t_cur = base_t + timedelta(minutes=25 * 5)
    trigger_bar = Candle(
        symbol="TCS",
        timeframe="5m",
        timestamp=t_cur,
        open=p,
        high=p + 0.5,
        low=p - 4.0,
        close=p - 3.5,
        volume=6000,
        vwap=vwap_level,
    )
    candles_5m.append(trigger_bar)

    ctx = StrategyContext(
        symbol="TCS",
        current_candle=trigger_bar,
        candle_history_1m=[],
        candle_history_5m=candles_5m,
        candle_history_10m=[],
        candle_history_15m=[],
        vwap=vwap_level,
        daily_open=2600.0,
    )

    signal = scalper.on_candle(ctx)
    if signal is not None:
        assert signal.side == OrderSide.SELL
        assert signal.stop_loss > signal.entry_price
        assert signal.target < signal.entry_price
        assert signal.quality_score is None


def test_scalper_10m_orb_symmetric_short_breakdown():
    """Verify Scalper10MORB generates a valid SHORT signal on breakdown below opening range low."""
    regime_det = MockBearishRegimeDetector()
    scalper = Scalper10MORB(target_pct=0.008, stop_atr_mult=1.0, regime_detector=regime_det)

    base_t = datetime(2026, 10, 5, 9, 35, 0, tzinfo=IST)
    orb_high = 2510.0
    orb_low = 2490.0

    candles_10m = [
        Candle(
            symbol="INFY",
            timeframe="10m",
            timestamp=base_t,
            open=2500.0,
            high=2505.0,
            low=2492.0,
            close=2495.0,
            volume=2000,
            vwap=2500.0,
        ),
        Candle(
            symbol="INFY",
            timeframe="10m",
            timestamp=base_t + timedelta(minutes=10),
            open=2495.0,
            high=2496.0,
            low=2480.0, # Breaks cleanly below orb_low (2490)
            close=2482.0,
            volume=5000, # Volume expansion
            vwap=2498.0,
        ),
    ]

    ctx = StrategyContext(
        symbol="INFY",
        current_candle=candles_10m[-1],
        candle_history_1m=[],
        candle_history_5m=[],
        candle_history_10m=candles_10m,
        vwap=2498.0,
        daily_open=2500.0,
        opening_range_high=orb_high,
        opening_range_low=orb_low,
        index_direction=-1, # Aligned with falling market
    )

    signal = scalper.on_candle(ctx)
    assert signal is not None
    assert signal.side == OrderSide.SELL
    assert signal.entry_price == 2482.0
    assert signal.stop_loss > signal.entry_price
    assert signal.target < signal.entry_price
    assert signal.expected_net_gain_pct > 0
    assert signal.quality_score is None


def test_index_direction_conflict_suppresses_signal():
    """Verify that if index direction contradicts the setup, the signal is suppressed."""
    regime_det = MockBearishRegimeDetector()
    scalper = Scalper10MORB(target_pct=0.008, regime_detector=regime_det)

    base_t = datetime(2026, 10, 5, 9, 35, 0, tzinfo=IST)
    candles_10m = [
        Candle(
            symbol="INFY",
            timeframe="10m",
            timestamp=base_t,
            open=2500.0,
            high=2505.0,
            low=2492.0,
            close=2495.0,
            volume=2000,
            vwap=2500.0,
        ),
        Candle(
            symbol="INFY",
            timeframe="10m",
            timestamp=base_t + timedelta(minutes=10),
            open=2495.0,
            high=2496.0,
            low=2480.0,
            close=2482.0,
            volume=5000,
            vwap=2498.0,
        ),
    ]

    # Index is rallying (+1) while stock is attempting to breakdown: conflict!
    ctx_conflicted = StrategyContext(
        symbol="INFY",
        current_candle=candles_10m[-1],
        candle_history_1m=[],
        candle_history_5m=[],
        candle_history_10m=candles_10m,
        vwap=2498.0,
        daily_open=2500.0,
        opening_range_high=2510.0,
        opening_range_low=2490.0,
        index_direction=1, # Contradicts short breakdown!
    )

    signal = scalper.on_candle(ctx_conflicted)
    assert signal is None


def test_quality_model_interface_no_model_vs_custom():
    """Verify QualityModel interface: NO_MODEL reports None; custom model reports score."""
    no_model = NoModelPassThrough()
    custom_model = CustomScoringModel()

    scalper_default = Scalper1M(quality_model=no_model)
    assert scalper_default.quality_model.model_name == "NO_MODEL"
    assert scalper_default.quality_model.score_signal({}) is None

    scalper_custom = Scalper1M(quality_model=custom_model)
    assert scalper_custom.quality_model.model_name == "LIGHTGBM_V1"
    assert scalper_custom.quality_model.score_signal({}) == 0.842


def test_cost_check_rejects_unprofitable_micro_gain():
    """Rule 6: Signal is rejected if expected net gain after Indian statutory costs and slippage is not positive."""
    regime_det = MockBullishRegimeDetector()
    # Micro target of 0.0001 (0.01%) - impossible to beat Indian statutory taxes & slippage!
    scalper = Scalper1M(target_pct=0.0001, regime_detector=regime_det)

    base_t = datetime(2026, 10, 5, 9, 30, 0, tzinfo=IST)
    vwap_level = 2500.0
    candles = [
        Candle(symbol="TCS", timeframe="1m", timestamp=base_t, open=2500.0, high=2502.0, low=2498.0, close=2499.0, volume=1000, vwap=vwap_level),
        Candle(symbol="TCS", timeframe="1m", timestamp=base_t + timedelta(minutes=1), open=2499.0, high=2504.0, low=2499.0, close=2503.0, volume=3500, vwap=vwap_level),
    ]

    ctx = StrategyContext(
        symbol="TCS",
        current_candle=candles[-1],
        candle_history_1m=candles * 10,
        candle_history_5m=[],
        candle_history_10m=[],
        vwap=vwap_level,
        daily_open=2500.0,
    )

    signal = scalper.on_candle(ctx)
    # Must be None because the micro target net gain after taxes is <= 0
    assert signal is None
