"""
TradeForge Institutional Market Regime Classifier.
Classifies market regime into:
- TRENDING_BULLISH
- TRENDING_BEARISH
- RANGE_BOUND
- VOLATILE_CHAOTIC

Evaluates:
1. ADX (14) with +DI and -DI for trend strength.
2. Wilder ATR for volatility thresholds and runaway risk.
3. Overnight Gap size.
4. Benchmark Index Direction Agreement (e.g. NIFTY 50 trend).
"""

from typing import List, Optional

import pandas as pd
from tradeforge_shared.enums import MarketRegime
from tradeforge_shared.schemas import Candle

from services.engine.features.store import FeatureStore


class RegimeDetector:
    """
    Market Regime Detector.
    Strategies query this before evaluating setups:
    - Trend scalpers only trade in matching trending regimes.
    - Volatile / chaotic markets halt aggressive trading.
    """

    def __init__(
        self,
        min_trend_adx: float = 20.0,
        max_atr_pct: float = 2.5,
        max_gap_pct: float = 3.0,
    ):
        self.min_trend_adx = min_trend_adx
        self.max_atr_pct = max_atr_pct
        self.max_gap_pct = max_gap_pct

    def determine_index_direction(self, index_candles: List[Candle]) -> int:
        """
        Derive benchmark index direction: +1 (bullish), -1 (bearish), 0 (neutral).
        """
        if len(index_candles) < 10:
            return 0

        df = FeatureStore.compute_features_df(index_candles)
        recent = df.iloc[-1]
        close = recent["close"]
        vwap = recent.get("vwap", close)
        ema_9 = recent.get("ema_9", close)
        ema_21 = recent.get("ema_21", close)

        if close > vwap and ema_9 >= ema_21:
            return 1
        elif close < vwap and ema_9 <= ema_21:
            return -1
        return 0

    def classify_regime(
        self,
        candles: List[Candle],
        index_direction: Optional[int] = None,
        index_candles: Optional[List[Candle]] = None,
    ) -> MarketRegime:
        """
        Classify current market regime using ADX, ATR, Gap size, and Index agreement.
        """
        if len(candles) < 15:
            return MarketRegime.RANGE_BOUND

        # Derive index direction if not supplied but index candles exist
        if index_direction is None and index_candles:
            index_direction = self.determine_index_direction(index_candles)

        df = FeatureStore.compute_features_df(candles)
        recent = df.iloc[-1]

        close = float(recent["close"])
        atr = float(recent.get("atr", close * 0.01))
        atr_pct = (atr / close) * 100.0 if close > 0 else 0.0
        gap_pct = abs(float(recent.get("gap_pct", 0.0)))

        # 1. Volatile / Chaotic check: extreme volatility spike or extreme breakaway gap
        if atr_pct > self.max_atr_pct or gap_pct > self.max_gap_pct:
            return MarketRegime.VOLATILE_CHAOTIC

        adx = float(recent.get("adx", 15.0))
        plus_di = float(recent.get("plus_di", 20.0))
        minus_di = float(recent.get("minus_di", 20.0))
        ema_9 = float(recent.get("ema_9", close))
        ema_21 = float(recent.get("ema_21", close))
        vwap = float(recent.get("vwap", close))
        supertrend_dir = int(recent.get("supertrend_direction", 1))

        # Check directional conviction via ADX
        is_trending_strength = not pd.isna(adx) and adx >= self.min_trend_adx

        # 2. Bullish Trend
        bullish_conditions = (
            is_trending_strength
            and plus_di > minus_di
            and close > vwap
            and ema_9 >= ema_21
            and supertrend_dir == 1
        )
        if bullish_conditions:
            # Index direction filter: cannot be fighting a falling index (-1)
            if index_direction is not None and index_direction < 0:
                return MarketRegime.RANGE_BOUND
            return MarketRegime.TRENDING_BULLISH

        # 3. Bearish Trend
        bearish_conditions = (
            is_trending_strength
            and minus_di > plus_di
            and close < vwap
            and ema_9 <= ema_21
            and supertrend_dir == -1
        )
        if bearish_conditions:
            # Index direction filter: cannot be fighting a rising index (+1)
            if index_direction is not None and index_direction > 0:
                return MarketRegime.RANGE_BOUND
            return MarketRegime.TRENDING_BEARISH

        # 4. Otherwise Range-Bound / Consolidation
        return MarketRegime.RANGE_BOUND
