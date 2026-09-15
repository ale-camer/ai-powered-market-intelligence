# Issue #0 — Day 0 Setup Tracking

**Branch:** `feature/day-0-setup`
**PR:** _(to be filled when merged)_
**Status:** 🟡 In Progress

---

## Day 0 Checklist

### Git Flow (PASO CERO)
- [x] `git init` on `main` with empty commit
- [x] `develop` branch created from `main`
- [x] `feature/day-0-setup` branch created from `develop`

### Virtual Environment
- [x] `.venv` created with Python 3.12+ (`python3 -m venv .venv`)
- [ ] `.venv` verified: `.venv/bin/python --version` shows ≥ 3.12

### Configuration Files
- [x] `.gitignore` created (Python, venv, IDE, Airflow, Terraform, secrets)
- [x] `.env.example` created (all required environment variables)
- [x] `pyproject.toml` created (build system, dev extras, ruff, mypy, pytest)

### Folder Structure (empty, with .gitkeep)
- [x] `src/market_intel/extractors/`
- [x] `src/market_intel/transformers/`
- [x] `src/market_intel/loaders/`
- [x] `src/market_intel/pipelines/`
- [x] `src/market_intel/api/`
- [x] `src/market_intel/core/`
- [x] `tests/unit/`
- [x] `tests/integration/`
- [x] `tests/e2e/`
- [x] `infra/docker/`
- [x] `infra/terraform/`
- [x] `infra/k8s/`
- [x] `docs/`

### Makefile Lifecycle Commands
- [x] `make start-issue ID=X NAME=...` — creates `feature/issue-X-name` from `develop`
- [x] `make deps` — installs `pip install -e ".[dev]"`
- [x] `make test-issue ID=X` — runs `pytest -m "issue_X"`
- [x] `make finish-issue ID=X` — push → PR with `Closes #X` → merge → cleanup
- [x] `make finish-milestone MILESTONE=MX` — merges `develop` → `main` via PR

### Agent Rules
- [x] `.agents/rules/workflow.md` created

### Documentation
- [x] `README.md` draft with architecture overview and milestones table
- [x] `docs/issue_0_setup.md` (this file)

### GitHub Remote
- [ ] Repo created: `gh repo create ale-camer/ai-powered-market-intelligence --public`
- [ ] Initial branches pushed: `main`, `develop`, `feature/day-0-setup`
- [ ] 5 milestones created (M1–M5)
- [ ] 25 issues created (atomic, assigned to milestones)
- [ ] PR `feature/day-0-setup` → `develop` opened
- [ ] PR merged → branch deleted
- [ ] `develop` fast-forward merged to `main` (via `finish-milestone`)

---

## Architecture Decision Records

| Decision | Rationale |
|----------|-----------|
| Python 3.12+ | Latest stable, best performance, improved typing |
| Apache Airflow 2.9 | Enterprise-standard orchestration, rich ecosystem |
| PostgreSQL + pgvector | Unified relational + vector search, avoids extra service |
| Redis 7 | In-memory dedup cache, Celery broker |
| FastAPI | High-performance async API framework |
| Ruff | 10–100× faster than flake8+isort+pyupgrade combined |

---

## Notes

> **Day 0 golden rule**: Zero business logic was written in this issue.
> All source files contain only empty `__init__.py` stubs or `.gitkeep` files.
> Business logic will be implemented starting from Issue #1.
