"""Structured logging setup. One line per event, ids included, no sensitive data."""

import logging
import sys

from app.core.config import settings


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    return logging.getLogger("bulk-cert")


logger = setup_logging()
