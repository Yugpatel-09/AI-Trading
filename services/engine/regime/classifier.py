from typing import List

from tradeforge_shared.enums import MarketRegime
from tradeforge_shared.schemas import Candle

from services.engine.features.indicators import TechnicalIndicators


class RegimeDetector:
    """
    Specialist 1: Classifies market regime as Trending, Range-bound, or Chaotic.
    A scalper that loves chop is switched off on trending days, and vice versa.
    """
    def classify_regime(self, candles: List[Candle]) -> MarketRegime:
        if len(candles) < 20:
            return MarketRegime.RANGE_BOUND

        df = TechnicalIndicators.compute_all_features(candles)
        recent = df.iloc[-1]

        atr = recent.get("atr", 10.0)
        close = recent.get("close", 100.0)
        atr_pct = (atr / close) * 100.0 if close > 0 else 0

        # Highly volatile / chaotic day (huge ATR spike)
        if atr_pct > 2.5:
            return MarketRegime.VOLATILE_CHAOTIC

        ema_9 = recent.get("ema_9", close)
        ema_21 = recent.get("ema_21", close)
        vwap = recent.get("vwap", close)

        # Bullish Trend: Close > EMA9 > EMA21 and Close > VWAP
        if close > ema_9 > ema_21 and close > vwap:
            return MarketRegime.TRENDING_BULLISH

        # Bearish Trend: Close < EMA9 < EMA21 and Close < VWAP
        if close < ema_9 < ema_21 and close < vwap:
            return MarketRegime.TRENDING_BEARISH

        # Otherwise range-bound / consolidation
        return MarketRegime.RANGE_BOUND
