"""
TradeForge Broker Historical Market Data Provider.
Fetches real historical candles directly through broker gateway (e.g. Zerodha Kite Connect).
Rule: Never fake broker data or return fabricated historical bars.
"""

from datetime import date, datetime
from typing import Any, List, Optional

from tradeforge_shared.schemas import Candle

from services.backtester.data_providers.base import DataProvider
from services.engine.data_feed.resampler import to_ist


class BrokerHistoricalDataProvider(DataProvider):
    """
    Fetches genuine historical candles from connected broker API.
    Refuses execution without active broker authentication.
    """

    def __init__(self, broker_client: Optional[Any] = None):
        self.broker_client = broker_client

    @property
    def provider_name(self) -> str:
        return "BROKER_HISTORICAL_API"

    def load_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        instrument_token: Optional[int] = None,
    ) -> List[Candle]:
        if not self.broker_client:
            raise PermissionError(
                "BrokerHistoricalDataProvider requires an active broker client session. "
                "No live broker credentials or access tokens found."
            )

        if not instrument_token:
            raise ValueError(f"Instrument token required for broker historical fetch on {symbol}.")

        from_dt = datetime.combine(start_date or date.today(), datetime.min.time())
        to_dt = datetime.combine(end_date or date.today(), datetime.max.time())

        # Standard Kite Connect historical_data contract
        raw_bars = self.broker_client.historical_data(
            instrument_token=instrument_token,
            from_date=from_dt,
            to_date=to_dt,
            interval="minute" if timeframe == "1m" else timeframe,
        )

        candles: List[Candle] = []
        for b in raw_bars:
            ts = to_ist(b["date"] if isinstance(b["date"], datetime) else datetime.fromisoformat(b["date"]))
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=round(float(b["open"]), 2),
                    high=round(float(b["high"]), 2),
                    low=round(float(b["low"]), 2),
                    close=round(float(b["close"]), 2),
                    volume=int(b["volume"]),
                    vwap=round(float(b.get("vwap", b["close"])), 2),
                )
            )

        return candles
