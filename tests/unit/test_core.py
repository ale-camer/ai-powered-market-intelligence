"""Unit tests for market_intel.core modules."""

import logging

import pytest

from market_intel.core.config import Settings, get_settings
from market_intel.core.exceptions import ConfigurationError, MarketIntelError
from market_intel.core.logger import configure_logging, get_logger


@pytest.mark.unit
@pytest.mark.issue_01
@pytest.mark.issue_1
def test_settings_load_defaults() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.app_env in {"development", "staging", "production", "test"}
    assert settings.postgres_port == 5432
    assert settings.postgres_db == "market_intel"


@pytest.mark.unit
@pytest.mark.issue_01
@pytest.mark.issue_1
def test_exceptions_hierarchy() -> None:
    err = ConfigurationError("Invalid configuration")
    assert isinstance(err, MarketIntelError)
    assert isinstance(err, Exception)
    assert str(err) == "Invalid configuration"
    assert err.message == "Invalid configuration"


@pytest.mark.unit
@pytest.mark.issue_01
@pytest.mark.issue_1
def test_configure_logging_standard() -> None:
    configure_logging(log_level="DEBUG", use_json=False)
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.unit
@pytest.mark.issue_01
@pytest.mark.issue_1
def test_configure_logging_json() -> None:
    configure_logging(log_level="INFO", use_json=True)
    logger = get_logger("test_json_module")
    assert isinstance(logger, logging.Logger)
    assert logging.getLogger().level == logging.INFO
