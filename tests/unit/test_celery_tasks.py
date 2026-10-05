"""Unit tests for Celery async task workers, retry logic, and DLQ (Issue #17)."""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from market_intel.core.celery_app import (
    CeleryAppShim,
    CeleryTaskShim,
    MaxRetriesExceededError,
    calculate_backoff_delay,
    clear_dlq,
    create_celery_app,
    enrich_article_task,
    generate_embedding_task,
    get_dlq_messages,
    route_to_dlq,
    send_alert_task,
)
from market_intel.core.config import Settings
from market_intel.core.schemas import NERResult, SentimentResult


@pytest.fixture(autouse=True)
def reset_dlq_store() -> Generator[None, None, None]:
    """Ensure DLQ registry is cleared before and after each test."""
    clear_dlq()
    yield
    clear_dlq()


@pytest.mark.unit
@pytest.mark.issue_17
def test_celery_app_default_configuration() -> None:
    """Validate Celery app default settings: Redis broker, PostgreSQL result backend, queues."""
    app = create_celery_app()
    assert isinstance(app, CeleryAppShim)

    conf = app.conf
    assert "redis://" in str(conf["broker_url"])
    assert "postgresql" in str(conf["result_backend"])
    assert conf["task_serializer"] == "json"
    assert conf["result_serializer"] == "json"
    assert conf["timezone"] == "UTC"
    assert conf["enable_utc"] is True

    # Validate queues and DLQ routing
    queues = conf["task_queues"]
    queue_names = [q["name"] if isinstance(q, dict) else getattr(q, "name", "") for q in queues]
    assert "celery" in queue_names
    assert "market_intel.dlq" in queue_names

    routes = conf["task_routes"]
    assert "market_intel.dlq.*" in routes
    assert routes["market_intel.dlq.*"]["queue"] == "market_intel.dlq"


@pytest.mark.unit
@pytest.mark.issue_17
def test_create_celery_app_custom_settings() -> None:
    """Validate create_celery_app with custom Settings overrides."""
    custom_settings = Settings(
        CELERY_BROKER_URL="redis://custom-redis:6380/2",
        CELERY_RESULT_BACKEND="postgresql+psycopg2://user:pass@custom-pg:5432/custom_db",
        CELERY_DEFAULT_QUEUE="custom_queue",
        CELERY_DLQ_NAME="custom.dlq",
    )
    custom_app = create_celery_app(settings=custom_settings)
    assert isinstance(custom_app, CeleryAppShim)

    conf = custom_app.conf
    assert conf["broker_url"] == "redis://custom-redis:6380/2"
    assert conf["result_backend"] == "postgresql+psycopg2://user:pass@custom-pg:5432/custom_db"
    assert conf["task_default_queue"] == "custom_queue"

    queue_names = [
        q["name"] if isinstance(q, dict) else getattr(q, "name", "")
        for q in conf["task_queues"]
    ]
    assert "custom_queue" in queue_names
    assert "custom.dlq" in queue_names


@pytest.mark.unit
@pytest.mark.issue_17
def test_calculate_backoff_delay() -> None:
    """Validate exponential backoff progression (60s, 120s, 240s, capped at max_delay)."""
    assert calculate_backoff_delay(retries=0, base_delay=60) == 60
    assert calculate_backoff_delay(retries=1, base_delay=60) == 120
    assert calculate_backoff_delay(retries=2, base_delay=60) == 240
    assert calculate_backoff_delay(retries=3, base_delay=60) == 480
    assert calculate_backoff_delay(retries=4, base_delay=60) == 600  # Capped at default 600s
    assert calculate_backoff_delay(retries=10, base_delay=60) == 600
    assert calculate_backoff_delay(retries=-1, base_delay=60) == 60


@pytest.mark.unit
@pytest.mark.issue_17
def test_route_to_dlq_recording() -> None:
    """Validate routing failed task metadata to the Dead Letter Queue."""
    assert len(get_dlq_messages()) == 0

    exc = ValueError("Fatal downstream schema mismatch")
    payload = route_to_dlq(
        task_id="task-xyz-123",
        task_name="market_intel.enrich_article_task",
        args=("arg1", 42),
        kwargs={"ticker": "AAPL"},
        exc=exc,
    )

    assert payload["task_id"] == "task-xyz-123"
    assert payload["task_name"] == "market_intel.enrich_article_task"
    assert payload["args"] == ["arg1", 42]
    assert payload["kwargs"] == {"ticker": "AAPL"}
    assert payload["exception_type"] == "ValueError"
    assert payload["exception_message"] == "Fatal downstream schema mismatch"
    assert payload["queue"] == "market_intel.dlq"
    assert "timestamp" in payload

    # Ensure message is stored in DLQ
    stored = get_dlq_messages()
    assert len(stored) == 1
    assert stored[0]["task_id"] == "task-xyz-123"

    clear_dlq()
    assert len(get_dlq_messages()) == 0


@pytest.mark.unit
@pytest.mark.issue_17
def test_enrich_article_task_dictionary_payload() -> None:
    """Validate enrich_article_task execution with a dictionary payload."""
    article = {
        "id": "art-001",
        "title": "Apple Reports Record Quarterly Revenue",
        "content": "Apple Inc. AAPL revealed quarterly results exceeding Wall Street estimates.",
    }

    mock_sentiment = SentimentResult(
        label="positive",
        score=0.88,
        confidence=0.95,
        model_used="ProsusAI/finbert",
    )
    mock_ner = NERResult(
        entities={"ORG": ["Apple Inc."]},
        tickers=["AAPL"],
        sectors=["Information Technology"],
        model_used="en_core_web_trf",
    )

    with (
        patch(
            "market_intel.core.celery_app.SentimentAnalyzer.analyze_text",
            return_value=mock_sentiment,
        ),
        patch(
            "market_intel.core.celery_app.FinancialNERExtractor.extract_text",
            return_value=mock_ner,
        ),
    ):
        result = enrich_article_task(article)

    assert isinstance(result, dict)
    assert result["status"] == "enriched"
    assert result["article_id"] == "art-001"
    assert result["sentiment"]["label"] == "positive"
    assert result["sentiment"]["score"] == 0.88
    assert result["ner"]["tickers"] == ["AAPL"]
    assert "Information Technology" in result["ner"]["sectors"]


@pytest.mark.unit
@pytest.mark.issue_17
def test_enrich_article_task_json_string_input() -> None:
    """Validate enrich_article_task correctly deserializes JSON string payloads."""
    payload = json.dumps(
        {
            "id": "art-json-002",
            "title": "Microsoft Launches New Cloud AI Cluster",
            "description": "Microsoft announced expanded Azure enterprise infrastructure.",
        }
    )

    result = enrich_article_task(payload)
    assert isinstance(result, dict)
    assert result["status"] == "enriched"
    assert result["article_id"] == "art-json-002"
    assert "sentiment" in result
    assert "ner" in result


@pytest.mark.unit
@pytest.mark.issue_17
def test_enrich_article_task_empty_input() -> None:
    """Validate enrich_article_task skips processing when input has no text."""
    result = enrich_article_task({"title": "", "content": ""})
    assert isinstance(result, dict)
    assert result["status"] == "skipped"
    assert "Empty article content" in str(result.get("reason", ""))


@pytest.mark.unit
@pytest.mark.issue_17
def test_generate_embedding_task_success() -> None:
    """Validate generate_embedding_task produces vector with 1536 dimensions."""
    mock_vec = [0.05] * 1536

    mock_transformer = MagicMock()
    mock_item = MagicMock(embedding=mock_vec)

    async def mock_batch(texts: list[str]) -> list[MagicMock]:
        _ = texts
        return [mock_item]

    mock_transformer.generate_embeddings_batch_async = mock_batch

    with patch(
        "market_intel.core.celery_app.DocumentTransformer",
        return_value=mock_transformer,
    ):
        res = generate_embedding_task(
            "Federal Reserve maintains benchmark interest rate unchanged."
        )

    assert isinstance(res, dict)
    assert res["status"] == "completed"
    assert res["dimensions"] == 1536
    assert res["token_count"] > 0
    assert len(res["embedding"]) == 1536


@pytest.mark.unit
@pytest.mark.issue_17
def test_generate_embedding_task_empty_text() -> None:
    """Validate generate_embedding_task returns zero vector on empty input."""
    res = generate_embedding_task("")
    assert isinstance(res, dict)
    assert res["status"] == "completed"
    assert res["dimensions"] == 1536
    assert res["token_count"] == 0
    assert res["embedding"] == [0.0] * 1536


@pytest.mark.unit
@pytest.mark.issue_17
def test_send_alert_task_success() -> None:
    """Validate send_alert_task broadcasts anomaly alert via connection manager."""
    alert_payload = {
        "id": "alert-test-999",
        "symbol": "AAPL",
        "score": 3.75,
        "severity": "high",
        "description": "Abnormal trading volume spike detected.",
    }

    with patch("market_intel.api.websocket.connection_manager.broadcast_alert"):
        res = send_alert_task(alert_payload)

    assert isinstance(res, dict)
    assert res["status"] == "delivered"
    assert res["alert_id"] == "alert-test-999"
    assert res["alert"]["symbol"] == "AAPL"


@pytest.mark.unit
@pytest.mark.issue_17
def test_send_alert_task_json_string() -> None:
    """Validate send_alert_task handles JSON string format."""
    payload = json.dumps({"symbol": "NVDA", "score": 4.1, "severity": "critical"})

    with patch("market_intel.api.websocket.connection_manager.broadcast_alert"):
        res = send_alert_task(payload)

    assert isinstance(res, dict)
    assert res["status"] == "delivered"
    assert res["alert"]["symbol"] == "NVDA"


@pytest.mark.unit
@pytest.mark.issue_17
def test_task_delay_and_apply_async() -> None:
    """Validate CeleryTaskShim delay and apply_async methods return AsyncResult."""
    # Test delay
    async_res = send_alert_task.delay({"symbol": "TSLA", "score": 2.5})
    assert async_res.id is not None
    assert async_res.successful() is True
    assert async_res.failed() is False
    assert async_res.get()["status"] == "delivered"

    # Test apply_async with countdown
    async_res2 = send_alert_task.apply_async(
        args=({"symbol": "GOOGL", "score": 1.8},),
        countdown=60,
    )
    assert async_res2.id is not None
    assert async_res2.successful() is True
    assert async_res2.get()["status"] == "delivered"


@pytest.mark.unit
@pytest.mark.issue_17
def test_task_retry_and_backoff_logic() -> None:
    """Validate task retry incrementation and backoff scheduling."""
    task_shim = CeleryTaskShim(
        fn=lambda self: None,
        name="market_intel.test_task",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )

    assert task_shim.request.retries == 0

    # 1st retry
    task_shim.retry(exc=ConnectionError("Transient network drop"))
    assert task_shim.request.retries == 1

    # 2nd retry
    task_shim.retry(exc=ConnectionError("Still offline"))
    assert task_shim.request.retries == 2

    # 3rd retry
    task_shim.retry(exc=ConnectionError("Third attempt"))
    assert task_shim.request.retries == 3


@pytest.mark.unit
@pytest.mark.issue_17
def test_task_max_retries_exceeded_routes_to_dlq() -> None:
    """Validate that exceeding max_retries triggers on_failure and routes task to DLQ."""
    assert len(get_dlq_messages()) == 0

    task_shim = CeleryTaskShim(
        fn=lambda self: None,
        name="market_intel.failing_task",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )

    # Exhaust retries
    task_shim.retry()
    task_shim.retry()
    task_shim.retry()
    assert task_shim.request.retries == 3
    assert len(get_dlq_messages()) == 0

    # 4th retry exceeds max_retries=3 -> triggers DLQ routing and raises MaxRetriesExceededError
    with pytest.raises(MaxRetriesExceededError) as exc_info:
        task_shim.retry(exc=TimeoutError("Downstream service timed out permanently"))

    assert "exceeded max retries limit" in str(exc_info.value)

    # Verify DLQ received the failed task
    dlq_messages = get_dlq_messages()
    assert len(dlq_messages) == 1
    dlq_entry = dlq_messages[0]
    assert dlq_entry["task_name"] == "market_intel.failing_task"
    assert dlq_entry["exception_type"] == "TimeoutError"
    assert "Downstream service timed out permanently" in str(dlq_entry["exception_message"])
    assert dlq_entry["queue"] == "market_intel.dlq"


@pytest.mark.unit
@pytest.mark.issue_17
def test_async_result_shim_failed_and_get_exception() -> None:
    """Validate AsyncResultShim behavior on failed tasks."""
    failing_shim = CeleryTaskShim(
        fn=lambda self: (_ for _ in ()).throw(ValueError("Boom")),
        name="market_intel.error_task",
        bind=True,
    )
    res = failing_shim.apply_async()
    assert res.successful() is False
    assert res.failed() is True
    with pytest.raises(ValueError, match="Boom"):
        res.get()


@pytest.mark.unit
@pytest.mark.issue_17
def test_celery_task_shim_unbound_and_non_callable() -> None:
    """Validate CeleryTaskShim with bind=False and non-callable target."""
    unbound_task = CeleryTaskShim(
        fn=lambda x, y: x + y,
        name="market_intel.add_task",
        bind=False,
    )
    assert unbound_task(2, 3) == 5

    non_callable_task = CeleryTaskShim(
        fn=None,
        name="market_intel.none_task",
    )
    assert non_callable_task() is None


@pytest.mark.unit
@pytest.mark.issue_17
def test_enrich_article_task_non_json_string() -> None:
    """Validate enrich_article_task fallback when passed a plain text string instead of JSON."""
    raw_text = "Plain text financial update regarding market volatility."
    res = enrich_article_task(raw_text)
    assert isinstance(res, dict)
    assert res["status"] == "enriched"
    assert "sentiment" in res
    assert "ner" in res


@pytest.mark.unit
@pytest.mark.issue_17
def test_enrich_article_task_retry_on_unhandled_exception() -> None:
    """Validate enrich_article_task invokes self.retry when unhandled error occurs."""
    with (
        patch.object(enrich_article_task, "retry") as mock_retry,
        patch(
            "market_intel.core.celery_app.SentimentAnalyzer",
            side_effect=RuntimeError("Unrecoverable NLP worker crash"),
        ),
        pytest.raises(RuntimeError),
    ):
        enrich_article_task({"title": "Test Title", "content": "Test content"})

    mock_retry.assert_called_once()


@pytest.mark.unit
@pytest.mark.issue_17
def test_generate_embedding_task_retry_on_exception() -> None:
    """Validate generate_embedding_task invokes self.retry when unhandled error occurs."""
    with (
        patch.object(generate_embedding_task, "retry") as mock_retry,
        patch(
            "market_intel.core.celery_app.DocumentTransformer",
            side_effect=RuntimeError("Embedding generator failed"),
        ),
        pytest.raises(RuntimeError),
    ):
        generate_embedding_task("Test document text")

    mock_retry.assert_called_once()


@pytest.mark.unit
@pytest.mark.issue_17
def test_send_alert_task_invalid_json_and_retry() -> None:
    """Validate send_alert_task invalid JSON fallback and retry on broadcast exception."""
    # Test invalid json fallback
    with patch("market_intel.api.websocket.connection_manager.broadcast_alert"):
        res = send_alert_task("invalid {json")
    assert res["status"] == "delivered"

    # Test retry invocation on exception
    with (
        patch.object(send_alert_task, "retry") as mock_retry,
        patch(
            "market_intel.api.websocket.connection_manager.broadcast_alert",
            side_effect=ConnectionError("WebSocket dropped"),
        ),
        pytest.raises(ConnectionError),
    ):
        send_alert_task({"symbol": "AAPL"})

    mock_retry.assert_called_once()


@pytest.mark.unit
@pytest.mark.issue_17
def test_create_celery_app_when_celery_available() -> None:
    """Validate create_celery_app branches when Celery library is present."""
    mock_celery_cls = MagicMock()
    mock_app_instance = MagicMock()
    mock_celery_cls.return_value = mock_app_instance

    mock_queue_cls = MagicMock()

    with (
        patch("market_intel.core.celery_app._HAS_CELERY", True),
        patch("market_intel.core.celery_app._CeleryClass", mock_celery_cls),
        patch("market_intel.core.celery_app._KombuQueue", mock_queue_cls),
    ):
        app = create_celery_app()

    assert app == mock_app_instance
    mock_app_instance.conf.update.assert_called_once()

