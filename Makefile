# ============================================================
# AI-Powered Market Intelligence — Project Makefile
# All git operations MUST go through these targets.
# NEVER run git branch/merge/push manually.
# ============================================================

SHELL := /bin/bash
PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ──────────────────────────────────────────────────────────────────────────────
# Environment
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: venv
venv: ## Create the Python virtual environment
	python3 -m venv .venv
	$(PIP) install --upgrade pip setuptools wheel

.PHONY: deps
deps: ## Install all dependencies from pyproject.toml (including dev extras)
	$(PIP) install -e ".[dev]"

.PHONY: deps-all
deps-all: ## Install ALL optional dependency groups
	$(PIP) install -e ".[all,dev]"

# ──────────────────────────────────────────────────────────────────────────────
# Code quality
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Run ruff linter
	.venv/bin/ruff check src/ tests/

.PHONY: format
format: ## Run ruff formatter
	.venv/bin/ruff format src/ tests/

.PHONY: typecheck
typecheck: ## Run mypy type checker
	.venv/bin/mypy src/

.PHONY: check
check: lint typecheck ## Run all static analysis

# ──────────────────────────────────────────────────────────────────────────────
# Testing
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Run the full test suite
	.venv/bin/pytest tests/ --cov=src --cov-report=term-missing

.PHONY: test-unit
test-unit: ## Run only unit tests
	.venv/bin/pytest tests/unit/ -m unit

.PHONY: test-integration
test-integration: ## Run only integration tests
	.venv/bin/pytest tests/integration/ -m integration

.PHONY: test-issue
test-issue: ## Run tests for a specific issue: make test-issue ID=X
ifndef ID
	$(error ID is required. Usage: make test-issue ID=<issue-number>)
endif
	.venv/bin/pytest tests/ -m "issue_$(ID)" -v

# ──────────────────────────────────────────────────────────────────────────────
# Git Flow — Issue Lifecycle  ← THESE ARE THE MANDATORY COMMANDS
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: start-issue
start-issue: ## Start a new issue branch from develop: make start-issue ID=X NAME=short-description
ifndef ID
	$(error ID is required. Usage: make start-issue ID=<issue-number> NAME=<short-description>)
endif
ifndef NAME
	$(error NAME is required. Usage: make start-issue ID=<issue-number> NAME=<short-description>)
endif
	git fetch origin
	git checkout develop
	git pull origin develop
	git checkout -b feature/issue-$(ID)-$(NAME)
	@echo "✅ Branch feature/issue-$(ID)-$(NAME) created from develop"

.PHONY: finish-issue
finish-issue: ## Push branch, open PR with Closes #ID, merge to develop, delete branch: make finish-issue ID=X
ifndef ID
	$(error ID is required. Usage: make finish-issue ID=<issue-number>)
endif
	$(eval BRANCH := $(shell git rev-parse --abbrev-ref HEAD))
	git push -u origin $(BRANCH)
	gh pr create \
		--base develop \
		--head $(BRANCH) \
		--title "$(BRANCH)" \
		--body "Closes #$(ID)" \
		--label "auto-merge"
	gh pr merge --squash --delete-branch --admin
	git checkout develop
	git pull origin develop
	git branch -D $(BRANCH) 2>/dev/null || true
	@echo "✅ Issue #$(ID) merged to develop. Branch $(BRANCH) deleted."

.PHONY: finish-milestone
finish-milestone: ## Merge develop into main via PR to close a milestone: make finish-milestone MILESTONE=M1
ifndef MILESTONE
	$(error MILESTONE is required. Usage: make finish-milestone MILESTONE=<milestone-label>)
endif
	git fetch origin
	git checkout main
	git pull origin main
	gh pr create \
		--base main \
		--head develop \
		--title "Release milestone $(MILESTONE)" \
		--body "Merges all issues from milestone $(MILESTONE) into production." \
		--label "release"
	gh pr merge --merge --admin
	git checkout develop
	git pull origin develop
	@echo "✅ Milestone $(MILESTONE) merged to main."

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml
	@echo "✅ Workspace cleaned."
