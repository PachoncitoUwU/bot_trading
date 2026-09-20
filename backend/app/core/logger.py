"""Secure and Structured Logging with Secret Redaction."""
import logging
import re
import sys


class SecretRedactingFormatter(logging.Formatter):
    """Filters out sensitive API keys and secrets from logs."""
    
    PATTERNS = [
        re.compile(r'(api_key|secret|password|token)["\']?\s*[:=]\s*["\']?([^"\'\s,]+)', re.IGNORECASE),
        re.compile(r'(Bearer\s+)([A-Za-z0-9\-\._~\+\/]+=*)', re.IGNORECASE),
    ]

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        redacted = original
        for pattern in self.PATTERNS:
            redacted = pattern.sub(r'\1=***REDACTED***', redacted)
        return redacted


def setup_logger(name: str = "trading_bot", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        # Force UTF-8 so Windows cp1252 consoles don't crash on special chars (e.g. →, ✅)
        if hasattr(handler.stream, "reconfigure"):
            try:
                handler.stream.reconfigure(encoding="utf-8")
            except Exception:
                pass  # Non-fatal: some streams (e.g. redirected) don't support reconfigure
        formatter = SecretRedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = setup_logger()
