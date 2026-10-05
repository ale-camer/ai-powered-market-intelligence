"""Production-ready asynchronous REST API for market intelligence signals, summaries, and alerts."""

import json
import urllib.parse
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intel.core.config import Settings, get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import (
    AlertItem,
    AlertsResponse,
    CompanySummaryResponse,
    EnrichedSignalSchema,
    HealthResponse,
    SignalsQueryResponse,
)
from market_intel.loaders.models import EnrichedSignalModel

logger = get_logger("market_intel.api")

try:
    from fastapi import FastAPI, HTTPException, Path, Query, status

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


SWAGGER_UI_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>AI-Powered Market Intelligence API - Swagger UI</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
    window.ui = SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
    });
    </script>
</body>
</html>
"""


def generate_openapi_spec(settings: Settings) -> dict[str, object]:
    """Build canonical OpenAPI 3.1.0 specification schema dictionary.

    Args:
        settings: Application settings containing api_title and api_version.

    Returns:
        Full OpenAPI schema as a serializable dictionary.
    """
    return {
        "openapi": "3.1.0",
        "info": {
            "title": settings.api_title,
            "version": settings.api_version,
            "description": (
                "Production REST API for querying enriched signals, "
                "AI-generated summaries, anomaly alerts, and system health."
            ),
        },
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health Check",
                    "description": (
                        "Return service health status, application version, and environment."
                    ),
                    "operationId": "get_health",
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/signals": {
                "get": {
                    "summary": "Query Enriched Signals",
                    "description": (
                        "Paginated query for enriched signals with ticker and type filters."
                    ),
                    "operationId": "get_signals",
                    "parameters": [
                        {
                            "name": "ticker",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Ticker symbol filter (e.g. AAPL)",
                        },
                        {
                            "name": "signal_type",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Signal type filter (e.g. sentiment, anomaly)",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100,
                            },
                            "description": "Maximum number of signals to return (1-100)",
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "default": 0,
                                "minimum": 0,
                            },
                            "description": "Number of records to skip",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SignalsQueryResponse"}
                                }
                            },
                        },
                        "422": {"description": "Validation Error"},
                    },
                }
            },
            "/summary/{ticker}": {
                "get": {
                    "summary": "Get Company Summary",
                    "description": (
                        "Retrieve the latest AI-generated executive summary for a company ticker."
                    ),
                    "operationId": "get_company_summary",
                    "parameters": [
                        {
                            "name": "ticker",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Stock ticker symbol (e.g. AAPL)",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/CompanySummaryResponse"
                                    }
                                }
                            },
                        },
                        "404": {"description": "Company summary not found for ticker"},
                    },
                }
            },
            "/alerts": {
                "get": {
                    "summary": "Get Active Anomaly Alerts",
                    "description": (
                        "Retrieve active statistical and machine-learning anomaly alerts."
                    ),
                    "operationId": "get_alerts",
                    "parameters": [
                        {
                            "name": "ticker",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Optional ticker filter",
                        },
                        {
                            "name": "severity",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Optional severity filter (e.g. high, medium, low)",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100,
                            },
                            "description": "Maximum number of alerts to return (1-100)",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AlertsResponse"}
                                }
                            },
                        },
                        "422": {"description": "Validation Error"},
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": HealthResponse.model_json_schema(),
                "SignalsQueryResponse": SignalsQueryResponse.model_json_schema(),
                "CompanySummaryResponse": CompanySummaryResponse.model_json_schema(),
                "AlertItem": AlertItem.model_json_schema(),
                "AlertsResponse": AlertsResponse.model_json_schema(),
            }
        },
    }


async def fetch_signals(
    session: AsyncSession,
    ticker: str | None = None,
    signal_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[EnrichedSignalModel], int]:
    """Execute filtered and paginated query for enriched signals.

    Args:
        session: Active SQLAlchemy AsyncSession.
        ticker: Optional ticker symbol filter.
        signal_type: Optional signal type filter.
        limit: Maximum number of signals.
        offset: Query offset.

    Returns:
        Tuple of (list of EnrichedSignalModel instances, total count).
    """
    stmt = select(EnrichedSignalModel)
    count_stmt = select(func.count(EnrichedSignalModel.id))

    if ticker:
        norm_ticker = ticker.strip().upper()
        stmt = stmt.where(EnrichedSignalModel.symbol == norm_ticker)
        count_stmt = count_stmt.where(EnrichedSignalModel.symbol == norm_ticker)

    if signal_type:
        norm_type = signal_type.strip().lower()
        stmt = stmt.where(EnrichedSignalModel.signal_type == norm_type)
        count_stmt = count_stmt.where(EnrichedSignalModel.signal_type == norm_type)

    count_res = await session.execute(count_stmt)
    total = count_res.scalar_one_or_none() or 0

    stmt = stmt.order_by(EnrichedSignalModel.timestamp.desc()).offset(offset).limit(limit)
    res = await session.execute(stmt)
    signals = list(res.scalars().all())

    return signals, total


async def fetch_summary(
    session: AsyncSession,
    ticker: str,
) -> EnrichedSignalModel | None:
    """Fetch latest enriched signal with an executive summary for a ticker.

    Args:
        session: Active SQLAlchemy AsyncSession.
        ticker: Stock ticker symbol.

    Returns:
        Matching EnrichedSignalModel or None if not found.
    """
    norm_ticker = ticker.strip().upper()
    stmt = (
        select(EnrichedSignalModel)
        .where(EnrichedSignalModel.symbol == norm_ticker)
        .where(EnrichedSignalModel.summary.is_not(None))
        .where(EnrichedSignalModel.summary != "")
        .order_by(EnrichedSignalModel.timestamp.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def fetch_alerts(
    session: AsyncSession,
    ticker: str | None = None,
    severity: str | None = None,
    limit: int = 20,
) -> list[EnrichedSignalModel]:
    """Fetch active anomaly alert signals.

    Args:
        session: Active SQLAlchemy AsyncSession.
        ticker: Optional ticker symbol filter.
        severity: Optional severity filter.
        limit: Maximum number of alerts.

    Returns:
        List of matching EnrichedSignalModel instances.
    """
    stmt = select(EnrichedSignalModel).where(
        (EnrichedSignalModel.signal_type == "anomaly")
        | (EnrichedSignalModel.signal_type == "alert")
    )

    if ticker:
        norm_ticker = ticker.strip().upper()
        stmt = stmt.where(EnrichedSignalModel.symbol == norm_ticker)

    if severity:
        norm_sev = severity.strip().lower()
        stmt = stmt.where(EnrichedSignalModel.sentiment_label == norm_sev)

    stmt = stmt.order_by(EnrichedSignalModel.timestamp.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def handle_health(
    session_factory: async_sessionmaker[AsyncSession] | None,
    settings: Settings,
) -> HealthResponse:
    """Generate service health check response.

    Args:
        session_factory: Optional database sessionmaker.
        settings: Application settings.

    Returns:
        HealthResponse instance.
    """
    db_status = "idle"
    if session_factory is not None:
        try:
            async with session_factory() as session:
                await session.execute(select(1))
            db_status = "connected"
        except Exception:
            db_status = "unreachable"

    return HealthResponse(
        status="healthy",
        version=settings.api_version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        details={
            "database": db_status,
            "cache": "connected",
        },
    )


async def handle_signals(
    session_factory: async_sessionmaker[AsyncSession] | None,
    ticker: str | None,
    signal_type: str | None,
    limit: int,
    offset: int,
) -> SignalsQueryResponse:
    """Query and return paginated enriched signals.

    Args:
        session_factory: Optional database sessionmaker.
        ticker: Optional ticker symbol filter.
        signal_type: Optional signal type filter.
        limit: Limit on returned records.
        offset: Offset for pagination.

    Returns:
        SignalsQueryResponse instance.
    """
    if session_factory is None:
        return SignalsQueryResponse(items=[], total=0, limit=limit, offset=offset)

    try:
        async with session_factory() as session:
            signals, total = await fetch_signals(
                session=session,
                ticker=ticker,
                signal_type=signal_type,
                limit=limit,
                offset=offset,
            )
            items = [EnrichedSignalSchema.from_orm(sig) for sig in signals]
            return SignalsQueryResponse(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
            )
    except Exception as exc:
        logger.warning(f"Error querying signals: {exc}")
        return SignalsQueryResponse(items=[], total=0, limit=limit, offset=offset)


async def handle_summary(
    session_factory: async_sessionmaker[AsyncSession] | None,
    ticker: str,
) -> CompanySummaryResponse | None:
    """Retrieve company summary response or None if not found.

    Args:
        session_factory: Optional database sessionmaker.
        ticker: Stock ticker symbol.

    Returns:
        CompanySummaryResponse or None if missing.
    """
    if session_factory is None:
        return None

    try:
        async with session_factory() as session:
            sig = await fetch_summary(session, ticker)
            if sig is None or not sig.summary:
                return None

            metrics_data: dict[str, object] = {}
            if sig.sentiment_score is not None:
                metrics_data["sentiment_score"] = sig.sentiment_score
            if sig.sentiment_label:
                metrics_data["sentiment_label"] = sig.sentiment_label
            if sig.confidence is not None:
                metrics_data["confidence"] = sig.confidence

            return CompanySummaryResponse(
                ticker=sig.symbol,
                summary=sig.summary,
                model_used=sig.source_type or "gpt-4o-mini",
                last_updated=sig.timestamp,
                metrics=metrics_data,
            )
    except Exception as exc:
        logger.warning(f"Error querying summary for {ticker}: {exc}")
        return None


async def handle_alerts(
    session_factory: async_sessionmaker[AsyncSession] | None,
    ticker: str | None,
    severity: str | None,
    limit: int,
) -> AlertsResponse:
    """Retrieve active anomaly detection alerts.

    Args:
        session_factory: Optional database sessionmaker.
        ticker: Optional ticker symbol filter.
        severity: Optional severity filter.
        limit: Limit on returned records.

    Returns:
        AlertsResponse instance.
    """
    if session_factory is None:
        return AlertsResponse(items=[], total=0)

    try:
        async with session_factory() as session:
            signals = await fetch_alerts(
                session=session,
                ticker=ticker,
                severity=severity,
                limit=limit,
            )
            alerts: list[AlertItem] = []
            for sig in signals:
                details_dict: dict[str, object] = (
                    sig.entities if isinstance(sig.entities, dict) else {}
                )
                method_name = (
                    str(details_dict.get("method", "zscore")) if details_dict else "zscore"
                )
                sev = sig.sentiment_label or "medium"
                raw_score = details_dict.get("score") if details_dict else None
                score_val = (
                    float(raw_score)
                    if isinstance(raw_score, (int, float))
                    else float(sig.confidence if sig.confidence is not None else 1.0)
                )
                alerts.append(
                    AlertItem(
                        id=sig.id,
                        symbol=sig.symbol,
                        method=method_name,
                        score=score_val,
                        severity=sev,
                        details=details_dict,
                        timestamp=sig.timestamp,
                    )
                )
            return AlertsResponse(items=alerts, total=len(alerts))
    except Exception as exc:
        logger.warning(f"Error querying alerts: {exc}")
        return AlertsResponse(items=[], total=0)


class AppState:
    """Mutable application state container."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        settings: Settings | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize state container with optional keyword arguments."""
        self.session_factory: async_sessionmaker[AsyncSession] | None = session_factory
        self.settings: Settings | None = settings
        self.__dict__.update(kwargs)


class MarketIntelASGIApp:
    """Lightweight, production-grade ASGI REST application for Market Intelligence."""

    def __init__(
        self,
        settings: Settings | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """Initialize MarketIntelASGIApp with settings and session factory.

        Args:
            settings: Optional custom Settings instance.
            session_factory: Optional custom async sessionmaker.
        """
        self.settings = settings or get_settings()
        self.title = self.settings.api_title
        self.version = self.settings.api_version
        self.state = AppState(session_factory=session_factory, settings=self.settings)
        self.dependency_overrides: dict[object, object] = {}
        self._fastapi_app: object = self._init_fastapi() if _HAS_FASTAPI else None

    def _init_fastapi(self) -> object:
        """Configure internal FastAPI instance if package is installed."""
        if not _HAS_FASTAPI:
            return None

        fastapi_inst = FastAPI(
            title=self.title,
            version=self.version,
            docs_url="/docs",
            openapi_url="/openapi.json",
        )
        fastapi_inst.state.session_factory = self.state.session_factory
        fastapi_inst.state.settings = self.settings

        async def get_health() -> HealthResponse:
            active_factory = getattr(self.state, "session_factory", None)
            return await handle_health(active_factory, self.settings)

        async def get_signals(
            ticker: str | None = Query(default=None),
            signal_type: str | None = Query(default=None),
            limit: int = Query(default=20, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
        ) -> SignalsQueryResponse:
            active_factory = getattr(self.state, "session_factory", None)
            return await handle_signals(active_factory, ticker, signal_type, limit, offset)

        async def get_summary(
            ticker: str = Path(..., min_length=1),
        ) -> CompanySummaryResponse:
            active_factory = getattr(self.state, "session_factory", None)
            res = await handle_summary(active_factory, ticker)
            if res is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Company summary not found for ticker '{ticker}'",
                )
            return res

        async def get_alerts(
            ticker: str | None = Query(default=None),
            severity: str | None = Query(default=None),
            limit: int = Query(default=20, ge=1, le=100),
        ) -> AlertsResponse:
            active_factory = getattr(self.state, "session_factory", None)
            return await handle_alerts(active_factory, ticker, severity, limit)

        fastapi_inst.add_api_route(
            "/health",
            get_health,
            methods=["GET"],
            response_model=HealthResponse,
            tags=["Health"],
        )
        fastapi_inst.add_api_route(
            "/signals",
            get_signals,
            methods=["GET"],
            response_model=SignalsQueryResponse,
            tags=["Signals"],
        )
        fastapi_inst.add_api_route(
            "/summary/{ticker}",
            get_summary,
            methods=["GET"],
            response_model=CompanySummaryResponse,
            tags=["Summaries"],
        )
        fastapi_inst.add_api_route(
            "/alerts",
            get_alerts,
            methods=["GET"],
            response_model=AlertsResponse,
            tags=["Alerts"],
        )

        return fastapi_inst

    def openapi(self) -> dict[str, object]:
        """Return the OpenAPI specification dictionary."""
        openapi_fn = getattr(self._fastapi_app, "openapi", None)
        if callable(openapi_fn):
            spec = openapi_fn()
            if isinstance(spec, dict):
                return spec
        return generate_openapi_spec(self.settings)

    async def __call__(
        self,
        scope: dict[str, object],
        receive: object,
        send: object,
    ) -> None:
        """ASGI request handler."""
        if self._fastapi_app is not None and callable(self._fastapi_app):
            await self._fastapi_app(scope, receive, send)
            return

        scope_type = scope.get("type")

        if scope_type == "lifespan":
            if callable(receive) and callable(send):
                while True:
                    message = await receive()
                    msg_type = message.get("type")
                    if msg_type == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif msg_type == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            return

        if scope_type != "http":
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        raw_query = scope.get("query_string", b"")
        query_str = raw_query.decode("utf-8") if isinstance(raw_query, bytes) else str(raw_query)
        query_params = urllib.parse.parse_qs(query_str)

        async def send_response(
            status_code: int,
            body: bytes,
            content_type: str = "application/json",
        ) -> None:
            if callable(send):
                await send(
                    {
                        "type": "http.response.start",
                        "status": status_code,
                        "headers": [
                            (b"content-type", content_type.encode("utf-8")),
                            (b"content-length", str(len(body)).encode("utf-8")),
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": body,
                    }
                )

        if method != "GET":
            err_body = json.dumps({"detail": f"Method {method} Not Allowed"}).encode("utf-8")
            await send_response(405, err_body)
            return

        active_factory = getattr(self.state, "session_factory", None)

        if path == "/health":
            resp = await handle_health(active_factory, self.settings)
            await send_response(200, resp.model_dump_json().encode("utf-8"))
            return

        if path == "/signals":
            ticker = query_params.get("ticker", [None])[0]
            sig_type = query_params.get("signal_type", [None])[0]
            limit_raw = query_params.get("limit", ["20"])[0]
            offset_raw = query_params.get("offset", ["0"])[0]

            try:
                limit = int(limit_raw)
                offset = int(offset_raw)
            except (ValueError, TypeError):
                err = json.dumps(
                    {
                        "detail": [
                            {
                                "loc": ["query", "limit_or_offset"],
                                "msg": "limit and offset must be integers",
                                "type": "type_error.integer",
                            }
                        ]
                    }
                ).encode("utf-8")
                await send_response(422, err)
                return

            if limit < 1 or limit > 100:
                err = json.dumps(
                    {
                        "detail": [
                            {
                                "loc": ["query", "limit"],
                                "msg": "limit must be between 1 and 100",
                                "type": "value_error.number.not_in_range",
                            }
                        ]
                    }
                ).encode("utf-8")
                await send_response(422, err)
                return

            if offset < 0:
                err = json.dumps(
                    {
                        "detail": [
                            {
                                "loc": ["query", "offset"],
                                "msg": "offset must be non-negative",
                                "type": "value_error.number.not_ge",
                            }
                        ]
                    }
                ).encode("utf-8")
                await send_response(422, err)
                return

            signals_resp = await handle_signals(active_factory, ticker, sig_type, limit, offset)
            await send_response(200, signals_resp.model_dump_json().encode("utf-8"))
            return

        if path.startswith("/summary/"):
            ticker_param = path[len("/summary/") :].strip()
            if not ticker_param:
                err = json.dumps({"detail": "Ticker cannot be empty"}).encode("utf-8")
                await send_response(404, err)
                return

            summary_resp = await handle_summary(active_factory, ticker_param)
            if summary_resp is None:
                err = json.dumps(
                    {"detail": f"Company summary not found for ticker '{ticker_param}'"}
                ).encode("utf-8")
                await send_response(404, err)
                return

            await send_response(200, summary_resp.model_dump_json().encode("utf-8"))
            return

        if path == "/alerts":
            ticker = query_params.get("ticker", [None])[0]
            severity = query_params.get("severity", [None])[0]
            limit_raw = query_params.get("limit", ["20"])[0]

            try:
                limit = int(limit_raw)
            except (ValueError, TypeError):
                err = json.dumps(
                    {
                        "detail": [
                            {
                                "loc": ["query", "limit"],
                                "msg": "limit must be an integer",
                                "type": "type_error.integer",
                            }
                        ]
                    }
                ).encode("utf-8")
                await send_response(422, err)
                return

            if limit < 1 or limit > 100:
                err = json.dumps(
                    {
                        "detail": [
                            {
                                "loc": ["query", "limit"],
                                "msg": "limit must be between 1 and 100",
                                "type": "value_error.number.not_in_range",
                            }
                        ]
                    }
                ).encode("utf-8")
                await send_response(422, err)
                return

            alerts_resp = await handle_alerts(active_factory, ticker, severity, limit)
            await send_response(200, alerts_resp.model_dump_json().encode("utf-8"))
            return

        if path == "/openapi.json":
            spec = self.openapi()
            await send_response(200, json.dumps(spec).encode("utf-8"))
            return

        if path == "/docs":
            await send_response(200, SWAGGER_UI_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        err = json.dumps({"detail": "Not Found"}).encode("utf-8")
        await send_response(404, err)


def create_app(
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> MarketIntelASGIApp:
    """Create and return the application instance (FastAPI or ASGI fallback).

    Args:
        settings: Optional custom Settings instance.
        session_factory: Optional database sessionmaker.

    Returns:
        MarketIntelASGIApp instance adhering to the ASGI specification.
    """
    active_settings = settings or get_settings()
    return MarketIntelASGIApp(active_settings, session_factory)


app: MarketIntelASGIApp = create_app()
