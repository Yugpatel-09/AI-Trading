#!/usr/bin/env python3
"""
TradeForge Synthetic Historical Market Data Seeder.
Generates realistic 1m, 5m, and 10m OHLCV candle datasets for NIFTY, BANKNIFTY, and RELIANCE.
"""
import random
from datetime import datetime, timedelta, timezone

from tradeforge_shared.schemas import Candle


def generate_candles(symbol: str = "NIFTY", base_price: float = 22000.0, count: int = 100, timeframe: str = "1m"):
    candles = []
    current_price = base_price
    start_time = datetime.now(timezone.utc) - timedelta(minutes=count)

    for i in range(count):
        candle_time = start_time + timedelta(minutes=i)
        change_pct = random.uniform(-0.0015, 0.0018)
        open_price = round(current_price, 2)
        close_price = round(open_price * (1 + change_pct), 2)
        high_price = round(max(open_price, close_price) + abs(random.uniform(0.5, 3.0)), 2)
        low_price = round(min(open_price, close_price) - abs(random.uniform(0.5, 3.0)), 2)
        volume = random.randint(1500, 12000)

        candle = Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=candle_time,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            vwap=round((high_price + low_price + close_price) / 3, 2),
        )
        candles.append(candle)
        current_price = close_price

    return candles

if __name__ == "__main__":
    nifty_candles = generate_candles("NIFTY", 22100.0, 50, "1m")
    print(f"Generated {len(nifty_candles)} synthetic 1m candles for NIFTY.")
    print(f"Latest Close: ₹{nifty_candles[-1].close:,.2f} at {nifty_candles[-1].timestamp.isoformat()}")
