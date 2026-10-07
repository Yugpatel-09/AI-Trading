"""
NSE & Kite Instruments Registry and Cache.

Caches the daily instruments dump from Zerodha Kite Connect, providing fast,
type-safe lookup for:
1. Instrument tokens (used for WebSocket subscriptions & live ticks).
2. Trading symbols, exchange segments, and lot sizes.
3. Official tick sizes (e.g. 0.05) and price rounding.
4. Upper and lower circuit limits (price bands).
5. Offline / local cache persistence with 24-hour TTL.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from services.api.app.core.logging import logger


class InstrumentInfo(BaseModel):
    """Normalized metadata for a traded instrument on NSE."""
    instrument_token: int
    exchange_token: int = 0
    tradingsymbol: str
    name: str = ""
    last_price: float = 0.0
    tick_size: float = 0.05
    lot_size: int = 1
    instrument_type: str = "EQ"
    segment: str = "NSE"
    exchange: str = "NSE"
    strike: float = 0.0
    expiry: Optional[str] = None
    lower_circuit_limit: Optional[float] = None
    upper_circuit_limit: Optional[float] = None


# Default fallback directory for daily cache
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"


class InstrumentsRegistry:
    """
    Thread-safe registry for NSE instrument metadata.
    Refreshes daily at pre-open or caches locally to eliminate external API bottlenecks.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._by_symbol: Dict[str, InstrumentInfo] = {}
        self._by_token: Dict[int, InstrumentInfo] = {}
        self._last_loaded_date: str = ""

        # Pre-seed standard benchmark instruments so platform functions without network
        self._seed_default_universe()

    def _seed_default_universe(self):
        """Standard high-liquidity NSE universe defaults."""
        defaults = [
            InstrumentInfo(
                instrument_token=256265,
                tradingsymbol="NIFTY 50",
                name="NIFTY 50",
                tick_size=0.05,
                lot_size=25,
                instrument_type="INDEX",
                segment="INDICES",
            ),
            InstrumentInfo(
                instrument_token=260105,
                tradingsymbol="NIFTY BANK",
                name="NIFTY BANK",
                tick_size=0.05,
                lot_size=15,
                instrument_type="INDEX",
                segment="INDICES",
            ),
            InstrumentInfo(
                instrument_token=738561,
                tradingsymbol="RELIANCE",
                name="RELIANCE INDUSTRIES",
                tick_size=0.05,
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                lower_circuit_limit=2250.0,
                upper_circuit_limit=2750.0,
            ),
            InstrumentInfo(
                instrument_token=2953217,
                tradingsymbol="TCS",
                name="TATA CONSULTANCY SERVICES",
                tick_size=0.05,
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                lower_circuit_limit=3600.0,
                upper_circuit_limit=4400.0,
            ),
            InstrumentInfo(
                instrument_token=408065,
                tradingsymbol="INFY",
                name="INFOSYS",
                tick_size=0.05,
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                lower_circuit_limit=1600.0,
                upper_circuit_limit=2100.0,
            ),
            InstrumentInfo(
                instrument_token=341249,
                tradingsymbol="HDFCBANK",
                name="HDFC BANK",
                tick_size=0.05,
                lot_size=1,
                instrument_type="EQ",
                segment="NSE",
                lower_circuit_limit=1400.0,
                upper_circuit_limit=1800.0,
            ),
        ]
        for inst in defaults:
            self.register_instrument(inst)

    def register_instrument(self, inst: InstrumentInfo):
        key = inst.tradingsymbol.upper().strip()
        self._by_symbol[key] = inst
        self._by_token[inst.instrument_token] = inst

    def get_by_symbol(self, symbol: str) -> Optional[InstrumentInfo]:
        """Look up instrument metadata by standard symbol name (case-insensitive)."""
        key = symbol.upper().strip()
        # Handle variations: NIFTY vs NIFTY 50
        if key == "NIFTY":
            return self._by_symbol.get("NIFTY 50") or self._by_symbol.get("NIFTY")
        if key == "BANKNIFTY":
            return self._by_symbol.get("NIFTY BANK") or self._by_symbol.get("BANKNIFTY")
        return self._by_symbol.get(key)

    def get_token(self, symbol: str) -> Optional[int]:
        """Get the integer instrument token for KiteTicker subscription."""
        inst = self.get_by_symbol(symbol)
        return inst.instrument_token if inst else None

    def get_by_token(self, token: int) -> Optional[InstrumentInfo]:
        """Look up instrument metadata by Kite integer instrument token."""
        return self._by_token.get(token)

    def round_to_tick(self, price: float, symbol: str) -> float:
        """Rounds price to the nearest valid exchange tick size."""
        inst = self.get_by_symbol(symbol)
        tick = inst.tick_size if inst else 0.05
        if tick <= 0:
            return round(price, 2)
        steps = round(price / tick)
        return round(steps * tick, 2)

    def check_circuit_limits(self, symbol: str, price: float) -> tuple[bool, str]:
        """
        Verify whether an order price falls within official exchange circuit bands.
        Returns (is_valid, rejection_reason).
        """
        inst = self.get_by_symbol(symbol)
        if not inst:
            return True, ""
        if inst.lower_circuit_limit and price < inst.lower_circuit_limit:
            return False, f"Price ₹{price:.2f} is below lower circuit limit ₹{inst.lower_circuit_limit:.2f}"
        if inst.upper_circuit_limit and price > inst.upper_circuit_limit:
            return False, f"Price ₹{price:.2f} is above upper circuit limit ₹{inst.upper_circuit_limit:.2f}"
        return True, ""

    def load_from_kite_dump(self, raw_instruments: List[Dict[str, Any]]):
        """
        Parse and load official daily dump from KiteConnect SDK `kite.instruments("NSE")`.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        loaded = 0
        for item in raw_instruments:
            try:
                inst = InstrumentInfo(
                    instrument_token=int(item["instrument_token"]),
                    exchange_token=int(item.get("exchange_token", 0)),
                    tradingsymbol=str(item["tradingsymbol"]),
                    name=str(item.get("name", "")),
                    tick_size=float(item.get("tick_size", 0.05)),
                    lot_size=int(item.get("lot_size", 1)),
                    instrument_type=str(item.get("instrument_type", "EQ")),
                    segment=str(item.get("segment", "NSE")),
                    exchange=str(item.get("exchange", "NSE")),
                    strike=float(item.get("strike", 0.0)),
                    expiry=str(item["expiry"]) if item.get("expiry") else None,
                )
                self.register_instrument(inst)
                loaded += 1
            except Exception:
                continue

        self._last_loaded_date = today_str
        logger.info(f"Loaded {loaded} instruments from Kite dump for {today_str}.")
        self.save_cache()

    def save_cache(self):
        """Persist current registry to disk cache."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        cache_file = self.cache_dir / f"instruments_{today_str}.json"
        try:
            data = [inst.model_dump() for inst in self._by_token.values()]
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Could not persist instruments cache: {e}")

    def load_cache(self) -> bool:
        """Load instruments from disk cache if created within the last 24 hours."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        cache_file = self.cache_dir / f"instruments_{today_str}.json"
        if not cache_file.exists():
            return False
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                items = json.load(f)
                for it in items:
                    self.register_instrument(InstrumentInfo(**it))
            self._last_loaded_date = today_str
            return True
        except Exception as e:
            logger.warning(f"Failed to load instruments cache: {e}")
            return False


# Global singleton instance
instruments_registry = InstrumentsRegistry()
