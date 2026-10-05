# Issue 25: v1.0.0 Production Release

**Branch:** `feature/issue-25-release-v1`
**Status:** Planned
**PR:** TBD
**Milestone:** M5 — Quality, Security & Release

---

## Objective

Prepare the repository for the final v1.0.0 production release. This involves bumping the package version, updating metadata classifiers to indicate a stable production status, generating an initial CHANGELOG, and finalizing Milestone 5.

---

## Acceptance Criteria

- [ ] **Version Bump (`pyproject.toml`)**:
  - Update project `version` from `0.1.0` to `1.0.0`.
  - Update `classifiers` from `Development Status :: 1 - Planning` to `Development Status :: 5 - Production/Stable`.
- [ ] **Changelog (`CHANGELOG.md`)**:
  - Create a `CHANGELOG.md` file documenting the v1.0.0 release features (Ingestion, NLP, Storage, Orchestration, API, Security, DevOps).
- [ ] **Tests (`tests/unit/test_release.py`)**:
  - Ensure a simple unit test exists under `@pytest.mark.issue_25` that verifies the version strings.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=25 NAME=release-v1
```

### 2. Version Bump
- **File**: `pyproject.toml`
  - Change `version` to `"1.0.0"`.
  - Change `Development Status` classifier.

### 3. Changelog Creation
- **File**: `CHANGELOG.md`
  - Write comprehensive release notes for version 1.0.0.

### 4. Version Test
- **File**: `tests/unit/test_release.py`
  - Write test to assert `get_settings().api_version == "1.0.0"` or similar.

### 5. Verification & Quality Gates
```bash
make test-issue ID=25
make check
```

### 6. Git & Issue Finish
```bash
make finish-issue ID=25 MSG="chore: bump version to v1.0.0 and prepare production release"
```

### 7. Milestone Finish (Post-Issue)
Because Issue 25 concludes Milestone 5:
```bash
make finish-milestone MILESTONE=M5
```
