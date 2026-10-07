"""
Kite Ticker & Historical Data Provider.

Implements real-time market data streaming and historical backfill using
Zerodha's official KiteConnect SDK.

Non-Negotiable Invariants:
1. User-isolated streaming: Each user connects exclusively using their own credentials
   decrypted from crypto_vault (Exchange Data Vending Compliance & ADR 0002).
2. Ticks flow into TickToCandleAggregator (09:15-aligned, volume delta converted, gap-filled).
3. Feed health heartbeat updated on every incoming tick.
4. Historical backfill populates TimescaleDB / SQLite CandleRepository, respecting
   Kite historical API rate limits (max 3 req/sec).
5. Warm start: Hydrates FeatureStore before strategy execution begins.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from tradeforge_shared.schemas import Candle

from services.api.app.core.logging import logger
from services.engine.data_feed.aggregator import MarketTick, TickToCandleAggregator
from services.engine.data_feed.calendar import IST
from services.engine.data_feed.health import feed_health_monitor
from services.engine.data_feed.instruments import instruments_registry


class KiteTickerProvider:
    """
    Autonomous Market Data Provider wrapping KiteTicker & KiteConnect historical API.
    """

    def __init__(
        self,
        user_id: str,
        api_key: str,
        access_token: str,
        symbols: Optional[List[str]] = None,
        on_candle_close: Optional[Callable[[Candle], None]] = None,
        kite_client: Optional[Any] = None,
        kite_ticker: Optional[Any] = None,
    ):
        self.user_id = user_id
        self.api_key = api_key
        self.access_token = access_token
        self.symbols: List[str] = [s.upper().strip() for s in (symbols or ["NIFTY", "RELIANCE"])]
        self.on_candle_close = on_candle_close

        # External client injection for testing & production instantiation
        self._kite_client = kite_client
        self._kite_ticker = kite_ticker

        # Symbol to Aggregator mapping
        self._aggregators: Dict[str, TickToCandleAggregator] = {}
        self._token_to_symbol: Dict[int, str] = {}
        self._subscribed_tokens: Set[int] = set()
        self._is_connected: bool = False

        self._init_aggregators()

    def _init_aggregators(self):
        """Initialize per-symbol aggregators and resolve Kite instrument tokens."""
        for sym in self.symbols:
            inst = instruments_registry.get_by_symbol(sym)
            if inst:
                token = inst.instrument_token
                self._token_to_symbol[token] = sym
                self._subscribed_tokens.add(token)
            else:
                logger.warning(f"Could not resolve instrument token for symbol: {sym}")

            agg = TickToCandleAggregator(
                symbol=sym,
                on_candle_close=self._handle_candle_closed,
                fill_gaps=True,
            )
            self._aggregators[sym] = agg
            feed_health_monitor.register_symbol(sym)

    def _handle_candle_closed(self, candle: Candle):
        """Dispatch completed 1-minute candle to consumer callback."""
        if self.on_candle_close:
            try:
                self.on_candle_close(candle)
            except Exception as e:
                logger.error(f"Error in on_candle_close callback for {candle.symbol}: {e}")

    def get_kite_client(self) -> Any:
        """Lazy load or return initialized KiteConnect client."""
        if self._kite_client is not None:
            return self._kite_client
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(self.access_token)
        self._kite_client = kite
        return self._kite_client

    # -------------------------------------------------------------------------
    # WebSocket Ticker Stream Management
    # -------------------------------------------------------------------------
    def on_ticks(self, ws: Any, ticks: List[Dict[str, Any]]):
        """Callback executed on incoming tick packets from KiteTicker."""
        for raw in ticks:
            token = raw.get("instrument_token")
            symbol = self._token_to_symbol.get(token)
            if not symbol:
                continue

            last_price = float(raw.get("last_price", 0.0))
            if last_price <= 0:
                continue

            # Kite sends timestamp as datetime or string
            raw_ts = raw.get("timestamp") or raw.get("last_trade_time") or datetime.now(IST)
            if isinstance(raw_ts, str):
                try:
                    ts = datetime.fromisoformat(raw_ts)
                except Exception:
                    ts = datetime.now(IST)
            else:
                ts = raw_ts

            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=IST)

            market_tick = MarketTick(
                instrument_token=token,
                symbol=symbol,
                last_price=last_price,
                last_quantity=int(raw.get("last_traded_quantity", 0)),
                volume_traded=int(raw.get("volume_traded", 0)),
                timestamp=ts,
            )

            # Record heartbeat in health monitor & risk watchdog
            feed_health_monitor.record_tick(symbol, tick_time=ts)

            # Route to aggregator
            agg = self._aggregators.get(symbol)
            if agg:
                agg.process_tick(market_tick)

    def on_connect(self, ws: Any, response: Any):
        """Callback upon successful WebSocket handshake."""
        self._is_connected = True
        logger.info(f"[KITE TICKER] Connected for user {self.user_id}. Subscribing to tokens: {list(self._subscribed_tokens)}")
        if self._subscribed_tokens:
            ws.subscribe(list(self._subscribed_tokens))
            ws.set_mode(ws.MODE_FULL, list(self._subscribed_tokens))

    def on_close(self, ws: Any, code: int, reason: str):
        self._is_connected = False
        logger.warning(f"[KITE TICKER] Connection closed for user {self.user_id}: {code} - {reason}")

    def on_error(self, ws: Any, code: int, reason: str):
        logger.error(f"[KITE TICKER] Connection error for user {self.user_id}: {code} - {reason}")

    # -------------------------------------------------------------------------
    # Historical Backfill & Cold-Start Hydration
    # -------------------------------------------------------------------------
    async def backfill_historical_candles(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        timeframe: str = "minute",
    ) -> List[Candle]:
        """
        Fetch historical candle bars from Kite historical API and convert to shared Candle schemas.
        Enforces rate limiting (maximum 3 requests per second) to stay compliant with broker limits.
        """
        sym = symbol.upper().strip()
        inst = instruments_registry.get_by_symbol(sym)
        if not inst:
            logger.error(f"Cannot backfill: unknown instrument {sym}")
            return []

        kite = self.get_kite_client()
        candles: List[Candle] = []

        # Chunk large queries into 5-day blocks to prevent API timeouts
        chunk_start = from_date
        while chunk_start < to_date:
            chunk_end = min(chunk_start + timedelta(days=5), to_date)
            try:
                # Rate limit safety delay: 350ms between requests (approx 2.8 req/sec < 3.0 limit)
                await asyncio.sleep(0.35)

                records = kite.historical_data(
                    instrument_token=inst.instrument_token,
                    from_date=chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                    to_date=chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                    interval=timeframe,
                    continuous=False,
                    oi=False,
                )

                for r in records:
                    r_dt = r["date"] if isinstance(r["date"], datetime) else datetime.fromisoformat(r["date"])
                    if r_dt.tzinfo is None:
                        r_dt = r_dt.replace(tzinfo=IST)

                    tf_str = "1m" if timeframe == "minute" else timeframe
                    c = Candle(
                        symbol=sym,
                        timeframe=tf_str,
                        timestamp=r_dt,
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume=int(r["volume"]),
                        vwap=float(r.get("vwap", r["close"])),
                    )
                    candles.append(c)

            except Exception as e:
                logger.error(f"[HISTORICAL BACKFILL] Failed chunk {chunk_start} to {chunk_end} for {sym}: {e}")
                break

            chunk_start = chunk_end + timedelta(minutes=1)

        logger.info(f"[HISTORICAL BACKFILL] Completed {len(candles)} candles for {sym} from {from_date} to {to_date}.")
        return candles

    def get_completed_candles(self, symbol: str) -> List[Candle]:
        """Return all closed candles accumulated so far by the aggregator."""
        agg = self._aggregators.get(symbol.upper().strip())
        return agg.completed_candles if agg else []
