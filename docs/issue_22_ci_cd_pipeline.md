# Issue 22: Automated CI/CD Pipelines with GitHub Actions

**Branch:** `feature/issue-22-ci-cd-pipeline`  
**Status:** Completed  
**PR:** TBD  
**Milestone:** M5 — Quality, Security & Release  

---

## Objective

Build a comprehensive, multi-stage Continuous Integration and Continuous Delivery (CI/CD) automation pipeline using GitHub Actions for the AI-Powered Market Intelligence platform. Implement automated pull request validation (Conventional Commits enforcement, Ruff linting and formatting, Mypy strict type checking, and Pytest coverage gates enforcing $\ge 80\%$ statement coverage), container image builds, Terraform configuration validation, and automated production release packaging with semantic versioning. Provide a dedicated test suite under `@pytest.mark.issue_22` validating workflow YAML schemas, job triggers, environment matrices, and command sequences.

---

## Acceptance Criteria

- [x] **Continuous Integration Workflow (`.github/workflows/ci.yml`)**:
  - Triggers on:
    - Pull Requests targeting `develop` and `main`.
    - Pushes to `develop` and `main`.
  - Job 1: **`lint-and-typecheck`**:
    - Checks out code with full history.
    - Sets up Python 3.12 with pip caching enabled.
    - Runs Ruff formatting verification (`ruff format --check src/ tests/`).
    - Runs Ruff linter (`ruff check src/ tests/`).
    - Runs Mypy static type checker (`mypy src/`).
  - Job 2: **`test-suite`**:
    - Matrix testing on Python 3.12 and 3.13.
    - Provisioned service containers: PostgreSQL 16 with `pgvector` extension and Redis 7 Alpine with healthchecks.
    - Executes the test suite with strict coverage enforcement: `pytest tests/ --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=80`.
    - Uploads coverage reports as workflow artifacts.
  - Job 3: **`docker-build-check`**:
    - Validates that the multi-stage `Dockerfile` compiles cleanly without warnings.
    - Executes container healthcheck validation against built image.
  - Job 4: **`terraform-validate`**:
    - Installs Terraform CLI.
    - Runs `terraform fmt -check -recursive infra/terraform`.
    - Initializes and validates HCL configuration (`terraform init -backend=false && terraform validate`).
- [x] **PR Hygiene & Commit Validation (`.github/workflows/pr_hygiene.yml`)**:
  - Validates PR title follows Conventional Commits specification (`feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `perf`, `ci`).
- [x] **Release & Artifact Packaging Workflow (`.github/workflows/release.yml`)**:
  - Triggers on semantic version tag pushes (`v*.*.*`).
  - Builds and tags production container images (`latest` and semver tag).
  - Drafts GitHub Release notes with automated changelog generation.
- [x] **Local Developer Ergonomics & Makefile (`Makefile`)**:
  - Target `make ci` allowing developers to execute the full CI verification suite locally (`make check && make test`).
- [x] **Automated Unit & Configuration Tests (`tests/unit/test_ci_config.py`)**:
  - Unit tests under `@pytest.mark.unit` and `@pytest.mark.issue_22`:
    - Validates `.github/workflows/` YAML syntax with `yaml.safe_load`.
    - Asserts event triggers (PRs to `develop`/`main`, push to `develop`/`main`, version tags).
    - Asserts presence of critical jobs: linting, typechecking, pytest coverage with `--cov-fail-under=80`, container build, and Terraform validation.
    - Asserts PostgreSQL pgvector and Redis services in CI test job.
    - Asserts Makefile `ci` target consistency.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=22 NAME=ci-cd-pipeline
```

### 2. Main CI Workflow Configuration
- **File**: `.github/workflows/ci.yml`
  - Define top-level triggers (`pull_request`, `push` on branches `[develop, main]`).
  - Define `concurrency` group to cancel redundant runs on subsequent commits to the same PR.
  - Job `lint-and-typecheck`:
    - `actions/checkout@v4`
    - `actions/setup-python@v5` with `cache: 'pip'`
    - Run `pip install -e ".[dev]"`
    - Run Ruff check & format
    - Run Mypy
  - Job `test-suite`:
    - Define services:
      - `postgres`: image `pgvector/pgvector:pg16`, healthcheck `pg_isready`
      - `redis`: image `redis:7-alpine`, healthcheck `redis-cli ping`
    - Run `pytest tests/ --cov=src --cov-fail-under=80`
    - `actions/upload-artifact@v4` for coverage reports
  - Job `docker-build-check`:
    - `docker/setup-buildx-action@v3`
    - `docker/build-push-action@v5` with `push: false`, `load: true`
  - Job `terraform-validate`:
    - `hashicorp/setup-terraform@v3`
    - Run `terraform fmt -check` and `terraform validate`

### 3. PR Hygiene Workflow Configuration
- **File**: `.github/workflows/pr_hygiene.yml`
  - Validate PR title against Conventional Commits regex `^(feat|fix|docs|test|chore|refactor|perf|ci)(\([a-zA-Z0-9_-]+\))?: .{1,80}$`.

### 4. Release Automation Workflow Configuration
- **File**: `.github/workflows/release.yml`
  - Triggers on `tags: ['v*.*.*']`.
  - Builds production Docker image and creates GitHub Release via `softprops/action-gh-release@v2`.

### 5. Makefile Integration
- **File**: `Makefile`
  - Add `ci` target executing `check` and `test`:
    ```makefile
    .PHONY: ci
    ci: check test ## Run full CI pipeline checks locally
    ```

### 6. Automated Unit Tests
- **File**: `tests/unit/test_ci_config.py`
  - Mark `@pytest.mark.unit` and `@pytest.mark.issue_22`:
    - `test_github_workflows_directory_and_files_exist`: Verifies `ci.yml`, `pr_hygiene.yml`, `release.yml`.
    - `test_ci_workflow_triggers_and_concurrency`: Verifies triggers and PR concurrency cancel.
    - `test_ci_workflow_jobs_and_coverage_gate`: Verifies jobs `lint-and-typecheck`, `test-suite` (with `--cov-fail-under=80`), `docker-build-check`, `terraform-validate`.
    - `test_ci_workflow_services_postgres_redis`: Verifies `pgvector` and `redis` service containers.
    - `test_release_workflow_triggers_and_steps`: Verifies tag trigger `v*.*.*`.
    - `test_pr_hygiene_workflow_conventional_commits`: Verifies regex pattern.
    - `test_makefile_ci_target`: Verifies `ci: check test` in Makefile.

### 7. Verification & Quality Gates
```bash
make test-issue ID=22
.venv/bin/pytest tests/ --cov=src --cov-fail-under=80
make check
```

### 8. Git & Issue Finish
```bash
make finish-issue ID=22 MSG="ci: implement automated GitHub Actions CI/CD workflows and quality gates"
```
