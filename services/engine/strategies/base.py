from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from tradeforge_shared.enums import StrategyType
from tradeforge_shared.schemas import Candle, Signal


class StrategyContext:
    """Market context passed into strategy on each candle close."""
    def __init__(
        self,
        symbol: str,
        current_candle: Candle,
        candle_history_1m: List[Candle],
        candle_history_5m: List[Candle],
        candle_history_10m: List[Candle],
        vwap: float,
        daily_open: float,
        opening_range_high: Optional[float] = None,
        opening_range_low: Optional[float] = None,
        candle_history_15m: Optional[List[Candle]] = None,
        features: Optional[Dict[str, Any]] = None,
        index_direction: Optional[int] = None,
        index_candles: Optional[List[Candle]] = None,
    ):
        self.symbol = symbol
        self.current_candle = current_candle
        self.candle_history_1m = candle_history_1m
        self.candle_history_5m = candle_history_5m
        self.candle_history_10m = candle_history_10m
        self.candle_history_15m = candle_history_15m or []
        self.vwap = vwap
        self.daily_open = daily_open
        self.opening_range_high = opening_range_high
        self.opening_range_low = opening_range_low
        self.features = features or {}
        self.index_direction = index_direction
        self.index_candles = index_candles or []

class BaseStrategy(ABC):
    """
    Unified Strategy Interface.
    Rule 5: The same strategy code must run in backtest, paper, and live.
    No separate logic.
    """
    def __init__(self, strategy_type: StrategyType):
        self.strategy_type = strategy_type

    @abstractmethod
    def on_candle(self, context: StrategyContext) -> Optional[Signal]:
        """
        Evaluate candle close event.
        Returns a Signal with entry, mandatory stop-loss, target, and plain-English rationale,
        or None if no setup exists.
        """
        pass
