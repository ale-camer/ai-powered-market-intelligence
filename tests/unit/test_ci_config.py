"""Unit tests for GitHub Actions CI/CD workflows and automated quality gates.

Validates GitHub Actions workflows (ci.yml, pr_hygiene.yml, release.yml), job structure,
service containers (pgvector, redis), coverage thresholds, conventional commit regex,
and Makefile local CI targets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.issue_22]

WORKFLOWS_DIR = Path(".github/workflows")


def test_github_workflows_directory_and_files_exist() -> None:
    """Validate .github/workflows directory exists with all required pipeline definitions."""
    assert WORKFLOWS_DIR.is_dir(), ".github/workflows directory must exist"

    expected_files = [
        WORKFLOWS_DIR / "ci.yml",
        WORKFLOWS_DIR / "pr_hygiene.yml",
        WORKFLOWS_DIR / "release.yml",
    ]
    for workflow_file in expected_files:
        assert workflow_file.exists(), f"Missing required workflow file: {workflow_file}"


def test_ci_workflow_schema_and_triggers() -> None:
    """Validate ci.yml triggers on pushes/PRs to develop and main, and configures concurrency."""
    ci_path = WORKFLOWS_DIR / "ci.yml"
    with open(ci_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    # In YAML 1.1, unquoted 'on' evaluates to boolean True
    triggers = config.get("on") or config.get(True) or {}
    assert "push" in triggers
    assert "branches" in triggers["push"]
    assert "develop" in triggers["push"]["branches"]
    assert "main" in triggers["push"]["branches"]

    assert "pull_request" in triggers
    assert "branches" in triggers["pull_request"]
    assert "develop" in triggers["pull_request"]["branches"]
    assert "main" in triggers["pull_request"]["branches"]

    # Validate concurrency cancellation
    concurrency = config.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is True


def test_ci_workflow_jobs_and_coverage_gate() -> None:
    """Validate ci.yml declares required jobs, matrix versions, and strict coverage gate."""
    ci_path = WORKFLOWS_DIR / "ci.yml"
    with open(ci_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    jobs = config.get("jobs", {})
    expected_jobs = ["lint-and-typecheck", "test-suite", "docker-build-check", "terraform-validate"]
    for job_name in expected_jobs:
        assert job_name in jobs, f"Missing job '{job_name}' in ci.yml"

    # Lint and Typecheck assertions
    lint_job = jobs["lint-and-typecheck"]
    lint_steps_text = str(lint_job.get("steps", []))
    assert "ruff format --check" in lint_steps_text
    assert "ruff check" in lint_steps_text
    assert "mypy" in lint_steps_text

    # Test Suite assertions
    test_job = jobs["test-suite"]
    assert "lint-and-typecheck" in test_job.get("needs", [])
    matrix = test_job.get("strategy", {}).get("matrix", {})
    assert "3.12" in matrix.get("python-version", [])

    test_steps_text = str(test_job.get("steps", []))
    assert "--cov-fail-under=80" in test_steps_text
    assert "--cov=src" in test_steps_text


def test_ci_workflow_service_containers() -> None:
    """Validate ci.yml test-suite configures pgvector and redis service containers."""
    ci_path = WORKFLOWS_DIR / "ci.yml"
    with open(ci_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    test_job = config["jobs"]["test-suite"]
    assert "services" in test_job, "test-suite job must declare services"
    services = test_job["services"]

    assert "postgres" in services
    assert "pgvector" in services["postgres"].get("image", "")
    assert "5432:5432" in services["postgres"].get("ports", [])

    assert "redis" in services
    assert "redis:7" in services["redis"].get("image", "")
    assert "6379:6379" in services["redis"].get("ports", [])


def test_pr_hygiene_workflow_configuration() -> None:
    """Validate pr_hygiene.yml checks Conventional Commits regex pattern on PR titles."""
    pr_path = WORKFLOWS_DIR / "pr_hygiene.yml"
    with open(pr_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    triggers = config.get("on") or config.get(True) or {}
    assert "pull_request" in triggers
    pr_types = triggers["pull_request"].get("types", [])
    assert "opened" in pr_types

    jobs = config.get("jobs", {})
    assert "check-pr-title" in jobs
    steps_text = str(jobs["check-pr-title"].get("steps", []))
    assert "feat|fix|docs|test|chore|refactor|perf|ci" in steps_text


def test_release_workflow_configuration() -> None:
    """Validate release.yml triggers on semver tags and configures release automation."""
    release_path = WORKFLOWS_DIR / "release.yml"
    with open(release_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    triggers = config.get("on") or config.get(True) or {}
    assert "push" in triggers
    tags = triggers["push"].get("tags", [])
    assert "v*.*.*" in tags

    jobs = config.get("jobs", {})
    assert "build-and-release" in jobs
    steps_text = str(jobs["build-and-release"].get("steps", []))
    assert "action-gh-release" in steps_text


def test_makefile_ci_target() -> None:
    """Validate Makefile contains local ci target invoking check and test."""
    makefile_content = Path("Makefile").read_text(encoding="utf-8")

    assert ".PHONY: ci" in makefile_content
    assert "ci: check test" in makefile_content
