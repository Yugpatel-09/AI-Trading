"""
TradeForge 10-Minute Opening Range Breakout (ORB) Scalper Strategy.
Rule 5: The same strategy code runs identically in backtest, paper, and live.

Specification:
- Speed: Slower, 10 to 90 min hold.
- Regime Filter: Requires TRENDING_BULLISH (for long breakouts) or TRENDING_BEARISH (for short breakdowns).
- Trigger: Opening range breakout / breakdown with volume confirmation.
- Index Direction Agreement: Daily bias and index alignment.
- Symmetric Short signals (breakdown below opening range low).
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


class Scalper10MORB(BaseStrategy):
    """
    10-Minute Opening Range Breakout (ORB) Strategy.
    """

    def __init__(
        self,
        target_pct: float = 0.0075,
        stop_atr_mult: float = 1.1,
        cost_calculator: Optional[IndianCostCalculator] = None,
        regime_detector: Optional[RegimeDetector] = None,
        quality_model: Optional[QualityModel] = None,
    ):
        super().__init__(StrategyType.SCALPER_10M_ORB)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult
        self.cost_calc = cost_calculator or IndianCostCalculator(default_slippage_bps=5.0)
        self.regime_detector = regime_detector or RegimeDetector()
        self.quality_model = quality_model or NoModelPassThrough()

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_10m
        if len(history) < 2 or not context.opening_range_high or not context.opening_range_low:
            return None

        # 1. Trading Session Hours Check: ORB entries occur between 09:30 IST and 14:00 IST
        candle_ist = to_ist(candle.timestamp)
        c_time = candle_ist.time()
        if (c_time.hour == 9 and c_time.minute < 30) or c_time.hour >= 14:
            return None

        # 2. Ask RegimeDetector first
        regime = self.regime_detector.classify_regime(
            history,
            index_direction=context.index_direction,
            index_candles=context.index_candles,
        )
        if regime not in (MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH):
            return None

        # 3. Index Direction Agreement Filter
        if context.index_direction is not None:
            if regime == MarketRegime.TRENDING_BULLISH and context.index_direction < 0:
                return None
            if regime == MarketRegime.TRENDING_BEARISH and context.index_direction > 0:
                return None

        df = FeatureStore.compute_features_df(history)
        recent = df.iloc[-1]
        close = candle.close
        high = candle.high
        low = candle.low
        orb_high = context.opening_range_high
        orb_low = context.opening_range_low
        atr = float(recent.get("atr", close * 0.006))
        vwap = float(recent.get("vwap", close))
        vol_ratio = float(recent.get("vol_ratio", 1.0))

        stop_distance = max(3.0, atr * self.stop_atr_mult)

        # 4. Bullish ORB Breakout: Closes cleanly above opening range high
        is_long = (
            regime == MarketRegime.TRENDING_BULLISH
            and close > orb_high
            and high > orb_high * 1.001
            and close > vwap
            and vol_ratio >= 1.25
        )

        # 5. Symmetric Bearish ORB Breakdown: Closes cleanly below opening range low
        is_short = (
            regime == MarketRegime.TRENDING_BEARISH
            and close < orb_low
            and low < orb_low * 0.999
            and close < vwap
            and vol_ratio >= 1.25
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

        # 6. Mandatory Cost Check: Net gain after Indian statutory taxes & slippage must be positive
        if costs.net_pnl <= 0:
            return None

        expected_net_gain_pct = round((costs.net_pnl / (entry * 100)) * 100.0, 4)

        # 7. Score via QualityModel (None if NO_MODEL)
        quality_score = self.quality_model.score_signal(recent.to_dict())

        action_word = "Breakout" if is_long else "Breakdown"
        barrier_price = orb_high if is_long else orb_low
        barrier_label = "high" if is_long else "low"

        return Signal(
            id=f"sig_10m_{uuid.uuid4().hex[:8]}",
            strategy_type=StrategyType.SCALPER_10M_ORB,
            symbol=context.symbol,
            side=side,
            timeframe="10m",
            timestamp=candle.timestamp,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            time_stop_minutes=75,
            regime=regime,
            quality_score=quality_score,
            expected_net_gain_pct=expected_net_gain_pct,
            reason=(
                f"10m Opening Range {action_word} confirmed on {context.symbol} in {regime.value}. "
                f"Close ₹{close:.2f} broke ORB {barrier_label} (₹{barrier_price:.2f}) with {vol_ratio:.1f}x volume. "
                f"Stop bracket: ₹{stop:.2f} ({self.stop_atr_mult}x ATR). Net gain after costs: +{expected_net_gain_pct:.3f}%."
            ),
        )
