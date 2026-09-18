"""Logging setup."""

from __future__ import annotations

import logging
import sys

from app.core.config import settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # SQLAlchemy's own echo is controlled by DB_ECHO, not the root level.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.db_echo else logging.WARNING
    )
