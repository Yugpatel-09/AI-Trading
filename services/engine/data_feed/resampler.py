"""
TradeForge Candle Resampler.
Resamples 1m candles into 5m, 10m, and 15m timeframes strictly aligned to the
National Stock Exchange (NSE) session open at 09:15:00 IST (UTC+05:30).

Guarantees:
1. Strict session alignment: 09:15 IST open, 15:30 IST regular close.
2. No partial-candle leakage: Only fully closed candles are emitted in completed mode.
3. Gaps and holidays: Multi-day boundaries, weekend gaps, and intraday gaps are strictly
   handled without merging candles across trading sessions.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from tradeforge_shared.schemas import Candle

IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN_TIME = time(9, 15, 0)
SESSION_CLOSE_TIME = time(15, 30, 0)
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "10m": 10,
    "15m": 15,
}


def to_ist(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware and represented in Indian Standard Time (IST)."""
    if dt.tzinfo is None:
        # If naive, treat as IST if it falls in Indian market window, otherwise UTC
        if 9 <= dt.hour <= 16:
            return dt.replace(tzinfo=IST)
        return dt.replace(tzinfo=timezone.utc).astimezone(IST)
    return dt.astimezone(IST)


def get_session_bucket_window(
    timestamp: datetime,
    timeframe_minutes: int,
) -> Tuple[datetime, datetime]:
    """
    Calculate the (bucket_start, bucket_end) window for a given timestamp
    aligned to the NSE regular trading session start (09:15:00 IST).

    Regular session spans 09:15:00 to 15:30:00 IST (375 minutes).
    For timeframe N (e.g. 5m, 10m, 15m):
      bucket_idx = (minutes_since_0915) // N
      bucket_start = 09:15 + bucket_idx * N
      bucket_end = min(bucket_start + N, 15:30)
    """
    dt_ist = to_ist(timestamp)
    day = dt_ist.date()

    open_dt = datetime.combine(day, SESSION_OPEN_TIME, tzinfo=IST)
    close_dt = datetime.combine(day, SESSION_CLOSE_TIME, tzinfo=IST)

    if dt_ist < open_dt:
        # Pre-market bucket: align backwards from 09:15
        diff_mins = int((open_dt - dt_ist).total_seconds() // 60)
        bucket_idx = (diff_mins // timeframe_minutes) + 1
        b_start = open_dt - timedelta(minutes=bucket_idx * timeframe_minutes)
        b_end = b_start + timedelta(minutes=timeframe_minutes)
        return b_start, b_end

    if dt_ist >= close_dt:
        # Post-market bucket: align forwards from 15:30
        diff_mins = int((dt_ist - close_dt).total_seconds() // 60)
        bucket_idx = diff_mins // timeframe_minutes
        b_start = close_dt + timedelta(minutes=bucket_idx * timeframe_minutes)
        b_end = b_start + timedelta(minutes=timeframe_minutes)
        return b_start, b_end

    # Regular intraday trading session [09:15, 15:30)
    minutes_since_open = int((dt_ist - open_dt).total_seconds() // 60)
    bucket_idx = minutes_since_open // timeframe_minutes
    b_start = open_dt + timedelta(minutes=bucket_idx * timeframe_minutes)
    b_end = min(b_start + timedelta(minutes=timeframe_minutes), close_dt)

    return b_start, b_end


def aggregate_candle_bucket(
    candles: List[Candle],
    timeframe: str,
    bucket_start: datetime,
) -> Candle:
    """
    Aggregate a contiguous list of 1m candles into a single higher-timeframe Candle.
    Preserves symbol, computes OHLCV, and calculates volume-weighted VWAP.
    """
    if not candles:
        raise ValueError("Cannot aggregate empty list of candles")

    symbol = candles[0].symbol
    open_price = candles[0].open
    close_price = candles[-1].close
    high_price = max(c.high for c in candles)
    low_price = min(c.low for c in candles)
    total_volume = sum(c.volume for c in candles)

    # Volume-weighted average price for the bucket
    if total_volume > 0:
        sum_pv = sum((c.vwap or c.close) * c.volume for c in candles)
        vwap = round(sum_pv / total_volume, 2)
    else:
        vwap = round((open_price + high_price + low_price + close_price) / 4.0, 2)

    # Preserve output timestamp timezone matching input candle
    first_ts = candles[0].timestamp
    if first_ts.tzinfo is not None:
        out_timestamp = bucket_start.astimezone(first_ts.tzinfo)
    else:
        out_timestamp = bucket_start.replace(tzinfo=None)

    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=out_timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=total_volume,
        vwap=vwap,
    )


def resample_candles(
    candles: List[Candle],
    target_timeframe: str,
    complete_only: bool = True,
) -> List[Candle]:
    """
    Resample a list of 1m candles into target_timeframe ("5m", "10m", "15m").

    - Strict 09:15 IST NSE alignment.
    - No partial-candle leakage: Incomplete buckets (e.g. final bucket with only 2/5 bars)
      are not emitted when complete_only=True.
    - Gaps and holidays: Groups by date to prevent cross-day bleeding.
    """
    if not candles:
        return []

    if target_timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(
            f"Unsupported target timeframe: '{target_timeframe}'. "
            f"Supported: {list(TIMEFRAME_MINUTES.keys())}"
        )

    timeframe_minutes = TIMEFRAME_MINUTES[target_timeframe]
    if timeframe_minutes == 1:
        return list(candles)

    # 1. Sort chronologically
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)

    # 2. Group by trading session date in IST to prevent multi-day bleed
    candles_by_date: Dict[date, List[Candle]] = {}
    for c in sorted_candles:
        c_ist = to_ist(c.timestamp)
        candles_by_date.setdefault(c_ist.date(), []).append(c)

    resampled: List[Candle] = []

    for _d, day_candles in sorted(candles_by_date.items()):
        current_bucket_start: Optional[datetime] = None
        current_bucket_end: Optional[datetime] = None
        current_bucket_candles: List[Candle] = []

        for c in day_candles:
            b_start, b_end = get_session_bucket_window(c.timestamp, timeframe_minutes)

            if current_bucket_start is None:
                current_bucket_start = b_start
                current_bucket_end = b_end
                current_bucket_candles = [c]
            elif b_start == current_bucket_start:
                current_bucket_candles.append(c)
            else:
                # Previous bucket is complete because we have moved to a subsequent bucket
                if current_bucket_candles:
                    agg_bar = aggregate_candle_bucket(
                        current_bucket_candles,
                        target_timeframe,
                        current_bucket_start,
                    )
                    resampled.append(agg_bar)

                current_bucket_start = b_start
                current_bucket_end = b_end
                current_bucket_candles = [c]

        # Handle the final bucket of the day
        if current_bucket_candles and current_bucket_start and current_bucket_end:
            # Check completeness:
            # A bucket is complete if:
            # 1. Not complete_only (caller requested partials), OR
            # 2. Has the full expected count of 1m bars for that window duration, OR
            # 3. Last candle ends at/after the bucket end (or regular market close 15:30 IST)
            expected_bars = int(
                (current_bucket_end - current_bucket_start).total_seconds() // 60
            )
            is_full_count = len(current_bucket_candles) >= expected_bars

            last_c_ist = to_ist(current_bucket_candles[-1].timestamp)
            next_minute = last_c_ist + timedelta(minutes=1)
            is_time_past_end = next_minute >= current_bucket_end

            if not complete_only or is_full_count or is_time_past_end:
                agg_bar = aggregate_candle_bucket(
                    current_bucket_candles,
                    target_timeframe,
                    current_bucket_start,
                )
                resampled.append(agg_bar)

    return resampled


class StreamingCandleResampler:
    """
    Event-driven Candle Resampler for paper and live execution.
    Consumes 1m candles tick-by-tick and emits newly completed 5m, 10m, and 15m candles
    with zero partial-candle leakage.
    """

    def __init__(self, target_timeframes: Optional[List[str]] = None):
        self.target_timeframes = target_timeframes or ["5m", "10m", "15m"]
        # timeframe -> {bucket_start, bucket_end, candles}
        self._buffers: Dict[str, Dict] = {}
        for tf in self.target_timeframes:
            if tf not in TIMEFRAME_MINUTES:
                raise ValueError(f"Unsupported timeframe: {tf}")
            self._buffers[tf] = {
                "start": None,
                "end": None,
                "candles": [],
            }

    def add_candle(self, candle: Candle) -> Dict[str, Optional[Candle]]:
        """
        Process a new 1m candle.
        Returns a dict mapping timeframe -> newly closed Candle (or None if still in-progress).
        """
        closed_candles: Dict[str, Optional[Candle]] = {}

        for tf in self.target_timeframes:
            tf_mins = TIMEFRAME_MINUTES[tf]
            buf = self._buffers[tf]
            b_start, b_end = get_session_bucket_window(candle.timestamp, tf_mins)

            if buf["start"] is None:
                buf["start"] = b_start
                buf["end"] = b_end
                buf["candles"] = [candle]
                closed_candles[tf] = None
            elif b_start == buf["start"]:
                buf["candles"].append(candle)
                closed_candles[tf] = None
            else:
                # The previous bucket has finalized because time has advanced to a new bucket
                closed_bar = aggregate_candle_bucket(
                    buf["candles"],
                    tf,
                    buf["start"],
                )
                closed_candles[tf] = closed_bar

                # Reset buffer with the new candle
                buf["start"] = b_start
                buf["end"] = b_end
                buf["candles"] = [candle]

        return closed_candles

    def flush(self) -> Dict[str, Optional[Candle]]:
        """
        Finalize and flush any pending in-flight buckets (e.g. at 15:30 market close).
        """
        flushed: Dict[str, Optional[Candle]] = {}
        for tf, buf in self._buffers.items():
            if buf["candles"] and buf["start"]:
                flushed[tf] = aggregate_candle_bucket(
                    buf["candles"],
                    tf,
                    buf["start"],
                )
                buf["start"] = None
                buf["end"] = None
                buf["candles"] = []
            else:
                flushed[tf] = None
        return flushed
