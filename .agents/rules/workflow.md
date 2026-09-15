# Agent Workflow Rules — AI-Powered Market Intelligence

## Mandatory Operating Procedures

This document instructs the agent (AI coding assistant) on how to operate
within this repository. These rules are **non-negotiable** and override any
default behavior.

---

## 1. Issue-by-Issue Discipline

- **Never** start work on Issue N+1 without confirming Issue N is fully closed
  in GitHub (`gh issue view <N>` shows `state: CLOSED`).
- Each issue corresponds to exactly one `feature/issue-X-name` branch.
- Keep issues **atomic**: one concern per issue, one PR per issue.

---

## 2. Mandatory Makefile Commands

All git operations **MUST** use the Makefile targets. **Never** run raw
`git branch`, `git merge`, or `git push` manually.

| Action | Command |
|--------|---------|
| Start new issue | `make start-issue ID=X NAME=short-description` |
| Install / update dependencies | `make deps` |
| Run tests for an issue | `make test-issue ID=X` |
| Finish and merge an issue | `make finish-issue ID=X` |
| Close a milestone to main | `make finish-milestone MILESTONE=MX` |

---

## 3. Conventional Commits (MANDATORY)

Every commit message **must** follow this format:

```
<type>(<scope>): <short description>

[optional body]

[optional footer: Closes #X]
```

**Allowed types:**
- `feat:` — new feature or functionality
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — adding or updating tests
- `chore:` — maintenance (deps, config, tooling)
- `refactor:` — code change without new feature or fix
- `perf:` — performance improvement
- `ci:` — CI/CD changes

**Examples:**
```
feat(extractors): add NewsAPI extractor with pagination support
fix(loaders): handle duplicate key constraint on upsert
docs(readme): update architecture diagram for M2
test(nlp): add unit tests for sentiment pipeline
chore(deps): add apache-airflow 2.9 to pyproject.toml
```

---

## 4. Branch Naming Convention

```
feature/issue-X-short-description
fix/issue-X-short-description
```

Where `X` is the GitHub issue number and `short-description` is kebab-case.

---

## 5. Pull Request Rules

- **Base branch:** always `develop` (never `main` directly).
- **Body:** must include `Closes #X` where X is the issue number.
- **Squash merge:** always use squash to keep `develop` history clean.
- **Labels:** add appropriate labels (`feature`, `bug`, `release`, etc.).

---

## 6. Day 0 Golden Rule

During Day 0 (`feature/day-0-setup`):
- Create **empty scaffolding only**: folders, config files, docs.
- **Zero** business logic, extractors, models, DAGs, or API endpoints.
- All Python files contain only module-level docstrings or are empty.

---

## 7. Language

**English only** — all code, variable names, docstrings, commit messages,
issue titles, PR descriptions, and documentation must be written in English.

---

## 8. Issue Tracking File

After completing each issue, update the corresponding tracking document:
- Issue #0 → `docs/issue_0_setup.md`
- Issue #N → `docs/issue_N_<name>.md` (created at issue start)

Mark the checklist item `[x]` and record the PR URL.
