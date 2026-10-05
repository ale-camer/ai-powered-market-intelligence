"""Tests verifying production release requirements."""

import tomllib
from pathlib import Path

import pytest

from market_intel.core.config import get_settings


@pytest.mark.unit
@pytest.mark.issue_25
def test_api_version_is_v1() -> None:
    """Verify that the API version is bumped to 1.0.0 for the production release."""
    settings = get_settings()
    assert settings.api_version == "1.0.0", "API version must be exactly 1.0.0 for this release"


@pytest.mark.unit
@pytest.mark.issue_25
def test_pyproject_toml_version() -> None:
    """Verify that the pyproject.toml version is bumped to 1.0.0."""
    pyproject_path = Path("pyproject.toml")
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
        
    assert pyproject["project"]["version"] == "1.0.0", "pyproject.toml version must be 1.0.0"
