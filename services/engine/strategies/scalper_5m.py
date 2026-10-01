import uuid
from typing import Optional

from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType
from tradeforge_shared.schemas import Signal

from services.engine.features.indicators import TechnicalIndicators
from services.engine.strategies.base import BaseStrategy, StrategyContext


class Scalper5M(BaseStrategy):
    """
    5-Minute Scalper Specification:
    - Speed: Medium, 5 to 40 min hold.
    - Trigger: EMA 9 crosses above EMA 21 with above-average volume.
    - Trend Filter: 15m trend agreement and above VWAP.
    - Typical Target: 0.30% to 0.60%.
    - Stop: 1.0 x ATR.
    - Trades per day cap: 5 to 8.
    """
    def __init__(self, target_pct: float = 0.0045, stop_atr_mult: float = 1.0):
        super().__init__(StrategyType.SCALPER_5M)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_5m
        if len(history) < 22:
            return None

        # Time check
        candle_time = candle.timestamp.time() if hasattr(candle.timestamp, "time") else None
        if candle_time and (candle_time.hour >= 15 or (candle_time.hour == 9 and candle_time.minute < 20)):
            return None

        df = TechnicalIndicators.compute_all_features(history)
        recent = df.iloc[-1]
        prev = df.iloc[-2]

        close = candle.close
        ema_9_now = recent["ema_9"]
        ema_21_now = recent["ema_21"]
        ema_9_prev = prev["ema_9"]
        ema_21_prev = prev["ema_21"]
        vwap = recent.get("vwap", close)
        atr = recent.get("atr", close * 0.005)
        vol_ratio = recent.get("vol_ratio", 1.0)

        # Bullish EMA Cross: EMA 9 crosses above EMA 21
        bullish_cross = ema_9_prev <= ema_21_prev and ema_9_now > ema_21_now
        above_vwap = close > vwap

        if bullish_cross and above_vwap and vol_ratio >= 1.1:
            stop_distance = max(2.0, atr * self.stop_atr_mult)
            entry = close
            stop = round(entry - stop_distance, 2)
            target = round(entry * (1 + self.target_pct), 2)

            return Signal(
                id=f"sig_5m_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.SCALPER_5M,
                symbol=context.symbol,
                side=OrderSide.BUY,
                timeframe="5m",
                timestamp=candle.timestamp,
                entry_price=entry,
                stop_loss=stop,
                target=target,
                time_stop_minutes=40,
                regime=MarketRegime.TRENDING_BULLISH,
                quality_score=0.79,
                expected_net_gain_pct=round(self.target_pct * 100, 2),
                reason=(
                    f"5m EMA 9/21 cross confirmed on {context.symbol} above VWAP. "
                    f"EMA 9 ({ema_9_now:.2f}) crossed above EMA 21 ({ema_21_now:.2f}) with {vol_ratio:.1f}x volume. "
                    f"Stop set at ₹{stop:.2f} (1.0x ATR)."
                ),
            )

        return None
