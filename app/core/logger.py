"""Central logging configuration with secret redaction safeguards."""

from __future__ import annotations

import logging
import os
import sys
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
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    handler.addFilter(
        SecretRedactionFilter(
            os.environ.get(name, "")
            for name in ("BOT_TOKEN", "API_HASH", "TELEGRAM_SESSION")
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)