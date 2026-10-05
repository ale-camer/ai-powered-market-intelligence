"""Unit tests for security hardening, OWASP headers, and SAST tooling (Issue #23)."""

import pathlib
import tomllib
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from market_intel.api.app import MarketIntelASGIApp, create_app
from market_intel.api.security_middleware import (
    DEFAULT_CSP,
    DEFAULT_HSTS_MAX_AGE,
    DEFAULT_PERMISSIONS_POLICY,
    DEFAULT_REFERRER_POLICY,
    SecurityHeadersMiddleware,
)
from market_intel.core.config import Settings
from market_intel.core.security import (
    constant_time_compare,
    create_access_token,
    verify_access_token,
)
from market_intel.loaders.database import Base, get_async_session_factory
from market_intel.loaders.models import EnrichedSignalModel


@pytest.fixture
async def test_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create in-memory SQLite database for security endpoint tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_async_session_factory(engine)
    async with factory() as session:
        sig = EnrichedSignalModel(
            id=uuid.uuid4(),
            source_type="article",
            symbol="AAPL",
            signal_type="sentiment",
            sentiment_score=0.91,
            sentiment_label="bullish",
            confidence=0.95,
            summary="Apple expands enterprise security architecture.",
            entities={"tickers": ["AAPL"]},
            timestamp=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        )
        session.add(sig)
        await session.commit()

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def app_instance(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> MarketIntelASGIApp:
    """Provide MarketIntelASGIApp instance bound to test database."""
    test_settings = Settings(
        app_env="test",
        secret_key="ci-test-secret-key-at-least-32-chars-long",
        cors_allowed_origins=["http://localhost:3000", "https://app.marketintel.local"],
        cors_allow_credentials=True,
    )
    return create_app(settings=test_settings, session_factory=test_session_factory)


@pytest.fixture
async def client(app_instance: MarketIntelASGIApp) -> httpx.AsyncClient:
    """Provide httpx AsyncClient configured with ASGITransport."""
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


# ──────────────────────────────────────────────────────────────────────────────
# OWASP Defensive Security Headers & Banner Stripping
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.issue_23
async def test_security_headers_injected_on_health_and_signals(
    client: httpx.AsyncClient,
) -> None:
    """Validate OWASP defensive headers injected across multiple endpoints."""
    endpoints = ["/health", "/signals", "/metrics"]

    for endpoint in endpoints:
        response = await client.get(endpoint)
        assert response.status_code == 200, f"Failed for endpoint {endpoint}"

        headers = response.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert headers.get("Content-Security-Policy") == DEFAULT_CSP
        assert headers.get("Referrer-Policy") == DEFAULT_REFERRER_POLICY
        assert headers.get("Permissions-Policy") == DEFAULT_PERMISSIONS_POLICY
        assert (
            headers.get("Strict-Transport-Security")
            == f"max-age={DEFAULT_HSTS_MAX_AGE}; includeSubDomains"
        )


@pytest.mark.unit
@pytest.mark.issue_23
async def test_server_banner_suppressed(client: httpx.AsyncClient) -> None:
    """Validate Server and X-Powered-By banners are suppressed to prevent fingerprinting."""
    response = await client.get("/health")
    assert response.status_code == 200

    lower_keys = [k.lower() for k in response.headers]
    assert "server" not in lower_keys
    assert "x-powered-by" not in lower_keys


@pytest.mark.unit
@pytest.mark.issue_23
async def test_security_headers_middleware_direct_asgi() -> None:
    """Validate SecurityHeadersMiddleware direct ASGI wrapper behavior."""

    async def dummy_app(scope: dict[str, Any], receive: object, send: object) -> None:
        if scope["type"] == "http" and callable(send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/plain"),
                        (b"server", b"vuln-banner/1.0"),
                        (b"x-powered-by", b"test-framework"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"secure-ok"})

    middleware = SecurityHeadersMiddleware(dummy_app)
    transport = httpx.ASGITransport(app=middleware)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        resp = await test_client.get("/test")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "server" not in [k.lower() for k in resp.headers]
        assert "x-powered-by" not in [k.lower() for k in resp.headers]


@pytest.mark.unit
@pytest.mark.issue_23
def test_security_headers_middleware_custom_configuration() -> None:
    """Validate custom CSP, HSTS, and referrer settings in SecurityHeadersMiddleware."""
    middleware = SecurityHeadersMiddleware(
        app=lambda scope, rec, snd: None,
        content_security_policy="default-src 'none'",
        enable_hsts=False,
        referrer_policy="no-referrer",
        permissions_policy="camera=()",
    )

    headers_dict: dict[str, str] = {"server": "apache", "custom-header": "test"}
    middleware.apply_security_headers_to_dict(headers_dict)

    assert headers_dict["Content-Security-Policy"] == "default-src 'none'"
    assert headers_dict["Referrer-Policy"] == "no-referrer"
    assert headers_dict["Permissions-Policy"] == "camera=()"
    assert "Strict-Transport-Security" not in headers_dict
    assert "server" not in headers_dict
    assert headers_dict["custom-header"] == "test"


# ──────────────────────────────────────────────────────────────────────────────
# CORS Security Hardening
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.issue_23
async def test_cors_policy_allowed_origin(client: httpx.AsyncClient) -> None:
    """Validate allowed CORS origin receives credentials and origin headers."""
    response = await client.options(
        "/signals",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


@pytest.mark.unit
@pytest.mark.issue_23
async def test_cors_policy_disallowed_origin(client: httpx.AsyncClient) -> None:
    """Validate unauthorized CORS origin is not granted Access-Control-Allow-Origin."""
    response = await client.options(
        "/signals",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Disallowed origin does not receive Access-Control-Allow-Origin
    assert response.headers.get("Access-Control-Allow-Origin") is None


@pytest.mark.unit
@pytest.mark.issue_23
def test_cors_wildcard_with_credentials_rejected() -> None:
    """Validate CORS wildcard '*' origin with credentials enabled raises ValueError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            cors_allowed_origins=["*"],
            cors_allow_credentials=True,
        )
    assert "Disallowed wildcard '*' origin when cors_allow_credentials=True" in str(exc_info.value)

    # Allowed when credentials are disabled
    valid = Settings(
        cors_allowed_origins=["*"],
        cors_allow_credentials=False,
    )
    assert "*" in valid.cors_allowed_origins


@pytest.mark.unit
@pytest.mark.issue_23
def test_cors_origins_normalization() -> None:
    """Validate normalization of CORS origins from comma-separated strings or JSON arrays."""
    # Comma-separated string
    s1 = Settings(cors_allowed_origins="http://a.com, http://b.com")
    assert s1.cors_allowed_origins == ["http://a.com", "http://b.com"]

    # JSON array string
    s2 = Settings(cors_allowed_origins='["http://c.com", "http://d.com"]')
    assert s2.cors_allowed_origins == ["http://c.com", "http://d.com"]


# ──────────────────────────────────────────────────────────────────────────────
# Production Secret Key Validation & Hardening
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.issue_23
def test_production_weak_secret_key_rejected() -> None:
    """Validate production environment rejects weak, short, or placeholder secrets."""
    weak_candidates = [
        "change-me",
        "change-me-in-production",
        "secret",
        "password",
        "admin",
        "test",
        "short-key",
        "12345678",
        "a" * 31,  # Under 32 characters
        "a" * 20 + "change-me" + "a" * 10,  # Contains weak placeholder substring
    ]

    for weak_key in weak_candidates:
        with pytest.raises(ValidationError) as exc_info:
            Settings(app_env="production", secret_key=weak_key)
        err_msg = str(exc_info.value)
        assert "Production security error: SECRET_KEY" in err_msg, f"Expected error for {weak_key}"

    # Valid production secret
    secure_key = "prod-super-secure-cryptographic-secret-key-9999"
    prod_settings = Settings(app_env="production", secret_key=secure_key)
    assert prod_settings.secret_key == secure_key

    # In development or test, weak secrets are permitted
    dev_settings = Settings(app_env="development", secret_key="change-me")
    assert dev_settings.secret_key == "change-me"


# ──────────────────────────────────────────────────────────────────────────────
# Timing-Attack Resilience & HMAC Operations
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.issue_23
def test_constant_time_comparison() -> None:
    """Validate constant_time_compare for timing-safe equality comparison."""
    # Strings
    assert constant_time_compare("secret_token_123", "secret_token_123") is True
    assert constant_time_compare("secret_token_123", "secret_token_124") is False
    assert constant_time_compare("secret_token_123", "short") is False

    # Bytes
    assert constant_time_compare(b"hash_val_bytes", b"hash_val_bytes") is True
    assert constant_time_compare(b"hash_val_bytes", b"hash_val_byteX") is False


@pytest.mark.unit
@pytest.mark.issue_23
def test_jwt_token_tamper_resilience() -> None:
    """Validate token verification rejects tampered signatures and payloads."""
    secret = "test-secret-key-for-jwt-tampering-checks-123456"
    token = create_access_token({"sub": "user_123", "role": "admin"}, secret_key=secret)

    # Valid token decodes correctly
    claims = verify_access_token(token, secret_key=secret)
    assert claims is not None
    assert claims["sub"] == "user_123"

    # Tampered signature segment
    parts = token.split(".")
    tampered_sig = parts[0] + "." + parts[1] + ".invalidSig=="
    assert verify_access_token(tampered_sig, secret_key=secret) is None

    # Tampered payload segment
    tampered_payload = parts[0] + ".eyJzdWIiOiAiaGFja2VkIn0." + parts[2]
    assert verify_access_token(tampered_payload, secret_key=secret) is None

    # Wrong secret key
    assert verify_access_token(token, secret_key="wrong-secret-key-abcdef") is None


# ──────────────────────────────────────────────────────────────────────────────
# Security Tooling Configurations (Bandit, Gitleaks, Workflow, Makefile)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.issue_23
def test_bandit_configuration_file() -> None:
    """Validate bandit.yaml exists and contains required SAST configuration."""
    config_path = pathlib.Path("bandit.yaml")
    assert config_path.is_file(), "bandit.yaml must exist in repository root"

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "exclude_dirs" in data
    assert ".venv" in data["exclude_dirs"]
    assert "tests" in data["exclude_dirs"]
    assert "skips" in data
    assert "B101" in data["skips"]


@pytest.mark.unit
@pytest.mark.issue_23
def test_gitleaks_configuration_file() -> None:
    """Validate .gitleaks.toml exists and defines detection rules and allowlist."""
    config_path = pathlib.Path(".gitleaks.toml")
    assert config_path.is_file(), ".gitleaks.toml must exist in repository root"

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    assert "rules" in data
    rule_ids = {r["id"] for r in data["rules"]}
    assert "openai-api-key" in rule_ids
    assert "generic-api-key" in rule_ids
    assert "unencrypted-private-key" in rule_ids

    assert "allowlist" in data
    assert "paths" in data["allowlist"]
    assert "regexes" in data["allowlist"]


@pytest.mark.unit
@pytest.mark.issue_23
def test_security_workflow_schema() -> None:
    """Validate .github/workflows/security.yml structure and job definitions."""
    workflow_path = pathlib.Path(".github/workflows/security.yml")
    assert workflow_path.is_file(), "security.yml workflow must exist"

    with open(workflow_path, encoding="utf-8") as f:
        workflow = yaml.safe_load(f)

    triggers = workflow.get("on") or workflow.get(True) or {}
    assert "pull_request" in triggers
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers

    jobs = workflow.get("jobs", {})
    assert "sast-bandit" in jobs
    assert "dependency-audit" in jobs
    assert "secret-scan" in jobs
    assert "docker-trivy" in jobs


@pytest.mark.unit
@pytest.mark.issue_23
def test_makefile_security_target() -> None:
    """Validate Makefile contains security target running bandit."""
    makefile_path = pathlib.Path("Makefile")
    assert makefile_path.is_file()

    content = makefile_path.read_text(encoding="utf-8")
    assert ".PHONY: security" in content
    assert "security:" in content
    assert "bandit" in content
