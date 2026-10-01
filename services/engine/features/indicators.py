from typing import List

import numpy as np
import pandas as pd
from tradeforge_shared.schemas import Candle


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """
    Classic Wilder's smoothing (RMA / Wilder's Exponential Moving Average).
    Used as the standard in RSI, ATR, and ADX calculations.
    Initial value at index (period - 1) is the simple average of the first 'period' values.
    Subsequent values: RMA_t = (RMA_{t-1} * (period - 1) + series_t) / period.
    """
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return pd.Series(out, index=series.index)

    # Initial average
    first_window = vals[:period]
    valid_mask = ~np.isnan(first_window)
    if not np.any(valid_mask):
        return pd.Series(out, index=series.index)

    out[period - 1] = np.nanmean(first_window)
    for i in range(period, n):
        val = vals[i]
        if np.isnan(val):
            out[i] = out[i - 1]
        else:
            out[i] = (out[i - 1] * (period - 1) + val) / period

    return pd.Series(out, index=series.index)


class TechnicalIndicators:
    """
    High-performance feature store & indicator calculator for 1m, 5m, and 10m candles.
    Includes Wilder-smoothed RSI, ATR, ADX, Supertrend, and daily-resetting VWAP.
    """
    @staticmethod
    def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        data = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """
        Wilder-smoothed Relative Strength Index (RSI).
        Matches J. Welles Wilder Jr. (1978) reference implementation.
        """
        if len(series) < period + 1:
            return pd.Series(np.nan, index=series.index)

        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)

        # Smooth using Wilder's smoothing starting from index 1 (after the first diff)
        smoothed_gain = wilder_smooth(gain.iloc[1:], period)
        smoothed_loss = wilder_smooth(loss.iloc[1:], period)

        rs = smoothed_gain / (smoothed_loss + 1e-9)
        rsi_vals = 100.0 - (100.0 / (1.0 + rs))

        # Re-align with original series index (first row NaN)
        result = pd.Series(np.nan, index=series.index)
        result.iloc[1:] = rsi_vals
        return result

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Wilder-smoothed Average True Range (ATR).
        Matches J. Welles Wilder Jr. (1978) reference implementation.
        """
        if len(df) < period:
            return pd.Series(np.nan, index=df.index)

        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # First true range is high[0] - low[0]
        tr.iloc[0] = high.iloc[0] - low.iloc[0]
        return wilder_smooth(tr, period)

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """
        Volume Weighted Average Price (VWAP) with strict daily session reset.
        Reset occurs at each trading day's open (IST or date rollover).
        """
        if df.empty or "volume" not in df.columns or "close" not in df.columns:
            return pd.Series(dtype=float)

        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        pv = typical_price * df["volume"]

        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"])
            dates = ts.dt.date
            cum_volume = df.groupby(dates)["volume"].cumsum()
            cum_pv = pv.groupby(dates).cumsum()
        else:
            cum_volume = df["volume"].cumsum()
            cum_pv = pv.cumsum()

        return cum_pv / (cum_volume + 1e-9)

    @classmethod
    def calculate_adx(cls, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Average Directional Index (ADX) with +DI and -DI using Wilder's smoothing.
        Returns DataFrame with ['adx', 'plus_di', 'minus_di'].
        """
        if len(df) < period * 2:
            nan_series = pd.Series(np.nan, index=df.index)
            return pd.DataFrame({"adx": nan_series, "plus_di": nan_series, "minus_di": nan_series})

        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        # Directional Movement
        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # True Range
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        tr.iloc[0] = high.iloc[0] - low.iloc[0]

        # Wilder smoothing of TR, +DM, -DM
        smoothed_tr = wilder_smooth(tr, period)
        smoothed_plus_dm = wilder_smooth(pd.Series(plus_dm, index=df.index), period)
        smoothed_minus_dm = wilder_smooth(pd.Series(minus_dm, index=df.index), period)

        plus_di = 100.0 * (smoothed_plus_dm / (smoothed_tr + 1e-9))
        minus_di = 100.0 * (smoothed_minus_dm / (smoothed_tr + 1e-9))

        # Directional Index (DX)
        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di
        dx = 100.0 * (di_diff / (di_sum + 1e-9))

        # ADX is Wilder-smoothed DX
        adx = wilder_smooth(dx, period)

        return pd.DataFrame({
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
        }, index=df.index)

    @classmethod
    def calculate_supertrend(cls, df: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> pd.DataFrame:
        """
        Supertrend indicator.
        Calculates upper/lower ATR bands with dynamic ratchet and trend direction flip.
        Returns DataFrame with ['supertrend', 'direction'] where direction=1 (bullish) or -1 (bearish).
        """
        n = len(df)
        if n < period:
            nan_series = pd.Series(np.nan, index=df.index)
            return pd.DataFrame({"supertrend": nan_series, "direction": pd.Series(1, index=df.index)})

        atr = cls.calculate_atr(df, period)
        hl2 = (df["high"] + df["low"]) / 2.0
        basic_upper = hl2 + (multiplier * atr)
        basic_lower = hl2 - (multiplier * atr)

        final_upper = np.zeros(n)
        final_lower = np.zeros(n)
        supertrend = np.zeros(n)
        direction = np.ones(n, dtype=int)

        close = df["close"].to_numpy(dtype=float)
        bu = basic_upper.to_numpy(dtype=float)
        bl = basic_lower.to_numpy(dtype=float)

        for i in range(period - 1, n):
            if i == period - 1:
                final_upper[i] = bu[i]
                final_lower[i] = bl[i]
                direction[i] = 1 if close[i] >= final_lower[i] else -1
                supertrend[i] = final_lower[i] if direction[i] == 1 else final_upper[i]
                continue

            # Ratchet upper band down
            if bu[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
                final_upper[i] = bu[i]
            else:
                final_upper[i] = final_upper[i - 1]

            # Ratchet lower band up
            if bl[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
                final_lower[i] = bl[i]
            else:
                final_lower[i] = final_lower[i - 1]

            # Evaluate trend direction
            prev_dir = direction[i - 1]
            if prev_dir == 1:
                if close[i] < final_lower[i]:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
                else:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
            else:
                if close[i] > final_upper[i]:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
                else:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]

        return pd.DataFrame({
            "supertrend": pd.Series(supertrend, index=df.index),
            "direction": pd.Series(direction, index=df.index),
        })

    @classmethod
    def compute_all_features(cls, candles: List[Candle]) -> pd.DataFrame:
        df = cls.candles_to_dataframe(candles)
        if len(df) < 5:
            return df
        df["ema_9"] = cls.calculate_ema(df["close"], 9)
        df["ema_21"] = cls.calculate_ema(df["close"], 21)
        df["rsi"] = cls.calculate_rsi(df["close"], 14)
        df["atr"] = cls.calculate_atr(df, 14)
        df["vwap"] = cls.calculate_vwap(df)
        df["vol_sma"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / (df["vol_sma"] + 1e-9)

        # ADX feature pack
        adx_data = cls.calculate_adx(df, 14)
        df["adx"] = adx_data["adx"]
        df["plus_di"] = adx_data["plus_di"]
        df["minus_di"] = adx_data["minus_di"]

        # Supertrend feature pack (period 7, mult 3.0)
        st_data = cls.calculate_supertrend(df, period=7, multiplier=3.0)
        df["supertrend"] = st_data["supertrend"]
        df["supertrend_direction"] = st_data["direction"]

        return df
