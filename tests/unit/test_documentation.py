"""Tests for project documentation and OpenAPI schema."""

from pathlib import Path

import pytest

from market_intel.api.app import MarketIntelASGIApp
from market_intel.core.config import Settings


@pytest.mark.unit
@pytest.mark.issue_24
def test_mkdocs_config_exists() -> None:
    """Verify mkdocs.yml is configured."""
    assert Path("mkdocs.yml").is_file(), "mkdocs.yml must exist"

@pytest.mark.unit
@pytest.mark.issue_24
def test_openapi_schema_metadata() -> None:
    """Verify OpenAPI schema includes custom metadata."""
    settings = Settings(
        app_env="test",
        secret_key="test_key_that_is_long_enough_for_validation_12345",
    )
    app = MarketIntelASGIApp(settings=settings)
    
    # We must access the internal FastAPI instance to check schema
    if app._fastapi_app:
        schema = app._fastapi_app.openapi()  # type: ignore[attr-defined]
        assert schema["info"]["title"] == settings.api_title
        assert "description" in schema["info"]
        assert "contact" in schema["info"]
        assert "tags" in schema
        
        tags = [t["name"] for t in schema["tags"]]
        assert "Health" in tags
        assert "Signals" in tags
