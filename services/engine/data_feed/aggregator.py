"""
Tick-to-Candle Aggregator.

Converts real-time tick streams into 1-minute OHLCV candles strictly aligned
to the NSE 09:15:00 IST market session open.

Non-Negotiable Guarantees:
1. Strict 09:15:00 IST alignment: Minute buckets start on the minute boundary (:00.000).
2. Cumulative to per-candle volume conversion:
   Kite sends cumulative daily volume. The aggregator tracks the delta and resets daily.
3. Out-of-order & duplicate tick handling: Drops or absorbs ticks without corrupting high/low.
4. Intraday Gap Handling: Emits zero-volume flat candles if ticks pause mid-session.
5. Complete-Candles-Only: Emits completed candles ONLY after the minute has fully closed,
   preventing intra-bar strategy lookahead bias.
"""

from datetime import datetime, timedelta
from typing import Callable, List, Optional

from pydantic import BaseModel
from tradeforge_shared.schemas import Candle

from services.api.app.core.logging import logger
from services.engine.data_feed.calendar import IST, nse_calendar


class MarketTick(BaseModel):
    """Raw tick data packet received from KiteTicker or simulated feed."""
    instrument_token: int
    symbol: str
    last_price: float
    last_quantity: int = 0
    volume_traded: int = 0  # Cumulative day volume from Kite
    timestamp: datetime
    buy_quantity: int = 0
    sell_quantity: int = 0


class BarAccumulator:
    """Internal working state for a forming 1-minute candle."""
    def __init__(self, symbol: str, bucket_start: datetime, first_price: float):
        self.symbol = symbol
        self.bucket_start = bucket_start
        self.open = first_price
        self.high = first_price
        self.low = first_price
        self.close = first_price
        self.volume = 0
        self.price_volume_sum = 0.0

    def update(self, price: float, delta_volume: int):
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += max(0, delta_volume)
        self.price_volume_sum += price * max(0, delta_volume)

    def to_candle(self) -> Candle:
        vwap = (self.price_volume_sum / self.volume) if self.volume > 0 else self.close
        return Candle(
            symbol=self.symbol,
            timeframe="1m",
            timestamp=self.bucket_start,
            open=round(self.open, 2),
            high=round(self.high, 2),
            low=round(self.low, 2),
            close=round(self.close, 2),
            volume=self.volume,
            vwap=round(vwap, 2),
        )


class TickToCandleAggregator:
    """
    Stateful real-time aggregator converting tick streams into closed 1-minute candles.
    """

    def __init__(
        self,
        symbol: str,
        on_candle_close: Optional[Callable[[Candle], None]] = None,
        fill_gaps: bool = True,
    ):
        self.symbol = symbol.upper().strip()
        self.on_candle_close = on_candle_close
        self.fill_gaps = fill_gaps

        self._active_bar: Optional[BarAccumulator] = None
        self._last_closed_candle: Optional[Candle] = None
        self._last_cumulative_volume: int = 0
        self._last_tick_time: Optional[datetime] = None
        self._completed_candles: List[Candle] = []

    @property
    def completed_candles(self) -> List[Candle]:
        return list(self._completed_candles)

    @staticmethod
    def floor_to_minute(dt: datetime) -> datetime:
        """Align timestamp to the start of the 1-minute boundary in IST."""
        ist_dt = dt.astimezone(IST) if dt.tzinfo else dt.replace(tzinfo=IST)
        return ist_dt.replace(second=0, microsecond=0)

    def process_tick(self, tick: MarketTick) -> List[Candle]:
        """
        Process incoming tick, update active bar, and return any newly closed candles.
        """
        tick_time = tick.timestamp.astimezone(IST) if tick.timestamp.tzinfo else tick.timestamp.replace(tzinfo=IST)
        tick_price = float(tick.last_price)

        # 1. Out-of-order check: Ignore ticks that arrive from the past
        if self._last_tick_time and tick_time < self._last_tick_time - timedelta(seconds=2):
            logger.warning(f"Dropping out-of-order tick for {self.symbol}: {tick_time} < {self._last_tick_time}")
            return []

        self._last_tick_time = tick_time
        bucket_start = self.floor_to_minute(tick_time)

        # 2. Cumulative volume to per-tick delta volume conversion
        if self._last_cumulative_volume == 0:
            delta_volume = tick.last_quantity or 0
        elif tick.volume_traded >= self._last_cumulative_volume:
            delta_volume = tick.volume_traded - self._last_cumulative_volume
        else:
            # Day rollover or reset
            delta_volume = tick.last_quantity or 0

        self._last_cumulative_volume = tick.volume_traded
        emitted_candles: List[Candle] = []

        # 3. First tick of the session
        if self._active_bar is None:
            self._active_bar = BarAccumulator(self.symbol, bucket_start, tick_price)
            self._active_bar.update(tick_price, delta_volume)
            return []

        # 4. Same minute bucket: update running bar
        if bucket_start == self._active_bar.bucket_start:
            self._active_bar.update(tick_price, delta_volume)
            return []

        # 5. Minute has rolled over: Close the previous bar
        closed_candle = self._active_bar.to_candle()
        self._completed_candles.append(closed_candle)
        emitted_candles.append(closed_candle)
        self._last_closed_candle = closed_candle

        if self.on_candle_close:
            self.on_candle_close(closed_candle)

        # 6. Intraday Gap Handling: Fill missing minutes between previous and current bar
        if self.fill_gaps and bucket_start > self._active_bar.bucket_start + timedelta(minutes=1):
            gap_cursor = self._active_bar.bucket_start + timedelta(minutes=1)
            last_close = closed_candle.close

            while gap_cursor < bucket_start:
                # Only fill gaps during active market hours
                if nse_calendar.is_market_open(gap_cursor):
                    gap_candle = Candle(
                        symbol=self.symbol,
                        timeframe="1m",
                        timestamp=gap_cursor,
                        open=last_close,
                        high=last_close,
                        low=last_close,
                        close=last_close,
                        volume=0,
                        vwap=last_close,
                    )
                    self._completed_candles.append(gap_candle)
                    emitted_candles.append(gap_candle)
                    self._last_closed_candle = gap_candle
                    if self.on_candle_close:
                        self.on_candle_close(gap_candle)

                gap_cursor += timedelta(minutes=1)

        # 7. Start new bar for the new bucket
        self._active_bar = BarAccumulator(self.symbol, bucket_start, tick_price)
        self._active_bar.update(tick_price, delta_volume)

        return emitted_candles

    def force_close_active_bar(self) -> Optional[Candle]:
        """
        Force-close any forming bar at market close (15:30 IST) or session shutdown.
        """
        if not self._active_bar:
            return None
        candle = self._active_bar.to_candle()
        self._completed_candles.append(candle)
        self._last_closed_candle = candle
        self._active_bar = None
        if self.on_candle_close:
            self.on_candle_close(candle)
        return candle
