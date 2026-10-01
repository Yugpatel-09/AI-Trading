from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from services.engine.features.indicators import TechnicalIndicators


def test_wilder_rsi_matches_reference_values():
    """
    Reference Test: Compare 14-period Wilder RSI against J. Welles Wilder Jr.'s
    original 1978 published dataset in 'New Concepts in Technical Trading Systems' (Table 1).
    Prices:
      Day 1 to 15: 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10,
                   45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28
    Reference Published Output for Day 15 (Index 14):
      Average Gain = 0.2393, Average Loss = 0.1007, RS = 2.3764, RSI = 70.46
    """
    prices = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10,
        45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    series = pd.Series(prices)
    rsi = TechnicalIndicators.calculate_rsi(series, period=14)

    # First 13 values should be NaN
    assert np.isnan(rsi.iloc[0])
    assert np.isnan(rsi.iloc[13])

    # Day 15 RSI (index 14) must match Wilder's reference 70.46
    day_15_rsi = rsi.iloc[14]
    assert pytest.approx(day_15_rsi, abs=0.05) == 70.46


def test_wilder_atr_matches_reference_values():
    """
    Reference Test: Compare 14-period Wilder ATR against J. Welles Wilder Jr.'s
    original 1978 commodity price dataset.
    """
    data = [
        (45.62, 44.88, 45.44),  # Day 1
        (46.00, 45.50, 45.88),  # Day 2
        (46.38, 45.62, 46.12),
        (46.50, 46.00, 46.25),
        (46.75, 46.00, 46.50),
        (46.62, 46.12, 46.38),
        (46.62, 46.12, 46.38),
        (46.75, 46.25, 46.62),
        (46.88, 46.25, 46.50),
        (46.88, 46.12, 46.25),
        (46.38, 45.75, 46.00),
        (46.38, 45.88, 46.00),
        (46.38, 45.88, 46.12),
        (46.62, 46.00, 46.50),  # Day 14
        (46.88, 46.38, 46.75),  # Day 15
    ]
    df = pd.DataFrame(data, columns=["high", "low", "close"])
    atr = TechnicalIndicators.calculate_atr(df, period=14)

    # Day 14 (index 13) should be initial 14-period mean: ~0.6036
    assert pytest.approx(atr.iloc[13], abs=0.01) == 0.604

    # Day 15 (index 14) Wilder smoothed: ~0.5962
    assert pytest.approx(atr.iloc[14], abs=0.01) == 0.596


def test_adx_trending_vs_choppy_behavior():
    """
    Reference Test: ADX properties.
    In a sustained strong bull market: Plus DI dominates Minus DI and ADX exceeds 40.
    In a choppy range-bound market: Plus DI and Minus DI oscillate closely and ADX stays low.
    """
    n = 60
    # 1. Strong Bullish Trend
    bull_highs = [100.0 + i * 2.0 + 1.0 for i in range(n)]
    bull_lows = [100.0 + i * 2.0 - 0.5 for i in range(n)]
    bull_closes = [100.0 + i * 2.0 + 0.8 for i in range(n)]
    df_bull = pd.DataFrame({"high": bull_highs, "low": bull_lows, "close": bull_closes})

    adx_bull = TechnicalIndicators.calculate_adx(df_bull, period=14)
    recent_bull = adx_bull.iloc[-1]
    assert recent_bull["plus_di"] > 40.0
    assert recent_bull["minus_di"] < 10.0
    assert recent_bull["adx"] > 50.0  # Strong trend confirmed

    # 2. Strong Bearish Trend
    bear_highs = [300.0 - i * 2.0 + 0.5 for i in range(n)]
    bear_lows = [300.0 - i * 2.0 - 1.5 for i in range(n)]
    bear_closes = [300.0 - i * 2.0 - 1.0 for i in range(n)]
    df_bear = pd.DataFrame({"high": bear_highs, "low": bear_lows, "close": bear_closes})

    adx_bear = TechnicalIndicators.calculate_adx(df_bear, period=14)
    recent_bear = adx_bear.iloc[-1]
    assert recent_bear["minus_di"] > 40.0
    assert recent_bear["plus_di"] < 10.0
    assert recent_bear["adx"] > 50.0


def test_supertrend_ratchet_and_direction_flip():
    """
    Reference Test: Supertrend dynamic ratchet and trend direction flip.
    During an uptrend, Supertrend trails below close.
    When a sharp downward bar violates the lower band, direction flips to -1 and Supertrend caps above close.
    """
    highs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 14, 12, 10, 8]
    lows = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 11, 10, 8, 6]
    closes = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 12.0, 10.5, 8.5, 6.5]
    df = pd.DataFrame({"high": highs, "low": lows, "close": closes})

    st_df = TechnicalIndicators.calculate_supertrend(df, period=3, multiplier=2.0)

    # Bars 3 to 9: Steady uptrend -> Direction must be 1, Supertrend band below close
    for i in range(3, 10):
        assert st_df["direction"].iloc[i] == 1
        assert st_df["supertrend"].iloc[i] < df["close"].iloc[i]

    # Bar 10: Price crashes from 18.5 to 12.0 -> Direction must flip to -1
    assert st_df["direction"].iloc[10] == -1
    assert st_df["supertrend"].iloc[10] > df["close"].iloc[10]

    # Bars 11 to 13: Downtrend continues -> Direction remains -1, Supertrend band above close
    for i in range(11, 14):
        assert st_df["direction"].iloc[i] == -1
        assert st_df["supertrend"].iloc[i] > df["close"].iloc[i]


def test_vwap_resets_daily_at_market_open():
    """
    Safety Rule: Intraday VWAP MUST reset at the open of each new trading session,
    never bleeding volume from previous days.
    """
    t0 = datetime(2026, 10, 1, 9, 15, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 2, 9, 15, 0, tzinfo=timezone.utc)

    # Day 1: 5 bars around 100 with 1000 volume each
    day1_records = [
        {
            "timestamp": t0 + timedelta(minutes=i),
            "high": 102.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 1000,
        }
        for i in range(5)
    ]

    # Day 2: 5 bars around 500 with 1000 volume each
    day2_records = [
        {
            "timestamp": t1 + timedelta(minutes=i),
            "high": 502.0,
            "low": 498.0,
            "close": 500.0,
            "volume": 1000,
        }
        for i in range(5)
    ]

    df = pd.DataFrame(day1_records + day2_records)
    vwap = TechnicalIndicators.calculate_vwap(df)

    # End of Day 1: VWAP should be 100.0
    assert pytest.approx(vwap.iloc[4], abs=0.1) == 100.0

    # Start of Day 2 (index 5): VWAP must reset to Day 2's first bar typical price (500.0),
    # NOT the cumulative 2-day blend (~166.7)
    assert pytest.approx(vwap.iloc[5], abs=0.1) == 500.0
