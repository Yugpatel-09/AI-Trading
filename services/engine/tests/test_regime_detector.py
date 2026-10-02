"""
Unit Tests for RegimeDetector.
Verifies:
1. Classification of all 4 market regimes:
   - TRENDING_BULLISH
   - TRENDING_BEARISH
   - RANGE_BOUND
   - VOLATILE_CHAOTIC
2. Index-direction agreement: stock trending against market index is downgraded to RANGE_BOUND.
3. Strategies return None in regimes they may not trade.
"""

from datetime import datetime, timedelta

from tradeforge_shared.enums import MarketRegime
from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import IST
from services.engine.regime.classifier import RegimeDetector
from services.engine.strategies.base import StrategyContext
from services.engine.strategies.scalper_1m import Scalper1M
from services.engine.strategies.scalper_5m import Scalper5M


def make_candle_series(
    start_price: float,
    trend_delta: float,
    count: int = 40,
    volatility: float = 1.0,
    start_hour: int = 9,
    start_minute: int = 15,
) -> list[Candle]:
    base_t = datetime(2026, 10, 5, start_hour, start_minute, 0, tzinfo=IST)
    candles = []
    p = start_price
    for i in range(count):
        t = base_t + timedelta(minutes=i)
        o = p
        c = p + trend_delta
        h = max(o, c) + volatility
        low_p = min(o, c) - volatility
        vol = 2000
        candles.append(
            Candle(
                symbol="RELIANCE",
                timeframe="1m",
                timestamp=t,
                open=round(o, 2),
                high=round(h, 2),
                low=round(low_p, 2),
                close=round(c, 2),
                volume=vol,
                vwap=round((h + low_p + c) / 3.0, 2),
            )
        )
        p = c
    return candles


def test_regime_detector_trending_bullish():
    detector = RegimeDetector()
    bull_candles = make_candle_series(2000.0, trend_delta=1.5, count=40, volatility=0.5)
    regime = detector.classify_regime(bull_candles)
    assert regime == MarketRegime.TRENDING_BULLISH


def test_regime_detector_trending_bearish():
    detector = RegimeDetector()
    bear_candles = make_candle_series(2000.0, trend_delta=-1.5, count=40, volatility=0.5)
    regime = detector.classify_regime(bear_candles)
    assert regime == MarketRegime.TRENDING_BEARISH


def test_regime_detector_range_bound():
    detector = RegimeDetector()
    # Flat chop (no directional move)
    flat_candles = []
    base_t = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    for i in range(40):
        t = base_t + timedelta(minutes=i)
        flat_candles.append(
            Candle(
                symbol="RELIANCE",
                timeframe="1m",
                timestamp=t,
                open=2000.0 if i % 2 == 0 else 2001.0,
                high=2002.0,
                low=1999.0,
                close=2001.0 if i % 2 == 0 else 2000.0,
                volume=1000,
                vwap=2000.5,
            )
        )
    regime = detector.classify_regime(flat_candles)
    assert regime == MarketRegime.RANGE_BOUND


def test_regime_detector_volatile_chaotic():
    detector = RegimeDetector()
    # High ATR spike (volatility=100 on 2000 price -> ATR% > 5%)
    chaotic_candles = make_candle_series(2000.0, trend_delta=0.0, count=40, volatility=80.0)
    regime = detector.classify_regime(chaotic_candles)
    assert regime == MarketRegime.VOLATILE_CHAOTIC


def test_regime_detector_index_conflict_downgrades_to_range_bound():
    detector = RegimeDetector()
    # Stock is moving up, but broader market index is crashing (-1)
    bull_candles = make_candle_series(2000.0, trend_delta=1.5, count=40, volatility=0.5)

    # When aligned with bullish market (+1 or None)
    assert detector.classify_regime(bull_candles, index_direction=1) == MarketRegime.TRENDING_BULLISH

    # When fighting a falling index (-1): must downgrade to RANGE_BOUND
    assert detector.classify_regime(bull_candles, index_direction=-1) == MarketRegime.RANGE_BOUND


def test_strategies_return_none_in_disallowed_regimes():
    """Rule: Every strategy must return None in regimes it may not trade."""
    scalper_1m = Scalper1M()
    scalper_5m = Scalper5M()

    # Create chaotic candle series
    chaotic_candles = make_candle_series(2000.0, trend_delta=0.0, count=40, volatility=80.0)
    current_bar = chaotic_candles[-1]

    ctx = StrategyContext(
        symbol="RELIANCE",
        current_candle=current_bar,
        candle_history_1m=chaotic_candles,
        candle_history_5m=chaotic_candles,
        candle_history_10m=chaotic_candles,
        candle_history_15m=chaotic_candles,
        vwap=current_bar.vwap or current_bar.close,
        daily_open=chaotic_candles[0].open,
    )

    # In chaotic market, scalpers must return None
    assert scalper_1m.on_candle(ctx) is None
    assert scalper_5m.on_candle(ctx) is None
