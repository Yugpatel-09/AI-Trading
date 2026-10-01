import uuid
from typing import Optional
from tradeforge_shared.schemas import Signal
from tradeforge_shared.enums import StrategyType, OrderSide, MarketRegime
from services.engine.strategies.base import BaseStrategy, StrategyContext
from services.engine.features.indicators import TechnicalIndicators

class Scalper10MORB(BaseStrategy):
    """
    10-Minute Opening Range Breakout (ORB) Scalper Specification:
    - Speed: Slower, 10 to 90 min hold.
    - Trigger: Opening range breakout (high of 09:15-09:35 broken) with volume confirmation.
    - Trend Filter: Daily bias + index agreement.
    - Typical Target: 0.50% to 1.00%.
    - Stop: 1.0 to 1.2 x ATR.
    - Trades per day cap: 3 to 5.
    """
    def __init__(self, target_pct: float = 0.0075, stop_atr_mult: float = 1.1):
        super().__init__(StrategyType.SCALPER_10M_ORB)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_10m
        if len(history) < 3 or not context.opening_range_high:
            return None

        # Time check: ORB entries occur between 09:35 and 13:00
        candle_time = candle.timestamp.time() if hasattr(candle.timestamp, "time") else None
        if candle_time and (candle_time.hour >= 14 or (candle_time.hour == 9 and candle_time.minute < 35)):
            return None

        df = TechnicalIndicators.compute_all_features(history)
        recent = df.iloc[-1]
        close = candle.close
        high = candle.high
        orb_high = context.opening_range_high
        atr = recent.get("atr", close * 0.006)
        vol_ratio = recent.get("vol_ratio", 1.0)

        # Bullish ORB Breakout: Candle closes cleanly above opening range high
        if close > orb_high and high > orb_high * 1.001 and vol_ratio >= 1.25:
            stop_distance = max(3.0, atr * self.stop_atr_mult)
            entry = close
            stop = round(entry - stop_distance, 2)
            target = round(entry * (1 + self.target_pct), 2)

            return Signal(
                id=f"sig_10m_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.SCALPER_10M_ORB,
                symbol=context.symbol,
                side=OrderSide.BUY,
                timeframe="10m",
                timestamp=candle.timestamp,
                entry_price=entry,
                stop_loss=stop,
                target=target,
                time_stop_minutes=75,
                regime=MarketRegime.TRENDING_BULLISH,
                quality_score=0.82,
                expected_net_gain_pct=round(self.target_pct * 100, 2),
                reason=(
                    f"10m Opening Range Breakout confirmed on {context.symbol}. "
                    f"Close ₹{close:.2f} broke above ORB high (₹{orb_high:.2f}) with {vol_ratio:.1f}x volume expansion. "
                    f"Stop bracket set at ₹{stop:.2f} ({self.stop_atr_mult}x ATR)."
                ),
            )

        return None
