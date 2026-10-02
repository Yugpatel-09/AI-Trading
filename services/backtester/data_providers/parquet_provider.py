"""
TradeForge Apache Parquet Historical Market Data Provider.
High-throughput columnar market data loader.
"""

from datetime import date
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd
from tradeforge_shared.schemas import Candle

from services.backtester.data_providers.base import DataProvider
from services.engine.data_feed.resampler import to_ist


class ParquetDataProvider(DataProvider):
    """
    Loads historical market candles from Apache Parquet files.
    Default directory: `data/historical/`
    """

    def __init__(self, data_directory: Union[str, Path] = "data/historical"):
        self.data_directory = Path(data_directory)

    @property
    def provider_name(self) -> str:
        return "PARQUET_FILE_PROVIDER"

    def load_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> List[Candle]:
        if file_path:
            target_file = Path(file_path)
        else:
            target_file = self.data_directory / f"{symbol}_{timeframe}.parquet"
            if not target_file.exists():
                target_file = self.data_directory / f"{symbol}.parquet"

        if not target_file.exists():
            raise FileNotFoundError(
                f"Historical Parquet data file for {symbol} ({timeframe}) not found at '{target_file}'."
            )

        df = pd.read_parquet(target_file)
        if df.empty:
            return []

        df.columns = [str(c).strip().lower() for c in df.columns]

        ts_col = None
        for col in ["timestamp", "date", "datetime", "time"]:
            if col in df.columns:
                ts_col = col
                break

        if not ts_col:
            raise ValueError(
                f"Parquet dataset in {target_file} is missing timestamp column. Found: {list(df.columns)}"
            )

        df["parsed_timestamp"] = pd.to_datetime(df[ts_col])
        df.sort_values("parsed_timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        candles: List[Candle] = []
        for _, row in df.iterrows():
            ts = to_ist(row["parsed_timestamp"].to_pydatetime())
            c_date = ts.date()

            if start_date and c_date < start_date:
                continue
            if end_date and c_date > end_date:
                continue

            open_p = float(row["open"])
            high_p = float(row["high"])
            low_p = float(row["low"])
            close_p = float(row["close"])
            vol = int(row.get("volume", 0))
            vwap_val = float(row["vwap"]) if "vwap" in row and not pd.isna(row["vwap"]) else None

            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=round(open_p, 2),
                    high=round(high_p, 2),
                    low=round(low_p, 2),
                    close=round(close_p, 2),
                    volume=vol,
                    vwap=round(vwap_val, 2) if vwap_val is not None else None,
                )
            )

        return candles
