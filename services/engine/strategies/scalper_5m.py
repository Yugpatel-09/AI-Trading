"""
TradeForge 5-Minute Scalper Strategy.
Rule 5: The same strategy code runs identically in backtest, paper, and live.

Specification:
- Speed: Medium, 5 to 40 min hold.
- Regime Filter: Requires TRENDING_BULLISH (for longs) or TRENDING_BEARISH (for shorts).
- Trigger: EMA 9 crosses EMA 21 with above-average volume.
- Real 15m trend filter: 15m EMA9/21 and VWAP trend agreement.
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


class Scalper5M(BaseStrategy):
    """
    5-Minute Scalper Strategy.
    """

    def __init__(
        self,
        target_pct: float = 0.0045,
        stop_atr_mult: float = 1.0,
        cost_calculator: Optional[IndianCostCalculator] = None,
        regime_detector: Optional[RegimeDetector] = None,
        quality_model: Optional[QualityModel] = None,
    ):
        super().__init__(StrategyType.SCALPER_5M)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult
        self.cost_calc = cost_calculator or IndianCostCalculator(default_slippage_bps=5.0)
        self.regime_detector = regime_detector or RegimeDetector()
        self.quality_model = quality_model or NoModelPassThrough()

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_5m
        if len(history) < 22:
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

        # 3. 15m Higher-Timeframe Trend Agreement
        hist_15m = context.candle_history_15m
        trend_15m_bullish = True
        trend_15m_bearish = True
        if len(hist_15m) >= 3:
            df_15m = FeatureStore.compute_features_df(hist_15m)
            rec_15m = df_15m.iloc[-1]
            c15 = rec_15m["close"]
            v15 = rec_15m.get("vwap", c15)
            ema9_15 = rec_15m.get("ema_9", c15)
            ema21_15 = rec_15m.get("ema_21", c15)
            trend_15m_bullish = (c15 >= v15) and (ema9_15 >= ema21_15)
            trend_15m_bearish = (c15 <= v15) and (ema9_15 <= ema21_15)

        # 4. Feature Extraction on 5m
        df = FeatureStore.compute_features_df(history)
        recent = df.iloc[-1]
        prev = df.iloc[-2]

        close = candle.close
        ema_9_now = float(recent["ema_9"])
        ema_21_now = float(recent["ema_21"])
        ema_9_prev = float(prev["ema_9"])
        ema_21_prev = float(prev["ema_21"])
        vwap = float(recent.get("vwap", close))
        atr = float(recent.get("atr", close * 0.005))
        vol_ratio = float(recent.get("vol_ratio", 1.0))

        stop_distance = max(2.0, atr * self.stop_atr_mult)

        # 5. Bullish Cross Setup
        bullish_cross = ema_9_prev <= ema_21_prev and ema_9_now > ema_21_now
        is_long = (
            regime == MarketRegime.TRENDING_BULLISH
            and trend_15m_bullish
            and bullish_cross
            and close > vwap
            and vol_ratio >= 1.1
        )

        # 6. Symmetric Bearish Cross Setup
        bearish_cross = ema_9_prev >= ema_21_prev and ema_9_now < ema_21_now
        is_short = (
            regime == MarketRegime.TRENDING_BEARISH
            and trend_15m_bearish
            and bearish_cross
            and close < vwap
            and vol_ratio >= 1.1
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
        cross_word = "above" if is_long else "below"
        vwap_word = "above" if is_long else "below"

        return Signal(
            id=f"sig_5m_{uuid.uuid4().hex[:8]}",
            strategy_type=StrategyType.SCALPER_5M,
            symbol=context.symbol,
            side=side,
            timeframe="5m",
            timestamp=candle.timestamp,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            time_stop_minutes=40,
            regime=regime,
            quality_score=quality_score,
            expected_net_gain_pct=expected_net_gain_pct,
            reason=(
                f"5m {action_word} EMA cross confirmed on {context.symbol} {vwap_word} VWAP in {regime.value}. "
                f"EMA 9 ({ema_9_now:.2f}) crossed {cross_word} EMA 21 ({ema_21_now:.2f}) with {vol_ratio:.1f}x volume. "
                f"Stop bracket: ₹{stop:.2f} ({self.stop_atr_mult}x ATR). Net gain after costs: +{expected_net_gain_pct:.3f}%."
            ),
        )
