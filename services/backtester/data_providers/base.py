"""
TradeForge Historical Market Data Provider Interface.
Rule: Real data is the default. Synthetic candles are restricted strictly to unit-test fixtures.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from tradeforge_shared.schemas import Candle


class DataProvider(ABC):
    """
    Abstract interface for loading historical candle datasets for backtesting and ML pipelines.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier for the data source."""
        pass

    @abstractmethod
    def load_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Candle]:
        """
        Load historical OHLCV candles chronologically sorted.
        """
        pass
