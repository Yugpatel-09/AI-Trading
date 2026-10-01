from typing import List

import pandas as pd
from tradeforge_shared.schemas import Candle


class TechnicalIndicators:
    """
    High-performance feature store & indicator calculator for 1m, 5m, and 10m candles.
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
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        cum_volume = df["volume"].cumsum()
        cum_pv = (typical_price * df["volume"]).cumsum()
        return cum_pv / (cum_volume + 1e-9)

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
        return df
