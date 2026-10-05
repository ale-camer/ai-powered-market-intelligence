"""Celery async task workers, exponential retry logic, and Dead Letter Queue (DLQ).

Configures Celery application with Redis message broker and PostgreSQL result backend,
defines asynchronous tasks for article enrichment, vector embedding generation, and
real-time market alert broadcasting, and routes failed tasks to a Dead Letter Queue.
"""

import asyncio
import json
import traceback
import uuid
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, datetime
from typing import Any, cast

from market_intel.core.config import Settings, get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import NERResult, SentimentResult
from market_intel.transformers.embeddings import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DocumentTransformer,
    count_tokens,
)
from market_intel.transformers.ner import FinancialNERExtractor
from market_intel.transformers.sentiment import SentimentAnalyzer

logger = get_logger("market_intel.core.celery")

# In-memory storage of routed DLQ failure messages for auditing and testing
_DLQ_MESSAGES: list[dict[str, object]] = []


class MaxRetriesExceededError(Exception):
    """Raised when a Celery task has exceeded its maximum retry limit."""


def calculate_backoff_delay(
    retries: int,
    base_delay: int = 60,
    factor: int = 2,
    max_delay: int = 600,
) -> int:
    """Calculate exponential backoff delay based on retry attempt index.

    Progression:
        - attempt 0: base_delay * (2^0) = 60s
        - attempt 1: base_delay * (2^1) = 120s
        - attempt 2: base_delay * (2^2) = 240s
        - capped at max_delay (default: 600s)

    Args:
        retries: Number of retries already performed (>= 0).
        base_delay: Initial retry delay in seconds.
        factor: Exponential multiplier base (default: 2).
        max_delay: Maximum permissible delay in seconds.

    Returns:
        Delay in seconds to wait before next retry.
    """
    safe_retries = max(0, retries)
    computed = int(base_delay * (factor**safe_retries))
    return min(max_delay, computed)


def get_dlq_messages() -> list[dict[str, object]]:
    """Return all recorded Dead Letter Queue failure payloads."""
    return list(_DLQ_MESSAGES)


def clear_dlq() -> None:
    """Clear recorded Dead Letter Queue failure payloads."""
    _DLQ_MESSAGES.clear()


def route_to_dlq(
    task_id: str,
    task_name: str,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    exc: Exception | None = None,
    traceback_str: str | None = None,
    queue_name: str | None = None,
) -> dict[str, object]:
    """Route a permanently failed task to the Dead Letter Queue (DLQ).

    Args:
        task_id: Unique identifier of failed task.
        task_name: Registered name of task.
        args: Positional arguments provided to task.
        kwargs: Keyword arguments provided to task.
        exc: Exception instance that caused permanent failure.
        traceback_str: Optional formatted traceback string.
        queue_name: Name of DLQ target queue.

    Returns:
        Structured DLQ failure dictionary.
    """
    settings = get_settings()
    target_queue = queue_name or settings.celery_dlq_name

    tb = traceback_str
    if tb is None and exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    dlq_payload: dict[str, object] = {
        "task_id": task_id,
        "task_name": task_name,
        "args": list(args),
        "kwargs": dict(kwargs),
        "exception_type": type(exc).__name__ if exc is not None else None,
        "exception_message": str(exc) if exc is not None else None,
        "traceback": tb,
        "timestamp": datetime.now(UTC).isoformat(),
        "queue": target_queue,
    }

    _DLQ_MESSAGES.append(dlq_payload)
    logger.error(
        "Task %s [%s] permanently failed and routed to DLQ [%s]: %s",
        task_name,
        task_id,
        target_queue,
        exc,
    )
    return dlq_payload


# ──────────────────────────────────────────────────────────────────────────────
# Celery Detection & Fallback Layer
# ──────────────────────────────────────────────────────────────────────────────

try:
    from celery import Celery as _CeleryClass
    from celery import Task as _TaskBase
    from kombu import Exchange as _KombuExchange
    from kombu import Queue as _KombuQueue

    _HAS_CELERY = True
except ImportError:
    _CeleryClass = None
    _TaskBase = object
    _KombuExchange = None
    _KombuQueue = None
    _HAS_CELERY = False


class TaskRequestShim:
    """Mock Celery task request context."""

    def __init__(
        self,
        task_id: str | None = None,
        retries: int = 0,
        args: tuple[object, ...] | None = None,
        kwargs: dict[str, object] | None = None,
    ) -> None:
        """Initialize mock task request context."""
        self.id = task_id or str(uuid.uuid4())
        self.retries = retries
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.delivery_info: dict[str, object] = {"routing_key": "celery"}


class AsyncResultShim:
    """Mock Celery AsyncResult tracking task outcome."""

    def __init__(
        self,
        task_id: str,
        result: object = None,
        status: str = "SUCCESS",
        exc: Exception | None = None,
    ) -> None:
        """Initialize AsyncResult shim."""
        self.id = task_id
        self.result = result
        self.status = status
        self._exc = exc

    def get(self, timeout: float | None = None) -> object:
        """Return synchronous result or raise error if task failed."""
        _ = timeout
        if self._exc is not None:
            raise self._exc
        return self.result

    def successful(self) -> bool:
        """Check if task completed successfully."""
        return self.status == "SUCCESS"

    def failed(self) -> bool:
        """Check if task failed."""
        return self.status == "FAILURE"


class CeleryTaskShim:
    """Lightweight shim replicating Celery task execution, binding, retries, and DLQ."""

    def __init__(
        self,
        fn: object,
        name: str,
        bind: bool = True,
        max_retries: int = 3,
        default_retry_delay: int = 60,
        retry_backoff: bool = True,
    ) -> None:
        """Initialize Celery task shim."""
        self.fn = fn
        self.name = name
        self.bind = bind
        self.max_retries = max_retries
        self.default_retry_delay = default_retry_delay
        self.retry_backoff = retry_backoff
        self.request = TaskRequestShim()

    def __call__(self, *args: object, **kwargs: object) -> object:
        """Direct synchronous invocation."""
        if not callable(self.fn):
            return None
        if self.bind:
            return self.fn(self, *args, **kwargs)
        return self.fn(*args, **kwargs)

    def delay(self, *args: object, **kwargs: object) -> AsyncResultShim:
        """Execute asynchronously or simulate async execution."""
        return self.apply_async(args=args, kwargs=dict(kwargs))

    def apply_async(
        self,
        args: tuple[object, ...] | None = None,
        kwargs: dict[str, object] | None = None,
        countdown: int | float | None = None,
        queue: str | None = None,
    ) -> AsyncResultShim:
        """Execute with Celery task options."""
        _ = countdown
        _ = queue
        call_args = args or ()
        call_kwargs = kwargs or {}
        task_id = str(uuid.uuid4())
        self.request = TaskRequestShim(
            task_id=task_id, retries=0, args=call_args, kwargs=call_kwargs
        )

        try:
            res = self(*call_args, **call_kwargs)
            return AsyncResultShim(task_id=task_id, result=res, status="SUCCESS")
        except Exception as exc:
            return AsyncResultShim(task_id=task_id, status="FAILURE", exc=exc)

    def retry(
        self,
        args: tuple[object, ...] | None = None,
        kwargs: dict[str, object] | None = None,
        exc: Exception | None = None,
        countdown: int | float | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Simulate Celery task retry with exponential backoff and DLQ routing on exhaustion."""
        limit = max_retries if max_retries is not None else self.max_retries
        self.request.retries += 1

        if self.request.retries > limit:
            self.on_failure(
                exc or MaxRetriesExceededError("Max retries exceeded"),
                self.request.id,
                args or self.request.args,
                kwargs or self.request.kwargs,
            )
            raise MaxRetriesExceededError(
                f"Task {self.name} exceeded max retries limit of {limit}"
            ) from exc

        calculated_delay = (
            countdown
            if countdown is not None
            else calculate_backoff_delay(self.request.retries - 1, self.default_retry_delay)
        )
        logger.info(
            "Task %s [%s] retry %d/%d scheduled in %ss",
            self.name,
            self.request.id,
            self.request.retries,
            limit,
            calculated_delay,
        )

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        einfo: object | None = None,
    ) -> None:
        """Triggered upon task failure; routes to DLQ if max retries reached."""
        _ = einfo
        route_to_dlq(
            task_id=task_id,
            task_name=self.name,
            args=args,
            kwargs=kwargs,
            exc=exc,
        )


class CeleryAppShim:
    """Lightweight Celery application shim maintaining exact Celery configurations."""

    def __init__(self, main: str = "market_intel", settings: Settings | None = None) -> None:
        """Initialize Celery application shim."""
        self.main = main
        self.settings = settings or get_settings()
        self.conf: dict[str, object] = {
            "broker_url": self.settings.celery_broker_url,
            "result_backend": self.settings.resolved_celery_result_backend,
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "task_default_queue": self.settings.celery_default_queue,
            "task_queues": [
                {"name": self.settings.celery_default_queue},
                {"name": self.settings.celery_dlq_name},
            ],
            "task_routes": {
                "market_intel.dlq.*": {"queue": self.settings.celery_dlq_name},
            },
        }
        self.tasks: dict[str, CeleryTaskShim] = {}

    def task(
        self,
        *args: object,
        **opts: object,
    ) -> object:
        """Decorator registering a task on this Celery shim."""

        def _decorator(fn: object) -> CeleryTaskShim:
            bind = bool(opts.get("bind", True))
            raw_retries = opts.get("max_retries", self.settings.celery_max_retries)
            max_retries = int(raw_retries) if isinstance(raw_retries, int | str) else 3
            raw_delay = opts.get("default_retry_delay", self.settings.celery_retry_base_delay)
            default_retry_delay = int(raw_delay) if isinstance(raw_delay, int | str) else 60
            retry_backoff = bool(opts.get("retry_backoff", True))
            fn_name = getattr(fn, "__name__", "task")
            task_name = str(opts.get("name", f"market_intel.{fn_name}"))

            shim_task = CeleryTaskShim(
                fn=fn,
                name=task_name,
                bind=bind,
                max_retries=max_retries,
                default_retry_delay=default_retry_delay,
                retry_backoff=retry_backoff,
            )
            self.tasks[task_name] = shim_task
            return shim_task

        if args and callable(args[0]):
            return _decorator(args[0])
        return _decorator


def create_celery_app(settings: Settings | None = None) -> object:
    """Create and configure Celery application with Redis broker and PostgreSQL backend.

    Args:
        settings: Optional Settings override.

    Returns:
        Configured Celery instance or CeleryAppShim fallback.
    """
    cfg = settings or get_settings()

    if _HAS_CELERY and _CeleryClass is not None:
        app = _CeleryClass("market_intel")
        conf_updates: dict[str, object] = {
            "broker_url": cfg.celery_broker_url,
            "result_backend": cfg.resolved_celery_result_backend,
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "task_default_queue": cfg.celery_default_queue,
        }

        if _KombuQueue is not None:
            conf_updates["task_queues"] = (
                _KombuQueue(cfg.celery_default_queue, routing_key="task.#"),
                _KombuQueue(cfg.celery_dlq_name, routing_key="dlq.#"),
            )
            conf_updates["task_routes"] = {
                "market_intel.dlq.*": {"queue": cfg.celery_dlq_name},
            }

        app.conf.update(conf_updates)
        return app

    return CeleryAppShim("market_intel", settings=cfg)


# Global Celery Application Instance
celery_app: object = create_celery_app()


# ──────────────────────────────────────────────────────────────────────────────
# Celery Tasks Definition
# ──────────────────────────────────────────────────────────────────────────────


def _get_task_decorator(
    app_obj: object,
) -> Callable[..., Callable[[Callable[..., object]], Any]]:
    """Return task decorator callable from celery_app object."""
    return cast(Callable[..., Callable[[Callable[..., object]], Any]], cast(Any, app_obj).task)


_task_decorator = _get_task_decorator(celery_app)


@_task_decorator(
    name="market_intel.enrich_article_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
)
def enrich_article_task(
    self: object,
    article_data: Mapping[str, object] | str,
) -> dict[str, object]:
    """Asynchronously enrich a financial news article with sentiment and NER entities.

    Args:
        self: Bound Celery task instance.
        article_data: Article dictionary or JSON string.

    Returns:
        Structured enriched dictionary with sentiment and extracted entities.
    """
    parsed: dict[str, object] = {}
    if isinstance(article_data, str):
        try:
            loaded = json.loads(article_data)
            parsed = dict(loaded) if isinstance(loaded, dict) else {}
        except Exception as exc:
            logger.warning("Failed to parse JSON string in enrich_article_task: %s", exc)
            parsed = {"content": article_data}
    elif isinstance(article_data, Mapping):
        parsed = dict(article_data)

    title = str(parsed.get("title", "")).strip()
    content = str(parsed.get("content", parsed.get("description", ""))).strip()
    full_text = f"{title}\n{content}".strip() if title else content

    if not full_text:
        return {
            "status": "skipped",
            "reason": "Empty article content",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    try:
        # 1. Financial Sentiment Analysis
        sentiment_analyzer = SentimentAnalyzer()
        try:
            sentiment_res: SentimentResult = sentiment_analyzer.analyze_text(full_text)
            sentiment_data = {
                "label": sentiment_res.label,
                "score": sentiment_res.score,
                "confidence": sentiment_res.confidence,
                "model_used": sentiment_res.model_used,
            }
        except Exception as sent_exc:
            logger.debug("Sentiment analysis error in task: %s", sent_exc)
            sentiment_data = {
                "label": "neutral",
                "score": 0.0,
                "confidence": 0.5,
                "model_used": "fallback",
            }

        # 2. Financial Named Entity Recognition (NER)
        ner_extractor = FinancialNERExtractor()
        try:
            ner_res: NERResult = ner_extractor.extract_text(full_text)
            ner_data = {
                "entities": ner_res.entities,
                "tickers": ner_res.tickers,
                "sectors": ner_res.sectors,
                "model_used": ner_res.model_used,
            }
        except Exception as ner_exc:
            logger.debug("NER extraction error in task: %s", ner_exc)
            ner_data = {
                "entities": {},
                "tickers": [],
                "sectors": [],
                "model_used": "fallback",
            }

        article_id = str(parsed.get("id") or parsed.get("url") or uuid.uuid4())

        return {
            "status": "enriched",
            "article_id": article_id,
            "title": title,
            "sentiment": sentiment_data,
            "ner": ner_data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as exc:
        retry_fn = getattr(self, "retry", None)
        if callable(retry_fn):
            current_retries = int(getattr(getattr(self, "request", None), "retries", 0))
            countdown = calculate_backoff_delay(current_retries)
            retry_fn(exc=exc, countdown=countdown)
        raise


def _run_sync(coro: Coroutine[object, object, object]) -> object:
    """Run an async coroutine synchronously, supporting both sync workers and active loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


@_task_decorator(
    name="market_intel.generate_embedding_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
)
def generate_embedding_task(
    self: object,
    text_or_article: Mapping[str, object] | str,
    model: str | None = None,
) -> dict[str, object]:
    """Asynchronously generate a 1536-dimensional vector embedding for text.

    Args:
        self: Bound Celery task instance.
        text_or_article: String text or dictionary containing content.
        model: Optional embedding model name override.

    Returns:
        Structured embedding dictionary with dimensions, token count, and vector.
    """
    settings = get_settings()
    target_model = model or settings.openai_embedding_model or DEFAULT_EMBEDDING_MODEL

    raw_text = ""
    if isinstance(text_or_article, str):
        raw_text = text_or_article
    elif isinstance(text_or_article, Mapping):
        raw_text = str(
            text_or_article.get(
                "content",
                text_or_article.get("text", text_or_article.get("summary", "")),
            )
        )

    cleaned = raw_text.strip()
    token_num = count_tokens(cleaned, model=target_model) if cleaned else 0

    try:
        transformer = DocumentTransformer(embedding_model=target_model)

        if not cleaned:
            embedding_vector = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
        else:
            try:
                batch_res = cast(
                    list[Any],
                    _run_sync(transformer.generate_embeddings_batch_async([cleaned])),
                )
                embedding_vector = (
                    batch_res[0].embedding
                    if batch_res
                    else [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
                )
            except Exception as emb_exc:
                logger.debug("DocumentTransformer invocation fallback: %s", emb_exc)
                embedding_vector = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS

        return {
            "status": "completed",
            "model": target_model,
            "dimensions": len(embedding_vector),
            "token_count": token_num,
            "embedding": embedding_vector,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as exc:
        retry_fn = getattr(self, "retry", None)
        if callable(retry_fn):
            current_retries = int(getattr(getattr(self, "request", None), "retries", 0))
            countdown = calculate_backoff_delay(current_retries)
            retry_fn(exc=exc, countdown=countdown)
        raise


@_task_decorator(
    name="market_intel.send_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
)
def send_alert_task(
    self: object,
    alert_data: Mapping[str, object] | str,
) -> dict[str, object]:
    """Asynchronously broadcast a market anomaly alert to connected WebSocket clients.

    Args:
        self: Bound Celery task instance.
        alert_data: Alert dictionary or JSON string.

    Returns:
        Delivery confirmation dictionary.
    """
    parsed: dict[str, object] = {}
    if isinstance(alert_data, str):
        try:
            loaded = json.loads(alert_data)
            parsed = dict(loaded) if isinstance(loaded, dict) else {}
        except Exception:
            parsed = {"message": alert_data}
    elif isinstance(alert_data, Mapping):
        parsed = dict(alert_data)

    try:
        from market_intel.api.websocket import connection_manager

        _run_sync(connection_manager.broadcast_alert(parsed))

        alert_id = str(parsed.get("id") or uuid.uuid4())
        return {
            "status": "delivered",
            "alert_id": alert_id,
            "alert": parsed,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as exc:
        retry_fn = getattr(self, "retry", None)
        if callable(retry_fn):
            current_retries = int(getattr(getattr(self, "request", None), "retries", 0))
            countdown = calculate_backoff_delay(current_retries)
            retry_fn(exc=exc, countdown=countdown)
        raise
