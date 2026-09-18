"""Centralized logging configuration with structured and JSON formatting support."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from market_intel.core.config import get_settings


def configure_logging(
    log_level: str | None = None,
    use_json: bool | None = None,
) -> None:
    """Configure the root logger with either standard or JSON structured formatting."""
    settings = get_settings()
    level_name = (log_level or settings.log_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    # In production, default to JSON logging; otherwise, human-readable
    if use_json is None:
        use_json = settings.app_env == "production"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if use_json:
        formatter: logging.Formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "timestamp"},
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for the given component name."""
    return logging.getLogger(name)
