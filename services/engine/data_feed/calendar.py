"""
NSE Market Calendar and Session Schedule.

Handles:
1. Standard trading hours (09:15:00 to 15:30:00 IST).
2. Pre-market session (09:00:00 to 09:15:00 IST).
3. Weekend closures (Saturday & Sunday).
4. Official NSE holidays (configurable via JSON or environment).
5. Special sessions (e.g., Diwali Muhurat trading).
"""

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Set

IST = timezone(timedelta(hours=5, minutes=30))
REGULAR_PRE_OPEN_TIME = time(9, 0, 0)
REGULAR_OPEN_TIME = time(9, 15, 0)
REGULAR_CLOSE_TIME = time(15, 30, 0)

# Default Official NSE Holidays (2026 calendar baseline)
DEFAULT_NSE_HOLIDAYS_2026: Set[str] = {
    "2026-01-26",  # Republic Day
    "2026-02-17",  # Mahashivratri
    "2026-03-03",  # Holi
    "2026-03-20",  # Id-Ul-Fitr
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. B.R. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-27",  # Bakri Id
    "2026-08-15",  # Independence Day
    "2026-09-04",  # Janmashtami
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-09",  # Diwali Balipratipada
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
}

# Special sessions (e.g., Diwali Laxmi Pujan Muhurat Trading)
DEFAULT_SPECIAL_SESSIONS: Dict[str, Dict[str, str]] = {
    "2026-11-08": {
        "name": "Diwali Muhurat Trading",
        "open": "18:15:00",
        "close": "19:15:00",
        "pre_open": "18:00:00",
    }
}


class NSEMarketCalendar:
    """
    Authoritative NSE Trading Calendar & Session Schedule.
    Configurable via environment variables:
      NSE_HOLIDAYS_CONFIG_PATH: Path to custom JSON file containing holidays & special sessions.
    """

    def __init__(self, config_path: Optional[str] = None):
        self._holidays: Set[str] = set(DEFAULT_NSE_HOLIDAYS_2026)
        self._special_sessions: Dict[str, Dict[str, str]] = dict(DEFAULT_SPECIAL_SESSIONS)
        path = config_path or os.getenv("NSE_HOLIDAYS_CONFIG_PATH")
        if path and Path(path).exists():
            self._load_config(Path(path))

    def _load_config(self, file_path: Path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "holidays" in data:
                    self._holidays = set(data["holidays"])
                if "special_sessions" in data:
                    self._special_sessions = data["special_sessions"]
        except Exception:
            pass

    def add_holiday(self, holiday_date: date | str):
        date_str = holiday_date.isoformat() if isinstance(holiday_date, date) else str(holiday_date)
        self._holidays.add(date_str)

    def add_special_session(self, session_date: str, open_time: str, close_time: str, pre_open_time: str = "18:00:00", name: str = "Special Session"):
        self._special_sessions[str(session_date)] = {
            "name": name,
            "open": open_time,
            "close": close_time,
            "pre_open": pre_open_time,
        }

    def is_trading_day(self, target_date: date) -> bool:
        """Returns True if the specified date is an active NSE trading day."""
        date_str = target_date.isoformat()
        # Special session overrides weekend / standard holiday
        if date_str in self._special_sessions:
            return True
        # Saturday (5) or Sunday (6)
        if target_date.weekday() >= 5:
            return False
        # Official holiday
        if date_str in self._holidays:
            return False
        return True

    def get_session_window(self, target_date: date) -> Optional[tuple[datetime, datetime]]:
        """Returns (session_open, session_close) in IST for a given date, or None if market is closed."""
        if not self.is_trading_day(target_date):
            return None

        date_str = target_date.isoformat()
        if date_str in self._special_sessions:
            spec = self._special_sessions[date_str]
            o_h, o_m, o_s = map(int, spec["open"].split(":"))
            c_h, c_m, c_s = map(int, spec["close"].split(":"))
            s_open = datetime(target_date.year, target_date.month, target_date.day, o_h, o_m, o_s, tzinfo=IST)
            s_close = datetime(target_date.year, target_date.month, target_date.day, c_h, c_m, c_s, tzinfo=IST)
            return s_open, s_close

        s_open = datetime(target_date.year, target_date.month, target_date.day, 9, 15, 0, tzinfo=IST)
        s_close = datetime(target_date.year, target_date.month, target_date.day, 15, 30, 0, tzinfo=IST)
        return s_open, s_close

    def get_pre_open_time(self, target_date: date) -> Optional[datetime]:
        """Returns the pre-open start time in IST (e.g. 09:00 IST), or None if market closed."""
        if not self.is_trading_day(target_date):
            return None
        date_str = target_date.isoformat()
        if date_str in self._special_sessions:
            spec = self._special_sessions[date_str]
            po_h, po_m, po_s = map(int, spec.get("pre_open", "18:00:00").split(":"))
            return datetime(target_date.year, target_date.month, target_date.day, po_h, po_m, po_s, tzinfo=IST)
        return datetime(target_date.year, target_date.month, target_date.day, 9, 0, 0, tzinfo=IST)

    def is_market_open(self, current_time: datetime) -> bool:
        """Determines if the NSE regular trading session is currently open."""
        ist_dt = current_time.astimezone(IST) if current_time.tzinfo else current_time.replace(tzinfo=IST)
        window = self.get_session_window(ist_dt.date())
        if not window:
            return False
        s_open, s_close = window
        return s_open <= ist_dt < s_close

    def is_pre_open_window(self, current_time: datetime) -> bool:
        """Determines if the pre-market session (09:00 to 09:15 IST) is active."""
        ist_dt = current_time.astimezone(IST) if current_time.tzinfo else current_time.replace(tzinfo=IST)
        if not self.is_trading_day(ist_dt.date()):
            return False
        window = self.get_session_window(ist_dt.date())
        po_time = self.get_pre_open_time(ist_dt.date())
        if not window or not po_time:
            return False
        s_open, _ = window
        return po_time <= ist_dt < s_open


# Global singleton instance
nse_calendar = NSEMarketCalendar()
