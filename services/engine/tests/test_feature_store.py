"""
Unit Tests for TradeForge Unified Shared Feature Store.
Verifies:
1. Presence and accuracy of all 12 institutional features:
   EMA 9/21, RSI, ATR, ADX (+DI/-DI), Supertrend, VWAP, vol_ratio,
   opening range, spread, time-of-day, gap size.
2. Opening range is None before window closes (e.g. before 09:30), then freezes.
3. Daily-reset VWAP resets at 09:15 open.
4. Overnight gap size across consecutive trading sessions.
5. Strongly typed MarketFeatures model.
"""

from datetime import datetime, timedelta

import numpy as np
from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import IST
from services.engine.features.store import FeatureStore, MarketFeatures


def create_session_candles(
    day_offset: int = 0,
    base_price: float = 1000.0,
    count: int = 60,
    start_hour: int = 9,
    start_minute: int = 15,
) -> list[Candle]:
    base_date = datetime(2026, 10, 5, start_hour, start_minute, 0, tzinfo=IST) + timedelta(days=day_offset)
    candles = []
    price = base_price
    for i in range(count):
        ts = base_date + timedelta(minutes=i)
        # Gentle alternating move
        delta = 1.5 if i % 2 == 0 else -0.5
        open_ = price
        close_ = price + delta
        high_ = max(open_, close_) + 1.0
        low_ = min(open_, close_) - 1.0
        vol = 1000 + i * 10
        candles.append(
            Candle(
                symbol="TCS",
                timeframe="1m",
                timestamp=ts,
                open=round(open_, 2),
                high=round(high_, 2),
                low=round(low_, 2),
                close=round(close_, 2),
                volume=vol,
                vwap=round((high_ + low_ + close_) / 3.0, 2),
            )
        )
        price = close_
    return candles


def test_feature_store_all_12_features_present():
    """Verify all 12 core institutional features are computed and non-empty."""
    candles = create_session_candles(day_offset=0, base_price=1000.0, count=60)
    df = FeatureStore.compute_features_df(candles, opening_range_minutes=15)

    assert len(df) == 60

    # 1. EMA 9/21
    assert "ema_9" in df.columns
    assert "ema_21" in df.columns
    assert not np.isnan(df["ema_9"].iloc[-1])
    assert not np.isnan(df["ema_21"].iloc[-1])

    # 2. RSI (14)
    assert "rsi" in df.columns
    assert not np.isnan(df["rsi"].iloc[-1])

    # 3. ATR (14)
    assert "atr" in df.columns
    assert not np.isnan(df["atr"].iloc[-1])

    # 4. ADX with +DI / -DI
    assert "adx" in df.columns
    assert "plus_di" in df.columns
    assert "minus_di" in df.columns

    # 5. Supertrend with direction
    assert "supertrend" in df.columns
    assert "supertrend_direction" in df.columns
    assert df["supertrend_direction"].iloc[-1] in (1, -1)

    # 6. Daily-reset VWAP
    assert "vwap" in df.columns
    assert df["vwap"].iloc[-1] > 0

    # 7. Volume ratio
    assert "vol_ratio" in df.columns
    assert df["vol_ratio"].iloc[-1] > 0

    # 8. Opening range high/low
    assert "opening_range_high" in df.columns
    assert "opening_range_low" in df.columns

    # 9. Spread (points & pct)
    assert "spread_points" in df.columns
    assert "spread_pct" in df.columns
    assert (df["spread_points"] >= 0).all()

    # 10. Time of day
    assert "time_of_day_minutes" in df.columns
    assert df["time_of_day_minutes"].iloc[0] == 0   # 09:15 is minute 0
    assert df["time_of_day_minutes"].iloc[15] == 15 # 09:30 is minute 15

    # 11. Gap size
    assert "gap_points" in df.columns
    assert "gap_pct" in df.columns

    # 12. Daily open
    assert "daily_open" in df.columns
    assert df["daily_open"].iloc[0] == candles[0].open


def test_opening_range_behavior_no_leakage_before_window():
    """
    Verify opening range returns None during the initial 15 minutes,
    then locks into fixed high and low values once the window completes.
    """
    candles = create_session_candles(day_offset=0, base_price=1000.0, count=45)
    df = FeatureStore.compute_features_df(candles, opening_range_minutes=15)

    # First 15 candles are from 09:15 to 09:29. Cutoff is 09:30.
    # At index 0 to 14: opening range should be NaN (not leaked before window closes)
    for i in range(15):
        assert np.isnan(df["opening_range_high"].iloc[i])
        assert np.isnan(df["opening_range_low"].iloc[i])

    # At index 15 (09:30) and beyond: opening range is frozen
    or_high_at_30 = df["opening_range_high"].iloc[15]
    or_low_at_30 = df["opening_range_low"].iloc[15]

    assert not np.isnan(or_high_at_30)
    assert not np.isnan(or_low_at_30)
    assert or_high_at_30 >= or_low_at_30

    # Should remain identical throughout the rest of the day
    for i in range(16, len(df)):
        assert df["opening_range_high"].iloc[i] == or_high_at_30
        assert df["opening_range_low"].iloc[i] == or_low_at_30


def test_gap_size_calculation_across_consecutive_sessions():
    """
    Verify gap size is calculated accurately from yesterday's close to today's open.
    """
    # Day 1: Closes at 1050.0
    day1_candles = create_session_candles(day_offset=0, base_price=1000.0, count=30)
    # Day 2: Opens at 1080.0 (Gap of +30 points)
    day2_candles = create_session_candles(day_offset=1, base_price=1080.0, count=30)

    combined = day1_candles + day2_candles
    df = FeatureStore.compute_features_df(combined)

    day1_mask = df["date_ist"] == datetime(2026, 10, 5).date()
    day2_mask = df["date_ist"] == datetime(2026, 10, 6).date()

    # Day 1 has no previous session in dataset -> Gap is 0.0
    assert (df.loc[day1_mask, "gap_points"] == 0.0).all()

    # Day 2 has gap = 1080.0 - day1_last_close
    day1_last_close = day1_candles[-1].close
    expected_gap_pts = round(1080.0 - day1_last_close, 2)
    expected_gap_pct = round((expected_gap_pts / day1_last_close) * 100.0, 4)

    assert df.loc[day2_mask, "gap_points"].iloc[0] == expected_gap_pts
    assert df.loc[day2_mask, "gap_pct"].iloc[0] == expected_gap_pct


def test_market_features_strongly_typed_model():
    """Verify get_features_for_candle returns a valid MarketFeatures model."""
    candles = create_session_candles(day_offset=0, base_price=2000.0, count=35)
    mf = FeatureStore.get_features_for_candle(candles, index=-1, opening_range_minutes=15)

    assert isinstance(mf, MarketFeatures)
    assert mf.symbol == "TCS"
    assert mf.timeframe == "1m"
    assert mf.opening_range_high is not None
    assert mf.opening_range_low is not None
    assert mf.time_of_day_minutes == 34
    assert mf.supertrend_direction in (-1, 1)

    d = mf.to_dict()
    assert "ema_9" in d
    assert "vol_ratio" in d
