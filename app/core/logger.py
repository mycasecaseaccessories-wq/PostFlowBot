"""Central logging configuration with secret redaction safeguards."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

_configured = False


class SecretRedactionFilter(logging.Filter):
    """Replace configured secret values if they are accidentally included in logs."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure console, rotating application, and error logs once per process."""
    global _configured
    if _configured:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    redaction = SecretRedactionFilter(
        os.environ.get(name, "")
        for name in ("BOT_TOKEN", "API_HASH", "TELEGRAM_SESSION")
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(redaction)

    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    application_log = RotatingFileHandler(
        log_dir / "application.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    application_log.setFormatter(formatter)
    application_log.addFilter(redaction)

    error_log = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_log.setLevel(logging.ERROR)
    error_log.setFormatter(formatter)
    error_log.addFilter(redaction)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(console)
    root.addHandler(application_log)
    root.addHandler(error_log)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)