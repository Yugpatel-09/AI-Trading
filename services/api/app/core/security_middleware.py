import time
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from services.api.app.core.config import settings
from services.api.app.core.logging import logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Institutional Security Headers Middleware.
    Enforces HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
    """
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Standard OWASP / Banking security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none';"
        )

        # HSTS in production or when HTTPS is used
        if not settings.is_dev or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF verification middleware for state-changing cookie authenticated requests.
    Bearer token requests (standard API JWT) are immune to CSRF.
    Any request using cookies for state-changing operations MUST present a valid X-CSRF-Token header.
    """
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    async def dispatch(self, request: Request, call_next):
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        # If a session cookie is present, require X-CSRF-Token matching the cookie
        session_cookie = request.cookies.get("tf_session")
        if session_cookie:
            csrf_token_header = request.headers.get("X-CSRF-Token")
            csrf_cookie = request.cookies.get("tf_csrf")
            if not csrf_token_header or not csrf_cookie or csrf_token_header != csrf_cookie:
                logger.warning(f"CSRF validation failed for path: {request.url.path}")
                return Response(
                    content='{"detail":"CSRF token missing or mismatch."}',
                    status_code=status.HTTP_403_FORBIDDEN,
                    media_type="application/json",
                )

        return await call_next(request)


class InMemoryRateLimiter:
    """
    Sliding-window rate limiter per client key (IP or user ID).
    """
    def __init__(self):
        # Maps key -> list of timestamps
        self._history: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        Returns (is_allowed, remaining_seconds_until_reset).
        """
        now = time.time()
        timestamps = self._history[key]

        # Purge timestamps outside the window
        cutoff = now - window_seconds
        valid_timestamps = [t for t in timestamps if t > cutoff]
        self._history[key] = valid_timestamps

        if len(valid_timestamps) >= max_requests:
            oldest_in_window = valid_timestamps[0]
            remaining = int(window_seconds - (now - oldest_in_window)) + 1
            return False, max(1, remaining)

        self._history[key].append(now)
        return True, 0

    def reset(self):
        self._history.clear()


rate_limiter = InMemoryRateLimiter()


def enforce_rate_limit(key: str, max_requests: int, window_seconds: int = 60):
    """Raise HTTP 429 if key has exceeded max_requests in window_seconds."""
    allowed, retry_after = rate_limiter.check_rate_limit(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds}s. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
