"""Security middleware implementing OWASP defensive headers and server banner suppression."""

from collections.abc import Callable
from typing import Any

try:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response

    _HAS_STARLETTE = True
except ImportError:  # pragma: no cover
    _HAS_STARLETTE = False

    class _BaseHTTPMiddlewareFallback:
        def __init__(self, app: object) -> None:
            self.app = app

        async def __call__(
            self,
            scope: dict[str, Any],
            receive: Callable[..., Any],
            send: Callable[..., Any],
        ) -> None:
            pass

    BaseHTTPMiddleware = _BaseHTTPMiddlewareFallback
    RequestResponseEndpoint = Any
    Request = Any
    Response = Any


DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'"
DEFAULT_PERMISSIONS_POLICY = "geolocation=(), camera=(), microphone=()"
DEFAULT_REFERRER_POLICY = "strict-origin-when-cross-origin"
DEFAULT_HSTS_MAX_AGE = 31536000


class SecurityHeadersMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Middleware enforcing enterprise-grade OWASP HTTP security headers.

    Injects:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), camera=(), microphone=()

    Suppresses:
    - Server
    - X-Powered-By
    """

    def __init__(
        self,
        app: object,
        content_security_policy: str = DEFAULT_CSP,
        enable_hsts: bool = True,
        hsts_max_age: int = DEFAULT_HSTS_MAX_AGE,
        hsts_include_subdomains: bool = True,
        referrer_policy: str = DEFAULT_REFERRER_POLICY,
        permissions_policy: str = DEFAULT_PERMISSIONS_POLICY,
    ) -> None:
        """Initialize security headers middleware.

        Args:
            app: Wrapped ASGI application.
            content_security_policy: CSP header directive string.
            enable_hsts: Whether to inject Strict-Transport-Security.
            hsts_max_age: Lifetime in seconds for HSTS cache.
            hsts_include_subdomains: Whether to append includeSubDomains.
            referrer_policy: Referrer-Policy value.
            permissions_policy: Permissions-Policy value.
        """
        if _HAS_STARLETTE and issubclass(BaseHTTPMiddleware, object):
            super().__init__(app)
        self.app = app

        self.content_security_policy = content_security_policy
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy

    def _build_hsts_header(self) -> str:
        """Construct Strict-Transport-Security header value."""
        header = f"max-age={self.hsts_max_age}"
        if self.hsts_include_subdomains:
            header += "; includeSubDomains"
        return header

    def apply_security_headers_to_dict(self, headers_dict: dict[str, str]) -> None:
        """Mutate a dictionary of HTTP headers with defensive values."""
        headers_dict["X-Content-Type-Options"] = "nosniff"
        headers_dict["X-Frame-Options"] = "DENY"
        headers_dict["X-XSS-Protection"] = "1; mode=block"
        headers_dict["Content-Security-Policy"] = self.content_security_policy
        headers_dict["Referrer-Policy"] = self.referrer_policy
        headers_dict["Permissions-Policy"] = self.permissions_policy

        if self.enable_hsts:
            headers_dict["Strict-Transport-Security"] = self._build_hsts_header()

        for suppressed in ("server", "Server", "x-powered-by", "X-Powered-By"):
            if suppressed in headers_dict:
                del headers_dict[suppressed]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Intercept Starlette/FastAPI request and append security headers to response."""
        response: Response = await call_next(request)

        # Enforce defensive headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = self.content_security_policy
        response.headers["Referrer-Policy"] = self.referrer_policy
        response.headers["Permissions-Policy"] = self.permissions_policy

        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = self._build_hsts_header()

        # Strip server banners to prevent fingerprinting
        for suppressed in ("server", "Server", "x-powered-by", "X-Powered-By"):
            if suppressed in response.headers:
                del response.headers[suppressed]

        return response

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        """Pure ASGI middleware invocation handler."""
        if _HAS_STARLETTE:
            await super().__call__(scope, receive, send)
            return

        if scope.get("type") != "http":
            if callable(self.app):
                await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                # Remove suppressed headers
                filtered = [
                    (k, v) for k, v in raw_headers if k.lower() not in (b"server", b"x-powered-by")
                ]
                # Append security headers
                filtered.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-xss-protection", b"1; mode=block"),
                        (b"strict-transport-security", self._build_hsts_header().encode("ascii")),
                        (b"content-security-policy", self.content_security_policy.encode("utf-8")),
                        (b"referrer-policy", self.referrer_policy.encode("ascii")),
                        (b"permissions-policy", self.permissions_policy.encode("ascii")),
                    ]
                )
                message = dict(message)
                message["headers"] = filtered
            await send(message)

        if callable(self.app):
            await self.app(scope, receive, send_wrapper)
