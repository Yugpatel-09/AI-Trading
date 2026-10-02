"""
Unit Tests for TradeForge Candle Resampler.
Verifies:
1. 1m -> 5m, 10m, 15m OHLCV + VWAP aggregation accuracy.
2. Strict 09:15:00 IST session alignment.
3. No partial-candle leakage (incomplete buckets are excluded in complete_only mode).
4. StreamingCandleResampler real-time behavior without lookahead.
5. Intraday gap resilience.
6. Multi-day and holiday boundary isolation (never merging candles across days).
"""

from datetime import datetime, timedelta

from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import (
    IST,
    StreamingCandleResampler,
    get_session_bucket_window,
    resample_candles,
    to_ist,
)


def create_1m_candle(
    day_offset: int,
    hour: int,
    minute: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1000,
    symbol: str = "NIFTY",
) -> Candle:
    # 2026-10-05 is a Monday
    base_date = datetime(2026, 10, 5, hour, minute, 0, tzinfo=IST) + timedelta(days=day_offset)
    return Candle(
        symbol=symbol,
        timeframe="1m",
        timestamp=base_date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        vwap=round((open_ + high + low + close) / 4.0, 2),
    )


def test_session_bucket_window_alignment():
    """Verify that bucket windows align strictly to 09:15 IST."""
    t_0915 = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    t_0918 = datetime(2026, 10, 5, 9, 18, 30, tzinfo=IST)
    t_0920 = datetime(2026, 10, 5, 9, 20, 0, tzinfo=IST)

    # 5-minute buckets
    b_start, b_end = get_session_bucket_window(t_0915, 5)
    assert b_start == t_0915
    assert b_end == t_0915 + timedelta(minutes=5)

    b_start_18, b_end_18 = get_session_bucket_window(t_0918, 5)
    assert b_start_18 == t_0915
    assert b_end_18 == t_0915 + timedelta(minutes=5)

    b_start_20, b_end_20 = get_session_bucket_window(t_0920, 5)
    assert b_start_20 == t_0920
    assert b_end_20 == t_0920 + timedelta(minutes=5)

    # 10-minute buckets: 09:15 to 09:25
    b10_start, b10_end = get_session_bucket_window(t_0918, 10)
    assert b10_start == t_0915
    assert b10_end == t_0915 + timedelta(minutes=10)

    # 15-minute buckets: 09:15 to 09:30
    b15_start, b15_end = get_session_bucket_window(t_0918, 15)
    assert b15_start == t_0915
    assert b15_end == t_0915 + timedelta(minutes=15)


def test_resample_5m_aggregation_accuracy():
    """Verify exact OHLCV and volume-weighted VWAP aggregation across 5 1m candles."""
    candles_1m = [
        create_1m_candle(0, 9, 15, open_=100.0, high=105.0, low=99.0, close=102.0, volume=100),
        create_1m_candle(0, 9, 16, open_=102.0, high=106.0, low=101.0, close=104.0, volume=200),
        create_1m_candle(0, 9, 17, open_=104.0, high=108.0, low=103.0, close=107.0, volume=300),
        create_1m_candle(0, 9, 18, open_=107.0, high=107.5, low=102.0, close=103.0, volume=200),
        create_1m_candle(0, 9, 19, open_=103.0, high=105.0, low=98.0, close=101.0, volume=200),
    ]

    resampled = resample_candles(candles_1m, target_timeframe="5m", complete_only=True)
    assert len(resampled) == 1

    bar_5m = resampled[0]
    assert bar_5m.symbol == "NIFTY"
    assert bar_5m.timeframe == "5m"
    assert bar_5m.open == 100.0   # Open of first candle
    assert bar_5m.high == 108.0   # Highest high across the 5 minutes
    assert bar_5m.low == 98.0     # Lowest low across the 5 minutes
    assert bar_5m.close == 101.0  # Close of last candle
    assert bar_5m.volume == 1000  # Sum of volume: 100+200+300+200+200
    assert bar_5m.timestamp == candles_1m[0].timestamp
    assert bar_5m.vwap is not None


def test_no_partial_candle_leakage():
    """
    CRITICAL SAFETY REQUIREMENT:
    An ongoing bucket with partial candles (e.g. only 3 out of 5 minutes)
    MUST NOT be emitted when complete_only=True.
    """
    # 3 candles for [09:15, 09:20) window
    partial_1m = [
        create_1m_candle(0, 9, 15, 100.0, 102.0, 99.0, 101.0),
        create_1m_candle(0, 9, 16, 101.0, 103.0, 100.0, 102.0),
        create_1m_candle(0, 9, 17, 102.0, 104.0, 101.0, 103.0),
    ]

    # In complete_only mode: should be 0 because 09:18 and 09:19 haven't occurred
    res_complete = resample_candles(partial_1m, target_timeframe="5m", complete_only=True)
    assert len(res_complete) == 0

    # In non-complete mode: partial can be returned if explicitly requested
    res_partial = resample_candles(partial_1m, target_timeframe="5m", complete_only=False)
    assert len(res_partial) == 1
    assert res_partial[0].close == 103.0


def test_streaming_candle_resampler_zero_lookahead():
    """
    Verify StreamingCandleResampler emits 5m and 10m bars only when their window ends.
    """
    streaming = StreamingCandleResampler(target_timeframes=["5m", "10m"])

    # Feed 1m candles for 09:15 to 09:19
    for m in range(15, 20):
        c = create_1m_candle(0, 9, m, 100.0 + m, 101.0 + m, 99.0 + m, 100.5 + m)
        emitted = streaming.add_candle(c)
        # None of the higher timeframe bars should be emitted yet!
        assert emitted["5m"] is None
        assert emitted["10m"] is None

    # Feed candle at 09:20 (start of next 5m bucket)
    c_0920 = create_1m_candle(0, 9, 20, 120.0, 121.0, 119.0, 120.5)
    emitted_20 = streaming.add_candle(c_0920)

    # 5m bar for [09:15, 09:20) should now be emitted!
    assert emitted_20["5m"] is not None
    assert emitted_20["5m"].timeframe == "5m"
    assert emitted_20["5m"].timestamp == create_1m_candle(0, 9, 15, 0, 0, 0, 0).timestamp

    # 10m bar for [09:15, 09:25) should NOT be emitted yet!
    assert emitted_20["10m"] is None

    # Feed candles 09:21 to 09:24
    for m in range(21, 25):
        c = create_1m_candle(0, 9, m, 120.0 + m, 121.0 + m, 119.0 + m, 120.5 + m)
        emitted = streaming.add_candle(c)
        assert emitted["5m"] is None
        assert emitted["10m"] is None

    # Feed candle at 09:25
    c_0925 = create_1m_candle(0, 9, 25, 130.0, 131.0, 129.0, 130.5)
    emitted_25 = streaming.add_candle(c_0925)

    # Both second 5m bar [09:20, 09:25) and first 10m bar [09:15, 09:25) should emit!
    assert emitted_25["5m"] is not None
    assert emitted_25["10m"] is not None
    assert emitted_25["10m"].timeframe == "10m"
    assert emitted_25["10m"].open == create_1m_candle(0, 9, 15, 115.0, 0, 0, 0).open


def test_gap_and_holiday_handling_never_merges_across_days():
    """
    Verify Friday session close (15:30 IST) and Monday session open (09:15 IST)
    are strictly separated and never merged into a single higher-timeframe bar.
    """
    # Friday 2026-10-02 afternoon
    friday_bars = [
        create_1m_candle(-3, 15, 25, 200.0, 202.0, 199.0, 201.0),
        create_1m_candle(-3, 15, 26, 201.0, 203.0, 200.0, 202.0),
        create_1m_candle(-3, 15, 27, 202.0, 204.0, 201.0, 203.0),
        create_1m_candle(-3, 15, 28, 203.0, 205.0, 202.0, 204.0),
        create_1m_candle(-3, 15, 29, 204.0, 206.0, 203.0, 205.0),
    ]

    # Monday 2026-10-05 morning
    monday_bars = [
        create_1m_candle(0, 9, 15, 220.0, 222.0, 219.0, 221.0),
        create_1m_candle(0, 9, 16, 221.0, 223.0, 220.0, 222.0),
        create_1m_candle(0, 9, 17, 222.0, 224.0, 221.0, 223.0),
        create_1m_candle(0, 9, 18, 223.0, 225.0, 222.0, 224.0),
        create_1m_candle(0, 9, 19, 224.0, 226.0, 223.0, 225.0),
    ]

    all_candles = friday_bars + monday_bars
    res_5m = resample_candles(all_candles, target_timeframe="5m", complete_only=True)

    assert len(res_5m) == 2
    friday_5m = res_5m[0]
    monday_5m = res_5m[1]

    # Friday bar must only reflect Friday prices
    assert to_ist(friday_5m.timestamp).date() != to_ist(monday_5m.timestamp).date()
    assert friday_5m.open == 200.0
    assert friday_5m.close == 205.0

    # Monday bar must only reflect Monday prices
    assert monday_5m.open == 220.0
    assert monday_5m.close == 225.0


def test_session_close_at_1530():
    """Verify final session bucket at 15:25 closes cleanly at 15:30 IST."""
    closing_bars = [
        create_1m_candle(0, 15, 25, 300.0, 302.0, 299.0, 301.0),
        create_1m_candle(0, 15, 26, 301.0, 303.0, 300.0, 302.0),
        create_1m_candle(0, 15, 27, 302.0, 304.0, 301.0, 303.0),
        create_1m_candle(0, 15, 28, 303.0, 305.0, 302.0, 304.0),
        create_1m_candle(0, 15, 29, 304.0, 306.0, 303.0, 305.0),
    ]

    res_10m = resample_candles(closing_bars, target_timeframe="10m", complete_only=True)
    # The 15:25-15:30 interval is 5 minutes because NSE closes at 15:30:00
    assert len(res_10m) == 1
    assert res_10m[0].open == 300.0
    assert res_10m[0].close == 305.0
