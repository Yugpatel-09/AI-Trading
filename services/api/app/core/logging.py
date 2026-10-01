import logging
import re

# Redaction patterns for sensitive authorization credentials
SENSITIVE_PATTERNS = [
    (re.compile(r'(password["\':\s=]+)([^"\'\s&,]+)', re.IGNORECASE), r'\1[REDACTED_PASSWORD]'),
    (re.compile(r'(token["\':\s=]+)([^"\'\s&,]+)', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'(api_key["\':\s=]+)([^"\'\s&,]+)', re.IGNORECASE), r'\1[REDACTED_API_KEY]'),
    (re.compile(r'(api_secret["\':\s=]+)([^"\'\s&,]+)', re.IGNORECASE), r'\1[REDACTED_SECRET]'),
    (re.compile(r'(totp_secret["\':\s=]+)([^"\'\s&,]+)', re.IGNORECASE), r'\1[REDACTED_TOTP]'),
    (re.compile(r'(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)', re.IGNORECASE), r'\1[REDACTED_BEARER]'),
]

class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips and redacts secrets before writing."""
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        redacted = original
        for pattern, replacement in SENSITIVE_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

def setup_secure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("tradeforge")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

logger = setup_secure_logging()
