"""
Unit-Test Only: Clearly Named Synthetic Candle Fixtures.
Rule: Keep synthetic candles strictly inside unit-test fixtures. Real data is platform default.
"""

import random
from datetime import datetime, timedelta
from typing import List

from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import IST


def create_synthetic_test_candles(
    symbol: str = "NIFTY",
    base_price: float = 22000.0,
    count: int = 100,
    timeframe: str = "1m",
    start_time: datetime = None,
    volatility: float = 2.0,
) -> List[Candle]:
    """
    Clearly named unit-test fixture generator for local mathematical verification.
    """
    start = start_time or datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    candles: List[Candle] = []
    p = base_price

    for i in range(count):
        t = start + timedelta(minutes=i)
        change = random.uniform(-0.001, 0.0012)
        o = p
        c = round(o * (1 + change), 2)
        h = round(max(o, c) + abs(random.uniform(0.5, volatility)), 2)
        low_val = round(min(o, c) - abs(random.uniform(0.5, volatility)), 2)
        vol = random.randint(1500, 10000)

        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=t,
                open=o,
                high=h,
                low=low_val,
                close=c,
                volume=vol,
                vwap=round((h + low_val + c) / 3.0, 2),
            )
        )
        p = c

    return candles
