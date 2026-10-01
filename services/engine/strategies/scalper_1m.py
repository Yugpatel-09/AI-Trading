import uuid
from datetime import datetime, timezone
from typing import Optional
from tradeforge_shared.schemas import Signal
from tradeforge_shared.enums import StrategyType, OrderSide, MarketRegime
from services.engine.strategies.base import BaseStrategy, StrategyContext
from services.engine.features.indicators import TechnicalIndicators

class Scalper1M(BaseStrategy):
    """
    1-Minute Scalper Specification:
    - Speed: Very fast, 1 to 10 min hold.
    - Trigger: VWAP pullback in the direction of the 5m trend with volume burst.
    - Typical Target: 0.15% to 0.30%.
    - Stop: 0.8 x ATR (tight bracket).
    - Trades per day cap: 8 to 12.
    """
    def __init__(self, target_pct: float = 0.0025, stop_atr_mult: float = 0.8):
        super().__init__(StrategyType.SCALPER_1M)
        self.target_pct = target_pct
        self.stop_atr_mult = stop_atr_mult

    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        candle = context.current_candle
        history = context.candle_history_1m
        if len(history) < 15:
            return None

        # Time check: No trades first 5 mins (before 09:20) or after 15:00
        candle_time = candle.timestamp.time() if hasattr(candle.timestamp, "time") else None
        if candle_time:
            if candle_time.hour == 9 and candle_time.minute < 20:
                return None
            if candle_time.hour >= 15:
                return None

        df = TechnicalIndicators.compute_all_features(history)
        recent = df.iloc[-1]
        prev = df.iloc[-2]

        close = candle.close
        vwap = recent.get("vwap", close)
        atr = recent.get("atr", close * 0.003)
        vol_ratio = recent.get("vol_ratio", 1.0)

        # Bullish VWAP Pullback:
        # Price previously tapped/pierced VWAP from above and closed back above VWAP with volume
        if prev["low"] <= vwap and close > vwap and vol_ratio >= 1.2:
            stop_distance = max(1.0, atr * self.stop_atr_mult)
            entry = close
            stop = round(entry - stop_distance, 2)
            target = round(entry * (1 + self.target_pct), 2)

            return Signal(
                id=f"sig_1m_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.SCALPER_1M,
                symbol=context.symbol,
                side=OrderSide.BUY,
                timeframe="1m",
                timestamp=candle.timestamp,
                entry_price=entry,
                stop_loss=stop,
                target=target,
                time_stop_minutes=15,
                regime=MarketRegime.TRENDING_BULLISH,
                quality_score=0.74,
                expected_net_gain_pct=round(self.target_pct * 100, 2),
                reason=(
                    f"1m VWAP pullback confirmed on {context.symbol}. "
                    f"Price tested VWAP (₹{vwap:.2f}) and closed above with {vol_ratio:.1f}x volume expansion. "
                    f"Stop bracket set at ₹{stop:.2f} ({self.stop_atr_mult}x ATR)."
                ),
            )

        return None
