# Issue 23: Security Hardening, SAST, Secrets Scanning, and Vulnerability Auditing

**Branch:** `feature/issue-23-security-hardening`  
**Status:** Planned  
**PR:** TBD  
**Milestone:** M5 — Quality, Security & Release  

---

## Objective

Establish an enterprise-grade defense-in-depth security architecture for the AI-Powered Market Intelligence platform. Implement OWASP-aligned HTTP security headers and CORS hardening middleware, enforce strict secret validation preventing production deployment with default credentials, integrate automated Static Application Security Testing (SAST via Bandit), configure automated secret leak detection (Gitleaks configuration), establish dependency vulnerability auditing (`pip-audit`), and define a dedicated GitHub Actions security workflow (`.github/workflows/security.yml`). Provide comprehensive unit tests under `@pytest.mark.issue_23` verifying header injection, secret rejection, and security scanner configurations.

---

## Acceptance Criteria

- [ ] **OWASP Security Headers & Middleware (`src/market_intel/api/security_middleware.py` & `src/market_intel/api/app.py`)**:
  - Middleware injecting standard defensive headers across all HTTP responses:
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: DENY`
    - `X-XSS-Protection: 1; mode=block`
    - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (when HTTPS / production)
    - `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - `Permissions-Policy: geolocation=(), camera=(), microphone=()`
  - Explicit server header stripping/masking preventing server banner fingerprinting.
  - Safe CORS policy with configurable allowed origins (disallowing wildcard `*` with credentials).
- [ ] **Secret Key & Production Security Validation (`src/market_intel/core/config.py` & `src/market_intel/core/security.py`)**:
  - Runtime validation in `Settings` rejecting placeholder or weak `SECRET_KEY` (e.g., `change-me`, `secret`, `password`, or keys under 32 characters) when `APP_ENV=production`.
  - Constant-time HMAC comparison preventing timing attacks during token verification.
- [ ] **SAST (Static Application Security Testing) Configuration (`bandit.yaml`)**:
  - Bandit configuration file defining test exclusions, severity thresholds (Medium/High), and custom rule options.
  - Integrated into developer tooling and CI workflows.
- [ ] **Secrets Leak Prevention (`.gitleaks.toml`)**:
  - Gitleaks configuration with rules detecting API tokens (OpenAI, NewsAPI, Alpha Vantage, Reddit, AWS, GitHub, Slack) and cryptographic keys (`.pem`, `.key`).
  - Whitelist/allowlist rules for test vectors and mock values.
- [ ] **Dedicated GitHub Actions Security Workflow (`.github/workflows/security.yml`)**:
  - Automated weekly cron and pull-request scanning pipeline:
    - SAST scan with Bandit.
    - Dependency vulnerability audit with `pip-audit`.
    - Secrets detection scan with Gitleaks.
    - Container vulnerability scan with Trivy.
- [ ] **Developer Ergonomics & Makefile (`Makefile`)**:
  - Target `make security`: runs local SAST inspection (Bandit), secret leak detection, and dependency auditing.
- [ ] **Automated Test Suite (`tests/unit/test_security_hardening.py`)**:
  - Unit tests under `@pytest.mark.unit` and `@pytest.mark.issue_23`:
    - Validates presence and values of OWASP security headers on API responses (`/health`, `/signals`, `/metrics`).
    - Validates CORS restrictions and origin handling.
    - Validates production environment rejection of weak or placeholder secret keys.
    - Validates Bandit configuration syntax and rules.
    - Validates `.gitleaks.toml` configuration structure.
    - Validates `.github/workflows/security.yml` syntax and job definitions.
    - Validates Makefile `security` target.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=23 NAME=security-hardening
```

### 2. Security Headers & Middleware Hardening
- **File**: `src/market_intel/api/security_middleware.py`
  - Implement `SecurityHeadersMiddleware(BaseHTTPMiddleware)`:
    - Injects `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy`, and `Permissions-Policy`.
    - Removes `Server` or `X-Powered-By` headers.
- **File**: `src/market_intel/api/app.py`
  - Register `SecurityHeadersMiddleware`.
  - Configure `CORSMiddleware` with secure defaults from `Settings`.

### 3. Core Secret Validation & Timing-Attack Resilience
- **File**: `src/market_intel/core/config.py`
  - Add validator on `secret_key` in `Settings`:
    - If `app_env == "production"`, enforce minimum 32 characters and reject common weak default strings (`change-me`, `secret`, `admin`, `password`).
- **File**: `src/market_intel/core/security.py`
  - Ensure constant-time comparison via `hmac.compare_digest` in all token and signature checks.

### 4. SAST & Secrets Detection Tooling Configurations
- **File**: `bandit.yaml`
  - Configure Bandit with profile: skip tests folder, target `src/`, report Medium/High severity.
- **File**: `.gitleaks.toml`
  - Configure Gitleaks detection rules and entropy thresholds for high-entropy secrets and provider API keys.
- **File**: `pyproject.toml`
  - Add `bandit>=1.7.8` and `pip-audit>=2.7.3` to optional `[project.optional-dependencies] dev` group if not present.

### 5. Automated Security CI Pipeline
- **File**: `.github/workflows/security.yml`
  - Triggers on PRs to `develop`/`main` and scheduled weekly cron (`0 4 * * 1`).
  - Jobs:
    - `sast-bandit`: Runs Bandit SAST scanner on `src/`.
    - `dependency-audit`: Runs `pip-audit` checking known CVEs.
    - `secret-scan`: Runs `gitleaks` container action.
    - `docker-trivy`: Scans Dockerfile with Trivy for image CVEs.

### 6. Makefile Integration
- **File**: `Makefile`
  - Add `security` target:
    ```makefile
    .PHONY: security
    security: ## Run SAST security scan and dependency vulnerability audit
    	.venv/bin/bandit -c bandit.yaml -r src/
    ```

### 7. Automated Unit & Hardening Tests
- **File**: `tests/unit/test_security_hardening.py`
  - Tests marked `@pytest.mark.unit` and `@pytest.mark.issue_23`:
    - `test_security_headers_injected_on_all_responses`: Verifies headers on `/health`, `/signals`.
    - `test_server_header_removed`: Verifies server header is suppressed.
    - `test_production_weak_secret_key_rejected`: Verifies ValueError when `APP_ENV=production` with weak secret.
    - `test_constant_time_token_verification`: Verifies `hmac.compare_digest` resilience.
    - `test_bandit_and_gitleaks_config_files`: Verifies existence and syntax of `bandit.yaml` and `.gitleaks.toml`.
    - `test_security_workflow_schema`: Verifies `.github/workflows/security.yml` structure.
    - `test_makefile_security_target`: Verifies `security` target in `Makefile`.

### 8. Verification & Quality Gates
```bash
make test-issue ID=23
.venv/bin/pytest tests/ --cov=src --cov-fail-under=80
make check
```

### 9. Git & Issue Finish
```bash
make finish-issue ID=23 MSG="feat(security): implement OWASP security headers, SAST scanning, and secret validation"
```
