# Issue 24: Project Documentation, OpenAPI, and MkDocs Site

**Branch:** `feature/issue-24-documentation`
**Status:** Planned
**PR:** TBD
**Milestone:** M5 — Quality, Security & Release

---

## Objective

Establish comprehensive project documentation for the AI-Powered Market Intelligence platform. Set up a MkDocs static site using the Material theme to document architecture and deployment. Enhance the FastAPI application with detailed OpenAPI metadata (title, description, tags, models). Add markdown documentation to Airflow DAGs for operational clarity. Finally, provide developer ergonomics to build and serve the documentation locally.

---

## Acceptance Criteria

- [ ] **MkDocs Site (`mkdocs.yml` & `docs/site/`)**:
  - Configure `mkdocs.yml` utilizing the `material` theme.
  - Create a basic documentation structure: `index.md` (overview), `architecture.md` (high-level system design), and `api.md` (endpoints overview).
  - Include necessary MkDocs dependencies in `pyproject.toml` (`mkdocs`, `mkdocs-material`).
- [ ] **OpenAPI & FastAPI Enhancement (`src/market_intel/api/app.py`)**:
  - Add explicit `title`, `description`, `version`, and `contact` metadata to the FastAPI instance.
  - Define `openapi_tags` to group endpoints logically (e.g., Health, Intelligence, Metrics).
- [ ] **Airflow DAG Documentation (`src/market_intel/pipelines/market_intel_dag.py`)**:
  - Inject a detailed `doc_md` into the DAG definition explaining the pipeline phases (Ingest -> Transform -> Load).
- [ ] **Developer Ergonomics (`Makefile`)**:
  - Add a `docs` target to the Makefile that runs `mkdocs serve` to preview documentation locally.
- [ ] **Automated Test Suite (`tests/unit/test_documentation.py`)**:
  - Validate MkDocs configuration file existence.
  - Validate OpenAPI schema generation includes custom metadata.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=24 NAME=documentation
```

### 2. MkDocs Setup
- **File**: `mkdocs.yml`
  - Create the configuration file with Material theme and navigation structure.
- **Files**: `docs/site/index.md`, `docs/site/architecture.md`, `docs/site/api.md`
  - Write foundational documentation for the project.
- **File**: `pyproject.toml`
  - Add `mkdocs-material` to the `dev` group dependencies.

### 3. FastAPI OpenAPI Customization
- **File**: `src/market_intel/api/app.py`
  - Pass comprehensive metadata kwargs to `FastAPI(...)`.

### 4. Airflow DAG Documentation
- **File**: `src/market_intel/pipelines/market_intel_dag.py`
  - Add `doc_md` parameter to the DAG instantiation.

### 5. Makefile Integration
- **File**: `Makefile`
  - Add `docs` target:
    ```makefile
    .PHONY: docs
    docs: ## Serve MkDocs documentation locally
    	.venv/bin/mkdocs serve
    ```

### 6. Automated Tests
- **File**: `tests/unit/test_documentation.py`
  - Verify OpenAPI metadata and MkDocs existence.

### 7. Verification & Quality Gates
```bash
make test-issue ID=24
make check
```

### 8. Git & Issue Finish
```bash
make finish-issue ID=24 MSG="docs: implement mkdocs site, openapi metadata, and dag docs"
```
