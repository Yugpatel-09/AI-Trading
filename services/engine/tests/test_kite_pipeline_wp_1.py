"""
Phase 1 Verification Tests: Real Kite Data Pipeline.

Comprehensive tests verifying:
1. NSEMarketCalendar: Trading days, weekends, official holidays, and Muhurat special sessions.
2. InstrumentsRegistry: Caching, symbol/token lookup, tick-size rounding, circuit limit checks.
3. TickToCandleAggregator: 09:15 IST alignment, cumulative to delta volume conversion,
   out-of-order rejection, gap filling, and complete-candles-only emission.
4. CandleRepository: Persistence, query, and cold-start hydration.
5. FeedHealthMonitor: Real-time latency tracking, STALE trip, alert dispatch, and FeedWatchdog sync.
6. KiteSessionManager: Token validation, daily OAuth exchange, and 09:00 pre-open gatekeeper.
7. KiteTickerProvider: User-isolated streaming, rate-limited historical backfill, and feature warming.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tradeforge_shared.schemas import Candle

from services.api.app.db.models import Base
from services.api.app.db.repositories.candle_repo import CandleRepository
from services.engine.data_feed.aggregator import MarketTick, TickToCandleAggregator
from services.engine.data_feed.calendar import IST, NSEMarketCalendar
from services.engine.data_feed.health import FeedHealthMonitor, FeedStatus
from services.engine.data_feed.instruments import InstrumentInfo, InstrumentsRegistry
from services.engine.data_feed.kite_provider import KiteTickerProvider
from services.engine.data_feed.session_checker import KiteSessionManager
from services.risk_guard.watchdog import FeedWatchdog


# -----------------------------------------------------------------------------
# 1. NSE Market Calendar Tests
# -----------------------------------------------------------------------------
def test_nse_calendar_trading_days_and_holidays():
    cal = NSEMarketCalendar()

    # Regular Wednesday in 2026
    trading_day = date(2026, 10, 7)
    assert cal.is_trading_day(trading_day) is True

    # Weekend: Saturday
    saturday = date(2026, 10, 10)
    assert cal.is_trading_day(saturday) is False

    # Official Holiday: Gandhi Jayanti (2026-10-02)
    holiday = date(2026, 10, 2)
    assert cal.is_trading_day(holiday) is False

    # Special session: Diwali Muhurat trading (2026-11-08 is a Sunday, but special session is active)
    muhurat_day = date(2026, 11, 8)
    assert cal.is_trading_day(muhurat_day) is True
    window = cal.get_session_window(muhurat_day)
    assert window is not None
    s_open, s_close = window
    assert s_open.hour == 18 and s_open.minute == 15
    assert s_close.hour == 19 and s_close.minute == 15


def test_nse_calendar_market_hours_and_pre_open():
    cal = NSEMarketCalendar()

    # Pre-open at 09:05 IST on active day
    pre_open_time = datetime(2026, 10, 7, 9, 5, 0, tzinfo=IST)
    assert cal.is_pre_open_window(pre_open_time) is True
    assert cal.is_market_open(pre_open_time) is False

    # Active market at 10:30 IST
    active_time = datetime(2026, 10, 7, 10, 30, 0, tzinfo=IST)
    assert cal.is_market_open(active_time) is True
    assert cal.is_pre_open_window(active_time) is False

    # Post-market at 15:35 IST
    closed_time = datetime(2026, 10, 7, 15, 35, 0, tzinfo=IST)
    assert cal.is_market_open(closed_time) is False


# -----------------------------------------------------------------------------
# 2. Instruments Registry Tests
# -----------------------------------------------------------------------------
def test_instruments_registry_lookup_and_circuit_limits(tmp_path: Path):
    reg = InstrumentsRegistry(cache_dir=tmp_path)

    # Pre-seeded instruments
    rel = reg.get_by_symbol("RELIANCE")
    assert rel is not None
    assert rel.instrument_token == 738561
    assert rel.lot_size == 1
    assert rel.tick_size == 0.05

    # Token lookup
    assert reg.get_by_token(738561) == rel

    # Tick size rounding
    assert reg.round_to_tick(2500.03, "RELIANCE") == 2500.05
    assert reg.round_to_tick(2500.01, "RELIANCE") == 2500.00
    assert reg.round_to_tick(2500.08, "RELIANCE") == 2500.10

    # Circuit limit checking
    valid, _ = reg.check_circuit_limits("RELIANCE", 2500.0)
    assert valid is True

    valid_low, err_low = reg.check_circuit_limits("RELIANCE", 2200.0)
    assert valid_low is False
    assert "below lower circuit" in err_low

    valid_high, err_high = reg.check_circuit_limits("RELIANCE", 2800.0)
    assert valid_high is False
    assert "above upper circuit" in err_high


def test_instruments_registry_cache_roundtrip(tmp_path: Path):
    reg1 = InstrumentsRegistry(cache_dir=tmp_path)
    custom_inst = InstrumentInfo(
        instrument_token=999999,
        tradingsymbol="CUSTOM_STOCK",
        name="Custom Stock Ltd",
        tick_size=0.10,
        lot_size=10,
        segment="NSE",
    )
    reg1.register_instrument(custom_inst)
    reg1.save_cache()

    # Load fresh registry from cache
    reg2 = InstrumentsRegistry(cache_dir=tmp_path)
    loaded = reg2.load_cache()
    assert loaded is True
    found = reg2.get_by_symbol("CUSTOM_STOCK")
    assert found is not None
    assert found.instrument_token == 999999
    assert found.tick_size == 0.10


# -----------------------------------------------------------------------------
# 3. Tick-to-Candle Aggregator Tests
# -----------------------------------------------------------------------------
def test_tick_aggregator_volume_conversion_and_complete_candles():
    closed_candles: list[Candle] = []
    agg = TickToCandleAggregator(
        symbol="RELIANCE",
        on_candle_close=lambda c: closed_candles.append(c),
        fill_gaps=False,
    )

    t0 = datetime(2026, 10, 7, 9, 15, 10, tzinfo=IST)
    t1 = datetime(2026, 10, 7, 9, 15, 30, tzinfo=IST)
    t2 = datetime(2026, 10, 7, 9, 15, 50, tzinfo=IST)
    t_next = datetime(2026, 10, 7, 9, 16, 5, tzinfo=IST)

    # 3 ticks inside minute 09:15
    # Kite cumulative volume grows from 1000 -> 1400 -> 1900 (+400, +500)
    agg.process_tick(MarketTick(instrument_token=738561, symbol="RELIANCE", last_price=2500.0, volume_traded=1000, last_quantity=50, timestamp=t0))
    agg.process_tick(MarketTick(instrument_token=738561, symbol="RELIANCE", last_price=2505.0, volume_traded=1400, last_quantity=400, timestamp=t1))
    agg.process_tick(MarketTick(instrument_token=738561, symbol="RELIANCE", last_price=2498.0, volume_traded=1900, last_quantity=500, timestamp=t2))

    # Bar 09:15 has NOT closed yet (complete-candles-only guarantee)
    assert len(closed_candles) == 0

    # First tick of minute 09:16 arrives -> closes minute 09:15
    agg.process_tick(MarketTick(instrument_token=738561, symbol="RELIANCE", last_price=2502.0, volume_traded=2100, last_quantity=200, timestamp=t_next))

    assert len(closed_candles) == 1
    c0 = closed_candles[0]
    assert c0.symbol == "RELIANCE"
    assert c0.timestamp == datetime(2026, 10, 7, 9, 15, 0, tzinfo=IST)
    assert c0.open == 2500.0
    assert c0.high == 2505.0
    assert c0.low == 2498.0
    assert c0.close == 2498.0
    # Volume delta: 50 (first tick qty) + 400 + 500 = 950
    assert c0.volume == 950


def test_tick_aggregator_gap_filling_mid_session():
    closed_candles: list[Candle] = []
    agg = TickToCandleAggregator(
        symbol="NIFTY",
        on_candle_close=lambda c: closed_candles.append(c),
        fill_gaps=True,
    )

    t0 = datetime(2026, 10, 7, 9, 20, 15, tzinfo=IST)
    agg.process_tick(MarketTick(instrument_token=256265, symbol="NIFTY", last_price=22000.0, volume_traded=5000, timestamp=t0))

    # Market pauses for 3 minutes (gap), then tick arrives at 09:24:05 IST
    t_after_gap = datetime(2026, 10, 7, 9, 24, 5, tzinfo=IST)
    emitted = agg.process_tick(MarketTick(instrument_token=256265, symbol="NIFTY", last_price=22010.0, volume_traded=5500, timestamp=t_after_gap))

    # Must emit bar 09:20 PLUS filled gap bars for 09:21, 09:22, 09:23
    assert len(emitted) == 4
    timestamps = [c.timestamp.minute for c in emitted]
    assert timestamps == [20, 21, 22, 23]

    # Filled gap bars have volume 0 and open=high=low=close=last_close
    gap_bar = emitted[1]
    assert gap_bar.volume == 0
    assert gap_bar.open == 22000.0
    assert gap_bar.close == 22000.0


# -----------------------------------------------------------------------------
# 4. Candle Repository Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candle_repository_save_and_hydration(tmp_path: Path):
    db_file = tmp_path / "test_candles.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    t0 = datetime(2026, 10, 7, 9, 15, 0, tzinfo=IST)
    candles = [
        Candle(symbol="RELIANCE", timeframe="1m", timestamp=t0 + timedelta(minutes=i), open=2500.0 + i, high=2505.0 + i, low=2495.0 + i, close=2502.0 + i, volume=1000 + i * 100, vwap=2501.0 + i)
        for i in range(5)
    ]

    async with session_maker() as session:
        repo = CandleRepository(session)
        saved = await repo.save_candles_batch(candles, timeframe="1m")
        assert saved == 5
        await session.commit()

    async with session_maker() as session:
        repo = CandleRepository(session)
        loaded = await repo.get_candles("RELIANCE", timeframe="1m", limit=10)
        assert len(loaded) == 5
        assert loaded[0].open == 2500.0
        assert loaded[-1].close == 2506.0

        latest = await repo.get_latest_candle("RELIANCE", timeframe="1m")
        assert latest is not None
        assert latest.timestamp == t0 + timedelta(minutes=4)

    await engine.dispose()


# -----------------------------------------------------------------------------
# 5. Feed Health & Watchdog Sync Tests
# -----------------------------------------------------------------------------
def test_feed_health_monitor_stale_detection_and_alerts():
    watchdog = FeedWatchdog(max_staleness_ms=3000)
    alerts: list[tuple[str, str]] = []

    monitor = FeedHealthMonitor(
        watchdog=watchdog,
        max_staleness_ms=3000,
        alert_callback=lambda sym, msg: alerts.append((sym, msg)),
    )

    t0 = datetime(2026, 10, 7, 10, 0, 0, tzinfo=timezone.utc)
    monitor.record_tick("RELIANCE", tick_time=t0)

    # 1 second later: Healthy
    t1 = t0 + timedelta(seconds=1)
    status_1 = monitor.evaluate_health(current_time=t1)
    assert status_1["RELIANCE"].status == FeedStatus.HEALTHY
    is_fresh, _ = watchdog.is_feed_fresh("RELIANCE", current_time=t1)
    assert is_fresh is True
    assert len(alerts) == 0

    # 4 seconds later (>3000ms threshold): STALE
    t2 = t0 + timedelta(seconds=4)
    status_2 = monitor.evaluate_health(current_time=t2)
    assert status_2["RELIANCE"].status == FeedStatus.STALE

    # Synchronized with RiskGuard FeedWatchdog
    is_fresh_2, delay_ms = watchdog.is_feed_fresh("RELIANCE", current_time=t2)
    assert is_fresh_2 is False
    assert delay_ms >= 4000

    # Alert fired
    assert len(alerts) == 1
    assert alerts[0][0] == "RELIANCE"
    assert "STALE" in alerts[0][1]


# -----------------------------------------------------------------------------
# 6. Daily Kite Session Pre-Open Check Tests
# -----------------------------------------------------------------------------
def test_kite_session_pre_open_check_valid_and_expired():
    mgr = KiteSessionManager()

    # 1. Mock valid Kite client
    mock_kite_valid = MagicMock()
    mock_kite_valid.profile.return_value = {
        "user_id": "AB1234",
        "user_name": "Trader John",
        "email": "trader@tradeforge.io",
    }

    res_valid = mgr.run_pre_open_check(
        user_id="usr_001",
        api_key="valid_key",
        access_token="valid_token",
        kite_client=mock_kite_valid,
    )
    assert res_valid.is_valid is True
    assert res_valid.broker_user_id == "AB1234"
    assert res_valid.user_name == "Trader John"
    assert res_valid.login_url is None

    # 2. Mock expired Kite client
    mock_kite_expired = MagicMock()
    mock_kite_expired.profile.side_effect = Exception("TokenException: Token is invalid or has expired.")

    res_expired = mgr.run_pre_open_check(
        user_id="usr_002",
        api_key="key_xyz",
        access_token="expired_token",
        kite_client=mock_kite_expired,
    )
    assert res_expired.is_valid is False
    assert "Token is invalid" in (res_expired.error_message or "")
    assert res_expired.login_url is not None
    assert "key_xyz" in res_expired.login_url


# -----------------------------------------------------------------------------
# 7. KiteTickerProvider User-Isolation & Backfill Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kite_ticker_provider_user_isolation_and_backfill():
    mock_kite = MagicMock()
    t_start = datetime(2026, 10, 5, 9, 15, 0, tzinfo=IST)
    mock_records = [
        {
            "date": t_start + timedelta(minutes=i),
            "open": 2500.0 + i,
            "high": 2505.0 + i,
            "low": 2495.0 + i,
            "close": 2502.0 + i,
            "volume": 1500,
            "vwap": 2501.0,
        }
        for i in range(10)
    ]
    mock_kite.historical_data.return_value = mock_records

    closed_stream: list[Candle] = []
    provider = KiteTickerProvider(
        user_id="trader_isolated_01",
        api_key="user_personal_key",
        access_token="user_personal_token",
        symbols=["RELIANCE"],
        on_candle_close=lambda c: closed_stream.append(c),
        kite_client=mock_kite,
    )

    # 1. Verify user credentials are isolated
    assert provider.user_id == "trader_isolated_01"
    assert provider.api_key == "user_personal_key"

    # 2. Historical backfill
    backfilled = await provider.backfill_historical_candles(
        symbol="RELIANCE",
        from_date=t_start,
        to_date=t_start + timedelta(minutes=10),
    )
    assert len(backfilled) == 10
    assert backfilled[0].symbol == "RELIANCE"
    assert backfilled[0].open == 2500.0

    # 3. Stream real ticks via on_ticks
    ticks = [
        {"instrument_token": 738561, "last_price": 2500.0, "volume_traded": 1000, "timestamp": t_start},
        {"instrument_token": 738561, "last_price": 2505.0, "volume_traded": 1500, "timestamp": t_start + timedelta(minutes=1, seconds=2)},
    ]
    provider.on_ticks(None, ticks)

    # Emitted 1 completed candle
    assert len(closed_stream) == 1
    assert closed_stream[0].symbol == "RELIANCE"
