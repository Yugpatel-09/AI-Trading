"""
TradeForge 1-Minute Scalper Strategy.
Rule 5: The same strategy code runs identically in backtest, paper, and live.

Specification:
- Speed: 1 to 10 min hold.
- Regime Filter: Requires TRENDING_BULLISH (for longs) or TRENDING_BEARISH (for shorts).
- Trigger: VWAP pullback in the direction of the 5m trend with volume burst.
- Real 5m trend filter: 5m EMA9/21 and VWAP agreement.
- Symmetric Short signals.
- Quality Model: NO_MODEL by default (never fake scores).
- Mandatory Cost Check: Rejects any signal where expected net gain after Indian statutory
  costs and slippage is not positive.
"""

import uuid
from typing import Optional

from tradeforge_shared.costs import IndianCostCalculator
from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType
from tradeforge_shared.schemas import Signal

from services.engine.data_feed.resampler import to_ist
from services.engine.features.store import FeatureStore
from services.engine.models.quality_model import NoModelPassThrough, QualityModel
from services.engine.regime.classifier import RegimeDetector
from services.engine.strategies.base import BaseStrategy, StrategyContext


class Scalper1M(BaseStrategy):
    """
    1-Minute Scalper Strategy.
    """

    def __init__(
        self,
        target_pct: float = 0.0025,
        stop_atr_mult: float = 0.8,
        cost_calculator: Optional[IndianCostCalculator] = None,
        regime_detector: Optional[RegimeDetector] = None,
        quality_model: Optional[QualityModel] = None,
    ):
        super().__init__(StrategyType.SCALPER_1M)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult
        self.cost_calc = cost_calculator or IndianCostCalculator(default_slippage_bps=5.0)
        self.regime_detector = regime_detector or RegimeDetector()
        self.quality_model = quality_model or NoModelPassThrough()

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_1m
        if len(history) < 15:
            return None

        # 1. Trading Session Hours Check: 09:20 IST to 15:00 IST
        candle_ist = to_ist(candle.timestamp)
        c_time = candle_ist.time()
        if (c_time.hour == 9 and c_time.minute < 20) or c_time.hour >= 15:
            return None

        # 2. Ask RegimeDetector first
        regime = self.regime_detector.classify_regime(
            history,
            index_direction=context.index_direction,
            index_candles=context.index_candles,
        )
        if regime not in (MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH):
            return None

        # 3. 5m Trend Filter
        hist_5m = context.candle_history_5m
        trend_5m_bullish = True
        trend_5m_bearish = True
        if len(hist_5m) >= 5:
            df_5m = FeatureStore.compute_features_df(hist_5m)
            rec_5m = df_5m.iloc[-1]
            c5 = rec_5m["close"]
            v5 = rec_5m.get("vwap", c5)
            ema9_5 = rec_5m.get("ema_9", c5)
            ema21_5 = rec_5m.get("ema_21", c5)
            trend_5m_bullish = (c5 >= v5) and (ema9_5 >= ema21_5)
            trend_5m_bearish = (c5 <= v5) and (ema9_5 <= ema21_5)

        # 4. Feature Extraction on 1m
        df = FeatureStore.compute_features_df(history)
        recent = df.iloc[-1]
        prev = df.iloc[-2]

        close = candle.close
        vwap = float(recent.get("vwap", close))
        atr = float(recent.get("atr", close * 0.003))
        vol_ratio = float(recent.get("vol_ratio", 1.0))

        stop_distance = max(1.0, atr * self.stop_atr_mult)

        # 5. Long Setup: Bullish VWAP Pullback
        # Tested VWAP from above and closed back above VWAP with volume
        is_long = (
            regime == MarketRegime.TRENDING_BULLISH
            and trend_5m_bullish
            and prev["low"] <= vwap
            and close > vwap
            and vol_ratio >= 1.2
        )

        # 6. Symmetric Short Setup: Bearish VWAP Pullback
        # Tested VWAP from below and closed back below VWAP with volume
        is_short = (
            regime == MarketRegime.TRENDING_BEARISH
            and trend_5m_bearish
            and prev["high"] >= vwap
            and close < vwap
            and vol_ratio >= 1.2
        )

        if not is_long and not is_short:
            return None

        side = OrderSide.BUY if is_long else OrderSide.SELL
        entry = close
        if side == OrderSide.BUY:
            stop = round(entry - stop_distance, 2)
            target = round(entry * (1 + self.target_pct), 2)
            costs = self.cost_calc.calculate_round_trip(
                buy_price=entry,
                sell_price=target,
                quantity=100,
            )
        else:
            stop = round(entry + stop_distance, 2)
            target = round(entry * (1 - self.target_pct), 2)
            costs = self.cost_calc.calculate_round_trip(
                buy_price=target,
                sell_price=entry,
                quantity=100,
            )

        # 7. Mandatory Cost Check: Net gain after Indian statutory taxes & slippage must be positive
        if costs.net_pnl <= 0:
            return None

        expected_net_gain_pct = round((costs.net_pnl / (entry * 100)) * 100.0, 4)

        # 8. Score via QualityModel (None if NO_MODEL)
        quality_score = self.quality_model.score_signal(recent.to_dict())

        action_word = "Long" if is_long else "Short"
        tested_side = "above" if is_long else "below"
        return Signal(
            id=f"sig_1m_{uuid.uuid4().hex[:8]}",
            strategy_type=StrategyType.SCALPER_1M,
            symbol=context.symbol,
            side=side,
            timeframe="1m",
            timestamp=candle.timestamp,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            time_stop_minutes=15,
            regime=regime,
            quality_score=quality_score,
            expected_net_gain_pct=expected_net_gain_pct,
            reason=(
                f"1m {action_word} VWAP pullback confirmed on {context.symbol} in {regime.value}. "
                f"Price tested VWAP (₹{vwap:.2f}) from {tested_side} and closed with {vol_ratio:.1f}x volume. "
                f"Stop bracket: ₹{stop:.2f} ({self.stop_atr_mult}x ATR). Net gain after costs: +{expected_net_gain_pct:.3f}%."
            ),
        )
