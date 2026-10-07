"""
Daily Kite Session Validator and Pre-Open Gatekeeper.

Kite Connect access tokens expire daily between 06:00 and 07:30 IST.
This module:
1. Validates user session token via `kite.profile()`.
2. Generates Kite Connect OAuth login URL for daily re-authentication.
3. Exchanges `request_token` for daily `access_token` via `kite.generate_session()`.
4. Performs mandatory pre-open check at 09:00 IST:
   - If valid, authorizes automated trading sessions.
   - If invalid/expired, blocks session startup, logs alert, and dispatches re-auth notification.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel

from services.api.app.core.logging import logger
from services.engine.data_feed.calendar import IST


class KiteSessionStatus(BaseModel):
    user_id: str
    is_valid: bool
    user_name: Optional[str] = None
    broker_user_id: Optional[str] = None
    checked_at: datetime
    error_message: Optional[str] = None
    login_url: Optional[str] = None


class KiteSessionManager:
    """
    Manages daily OAuth lifecycle and pre-market validation for Zerodha Kite Connect.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret

    def get_login_url(self, api_key: Optional[str] = None) -> str:
        """Generate official Zerodha Kite login redirect URL."""
        key = api_key or self.api_key or ""
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={key}"

    def validate_session(self, api_key: str, access_token: str, kite_client: Optional[Any] = None) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Verify that the Kite access token is active and valid for today.
        Returns (is_valid, profile_dict, error_msg).
        """
        if not api_key or not access_token:
            return False, None, "Missing Kite API key or access token."

        try:
            if kite_client is not None:
                profile = kite_client.profile()
            else:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=api_key)
                kite.set_access_token(access_token)
                profile = kite.profile()

            user_id = profile.get("user_id") or profile.get("user_shortname", "")
            user_name = profile.get("user_name", "")
            logger.info(f"[KITE SESSION] Verified active session for {user_id} ({user_name}).")
            return True, profile, None

        except Exception as e:
            err_msg = str(e)
            logger.warning(f"[KITE SESSION] Token validation failed: {err_msg}")
            return False, None, err_msg

    def exchange_request_token(
        self,
        api_key: str,
        api_secret: str,
        request_token: str,
        kite_client: Optional[Any] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Exchange daily post-login request_token for active access_token.
        """
        try:
            if kite_client is not None:
                session_data = kite_client.generate_session(request_token, api_secret=api_secret)
            else:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=api_key)
                session_data = kite.generate_session(request_token, api_secret=api_secret)

            logger.info("[KITE SESSION] Successfully generated new daily access token.")
            return True, session_data, None
        except Exception as e:
            err = str(e)
            logger.error(f"[KITE SESSION] Failed to generate session token: {err}")
            return False, None, err

    def run_pre_open_check(
        self,
        user_id: str,
        api_key: str,
        access_token: str,
        current_time: Optional[datetime] = None,
        kite_client: Optional[Any] = None,
    ) -> KiteSessionStatus:
        """
        Mandatory Pre-Market Check (executed at 09:00 IST).
        Refuses to start automated trading if Kite session is unauthenticated.
        """
        now = current_time or datetime.now(IST)
        is_valid, profile, err = self.validate_session(api_key, access_token, kite_client=kite_client)

        login_url = self.get_login_url(api_key) if not is_valid else None
        status = KiteSessionStatus(
            user_id=user_id,
            is_valid=is_valid,
            user_name=profile.get("user_name") if profile else None,
            broker_user_id=profile.get("user_id") if profile else None,
            checked_at=now,
            error_message=err,
            login_url=login_url,
        )

        if not is_valid:
            logger.critical(
                f"[PRE-OPEN CHECK HALT] User {user_id} Kite session invalid! Trading blocked for today. "
                f"Action required: Re-login at {login_url}"
            )
        else:
            logger.info(f"[PRE-OPEN CHECK PASS] User {user_id} session active. Green light for 09:15 open.")

        return status


# Global singleton instance
kite_session_manager = KiteSessionManager()
