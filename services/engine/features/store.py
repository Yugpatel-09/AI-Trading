"""
TradeForge Unified Shared Feature Store.
Rule 5: The same feature store code runs identically in backtest, paper, and live.

Computes the core institutional feature pack:
- EMA 9 and EMA 21
- Wilder-smoothed RSI (14)
- Wilder-smoothed ATR (14)
- Average Directional Index (ADX 14) with +DI and -DI
- Supertrend (7, 3.0) with dynamic ratchet and direction (+1/-1)
- Daily-resetting VWAP (resets at 09:15 IST open)
- Volume ratio (volume / SMA(volume, 20))
- Opening Range (high & low for the first N minutes of the session, 09:15-09:30 or 09:35)
- Spread (points and percentage)
- Time-of-day (minutes elapsed since 09:15 IST open)
- Gap size (today's open vs yesterday's close in points and percentage)
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from tradeforge_shared.schemas import Candle

from services.engine.data_feed.resampler import to_ist
from services.engine.features.indicators import TechnicalIndicators

IST = timezone(timedelta(hours=5, minutes=30))


class MarketFeatures(BaseModel):
    """Structured representation of all computed features for a candle."""
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    daily_open: float
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    rsi: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_direction: int = 1
    vol_ratio: float = 1.0
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    spread_points: float = 0.0
    spread_pct: float = 0.0
    time_of_day_minutes: int = 0
    gap_points: float = 0.0
    gap_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class FeatureStore:
    """
    Unified High-Performance Feature Store for TradeForge.
    Enforces identical feature computation across Backtest, Paper, and Live modes.
    """

    @classmethod
    def compute_features_df(
        cls,
        candles: List[Candle],
        opening_range_minutes: int = 15,
    ) -> pd.DataFrame:
        """
        Compute full feature dataset as a pandas DataFrame.
        """
        if not candles:
            return pd.DataFrame()

        df = TechnicalIndicators.candles_to_dataframe(candles)
        n = len(df)
        if n == 0:
            return df

        # 1. Moving Averages
        df["ema_9"] = TechnicalIndicators.calculate_ema(df["close"], 9)
        df["ema_21"] = TechnicalIndicators.calculate_ema(df["close"], 21)

        # 2. Oscillators & Volatility (Wilder-smoothed)
        df["rsi"] = TechnicalIndicators.calculate_rsi(df["close"], 14)
        df["atr"] = TechnicalIndicators.calculate_atr(df, 14)

        # 3. Directional Index (ADX)
        adx_df = TechnicalIndicators.calculate_adx(df, 14)
        df["adx"] = adx_df["adx"]
        df["plus_di"] = adx_df["plus_di"]
        df["minus_di"] = adx_df["minus_di"]

        # 4. Supertrend (period 7, multiplier 3.0)
        st_df = TechnicalIndicators.calculate_supertrend(df, period=7, multiplier=3.0)
        df["supertrend"] = st_df["supertrend"]
        df["supertrend_direction"] = st_df["direction"]

        # 5. VWAP (Daily Session Reset)
        df["vwap"] = TechnicalIndicators.calculate_vwap(df)

        # 6. Volume Ratio
        vol_sma = df["volume"].rolling(20, min_periods=1).mean()
        df["vol_ratio"] = df["volume"] / (vol_sma + 1e-9)

        # 7. Spread (High - Low)
        df["spread_points"] = (df["high"] - df["low"]).round(2)
        df["spread_pct"] = ((df["spread_points"] / (df["close"] + 1e-9)) * 100.0).round(4)

        # Convert timestamps to IST
        ts_ist = [to_ist(ts) for ts in df["timestamp"]]
        df["timestamp_ist"] = ts_ist
        df["date_ist"] = [t.date() for t in ts_ist]

        # 8. Time of Day (minutes since 09:15 IST)
        tod_minutes = []
        for t in ts_ist:
            open_dt = t.replace(hour=9, minute=15, second=0, microsecond=0)
            tod_minutes.append(int((t - open_dt).total_seconds() // 60))
        df["time_of_day_minutes"] = tod_minutes

        # 9. Opening Range and Daily Open (Computed per trading session date)
        or_high_col = np.full(n, np.nan, dtype=float)
        or_low_col = np.full(n, np.nan, dtype=float)
        daily_open_col = np.full(n, np.nan, dtype=float)

        # 10. Gap Size (Today Open vs Yesterday Close)
        gap_pts_col = np.zeros(n, dtype=float)
        gap_pct_col = np.zeros(n, dtype=float)

        unique_dates = list(dict.fromkeys(df["date_ist"]))
        prev_day_close: Optional[float] = None

        for d in unique_dates:
            day_mask = (df["date_ist"] == d)
            day_indices = df.index[day_mask].tolist()
            if not day_indices:
                continue

            # First candle of the session defines daily open
            first_idx = day_indices[0]
            today_open = float(df.loc[first_idx, "open"])
            daily_open_col[day_indices] = today_open

            # Compute gap relative to yesterday's last close
            if prev_day_close is not None and prev_day_close > 0:
                gap_pts = round(today_open - prev_day_close, 2)
                gap_pct = round((gap_pts / prev_day_close) * 100.0, 4)
                gap_pts_col[day_indices] = gap_pts
                gap_pct_col[day_indices] = gap_pct

            # Update prev_day_close with today's last candle close
            last_idx = day_indices[-1]
            prev_day_close = float(df.loc[last_idx, "close"])

            # Compute Opening Range for session d: [09:15, 09:15 + opening_range_minutes)
            open_dt = ts_ist[first_idx].replace(hour=9, minute=15, second=0, microsecond=0)
            or_cutoff = open_dt + timedelta(minutes=opening_range_minutes)

            or_candles_mask = day_mask & (df["timestamp_ist"] < or_cutoff)
            if or_candles_mask.any():
                day_or_high = float(df.loc[or_candles_mask, "high"].max())
                day_or_low = float(df.loc[or_candles_mask, "low"].min())

                # Opening range is active only for candles at or after the cutoff
                active_mask = day_mask & (df["timestamp_ist"] >= or_cutoff)
                active_indices = df.index[active_mask].tolist()
                or_high_col[active_indices] = day_or_high
                or_low_col[active_indices] = day_or_low

        df["daily_open"] = daily_open_col
        df["opening_range_high"] = or_high_col
        df["opening_range_low"] = or_low_col
        df["gap_points"] = gap_pts_col
        df["gap_pct"] = gap_pct_col

        return df

    @classmethod
    def get_features_for_candle(
        cls,
        candles: List[Candle],
        index: int = -1,
        opening_range_minutes: int = 15,
    ) -> MarketFeatures:
        """
        Extract strongly typed MarketFeatures for a specific candle index (defaults to latest).
        """
        if not candles:
            raise ValueError("Candles list cannot be empty")

        df = cls.compute_features_df(candles, opening_range_minutes=opening_range_minutes)
        row = df.iloc[index]
        c = candles[index]

        or_h = None if np.isnan(row["opening_range_high"]) else float(row["opening_range_high"])
        or_l = None if np.isnan(row["opening_range_low"]) else float(row["opening_range_low"])

        return MarketFeatures(
            timestamp=c.timestamp,
            symbol=c.symbol,
            timeframe=c.timeframe,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            vwap=float(row["vwap"]) if not np.isnan(row["vwap"]) else (c.vwap or c.close),
            daily_open=float(row["daily_open"]) if not np.isnan(row["daily_open"]) else c.open,
            ema_9=None if np.isnan(row["ema_9"]) else float(row["ema_9"]),
            ema_21=None if np.isnan(row["ema_21"]) else float(row["ema_21"]),
            rsi=None if np.isnan(row["rsi"]) else float(row["rsi"]),
            atr=None if np.isnan(row["atr"]) else float(row["atr"]),
            adx=None if np.isnan(row["adx"]) else float(row["adx"]),
            plus_di=None if np.isnan(row["plus_di"]) else float(row["plus_di"]),
            minus_di=None if np.isnan(row["minus_di"]) else float(row["minus_di"]),
            supertrend=None if np.isnan(row["supertrend"]) else float(row["supertrend"]),
            supertrend_direction=int(row["supertrend_direction"]) if not np.isnan(row["supertrend_direction"]) else 1,
            vol_ratio=float(row["vol_ratio"]) if not np.isnan(row["vol_ratio"]) else 1.0,
            opening_range_high=or_h,
            opening_range_low=or_l,
            spread_points=float(row["spread_points"]),
            spread_pct=float(row["spread_pct"]),
            time_of_day_minutes=int(row["time_of_day_minutes"]),
            gap_points=float(row["gap_points"]),
            gap_pct=float(row["gap_pct"]),
        )

    @classmethod
    def calculate_opening_range(
        cls,
        candles: List[Candle],
        target_date: Optional[date] = None,
        window_minutes: int = 15,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate opening range high and low for a given date over window_minutes.
        Returns (high, low) or (None, None) if opening window is not yet complete.
        """
        if not candles:
            return None, None

        if target_date is None:
            target_date = to_ist(candles[-1].timestamp).date()

        day_candles = [c for c in candles if to_ist(c.timestamp).date() == target_date]
        if not day_candles:
            return None, None

        first_c = day_candles[0]
        first_ist = to_ist(first_c.timestamp)
        open_dt = first_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        cutoff_dt = open_dt + timedelta(minutes=window_minutes)

        window_candles = [c for c in day_candles if to_ist(c.timestamp) < cutoff_dt]
        last_ist = to_ist(day_candles[-1].timestamp)

        # Range is only defined if we have reached or passed the cutoff time
        if last_ist < cutoff_dt or not window_candles:
            return None, None

        or_high = round(max(c.high for c in window_candles), 2)
        or_low = round(min(c.low for c in window_candles), 2)
        return or_high, or_low

    @classmethod
    def calculate_gap(
        cls,
        candles: List[Candle],
        target_date: Optional[date] = None,
    ) -> Tuple[float, float]:
        """
        Calculate overnight gap: today's open vs yesterday's close.
        Returns (gap_points, gap_pct).
        """
        if not candles:
            return 0.0, 0.0

        if target_date is None:
            target_date = to_ist(candles[-1].timestamp).date()

        # Group by IST date
        by_date: Dict[date, List[Candle]] = {}
        for c in candles:
            by_date.setdefault(to_ist(c.timestamp).date(), []).append(c)

        dates = sorted(by_date.keys())
        if target_date not in dates:
            return 0.0, 0.0

        idx = dates.index(target_date)
        if idx == 0:
            return 0.0, 0.0

        prev_date = dates[idx - 1]
        yesterday_candles = by_date[prev_date]
        today_candles = by_date[target_date]

        yesterday_close = yesterday_candles[-1].close
        today_open = today_candles[0].open

        gap_points = round(today_open - yesterday_close, 2)
        gap_pct = round((gap_points / yesterday_close) * 100.0, 4)
        return gap_points, gap_pct
