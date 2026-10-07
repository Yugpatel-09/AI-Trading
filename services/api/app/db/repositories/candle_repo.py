"""
Candle Repository for Multi-Timeframe Historical Data Storage.

Supports:
1. High-throughput batch upsert of OHLCV candles (TimescaleDB / SQLite).
2. Fetching recent closed bars for cold-start chart hydration.
3. Fast lookup of latest candle timestamp for gap detection.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_shared.schemas import Candle

from services.api.app.db.models import CandleModel
from services.engine.data_feed.resampler import to_ist


class CandleRepository:
    """Repository for managing persisted market candle feeds."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_candle(self, candle: Candle, timeframe: str = "1m") -> CandleModel:
        """Upsert a single candle bar into the database."""
        sym = candle.symbol.upper().strip()
        ts = candle.timestamp if candle.timestamp.tzinfo else candle.timestamp.replace(tzinfo=timezone.utc)

        stmt = (
            select(CandleModel)
            .where(CandleModel.symbol == sym)
            .where(CandleModel.timeframe == timeframe)
            .where(CandleModel.timestamp == ts)
        )
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()

        if record:
            record.open = candle.open
            record.high = candle.high
            record.low = candle.low
            record.close = candle.close
            record.volume = candle.volume
            record.vwap = candle.vwap
        else:
            record = CandleModel(
                symbol=sym,
                timeframe=timeframe,
                timestamp=ts,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                vwap=candle.vwap,
            )
            self.session.add(record)

        await self.session.flush()
        return record

    async def save_candles_batch(self, candles: List[Candle], timeframe: str = "1m") -> int:
        """Persist a collection of candles efficiently."""
        if not candles:
            return 0
        saved = 0
        for c in candles:
            await self.save_candle(c, timeframe=timeframe)
            saved += 1
        return saved

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 375,
        since: Optional[datetime] = None,
    ) -> List[Candle]:
        """
        Fetch chronological candles for an instrument and timeframe.
        Returns up to `limit` bars in ascending chronological order.
        """
        sym = symbol.upper().strip()
        stmt = (
            select(CandleModel)
            .where(CandleModel.symbol == sym)
            .where(CandleModel.timeframe == timeframe)
        )
        if since:
            stmt = stmt.where(CandleModel.timestamp >= since)

        stmt = stmt.order_by(desc(CandleModel.timestamp)).limit(limit)
        res = await self.session.execute(stmt)
        records = res.scalars().all()

        # Convert back to shared schema in chronological order
        chronological = sorted(records, key=lambda r: r.timestamp)
        return [
            Candle(
                symbol=r.symbol,
                timeframe=r.timeframe,
                timestamp=to_ist(r.timestamp),
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                vwap=r.vwap,
            )
            for r in chronological
        ]

    async def get_latest_candle(self, symbol: str, timeframe: str = "1m") -> Optional[Candle]:
        """Fetch the most recent closed candle bar for an instrument."""
        sym = symbol.upper().strip()
        stmt = (
            select(CandleModel)
            .where(CandleModel.symbol == sym)
            .where(CandleModel.timeframe == timeframe)
            .order_by(desc(CandleModel.timestamp))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        r = res.scalar_one_or_none()
        if not r:
            return None
        return Candle(
            symbol=r.symbol,
            timeframe=r.timeframe,
            timestamp=to_ist(r.timestamp),
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
            vwap=r.vwap,
        )
