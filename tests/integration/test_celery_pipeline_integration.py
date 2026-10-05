"""Integration tests for Celery task pipelines, retry policies, and DLQ routing (Issue #19)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_intel.core.celery_app import (
    calculate_backoff_delay,
    clear_dlq,
    enrich_article_task,
    generate_embedding_task,
    get_dlq_messages,
    route_to_dlq,
    send_alert_task,
)

pytestmark = [pytest.mark.integration, pytest.mark.issue_19]


def test_celery_task_chain_integration() -> None:
    """Validate task chaining: enrichment -> embedding generation -> alert dispatch."""
    # 1. Raw article input
    article_payload = {
        "title": "Microsoft and OpenAI announce massive expansion of cloud data centers",
        "description": "Microsoft shares rose following increased guidance on Azure AI revenue.",
        "content": (
            "Microsoft Corporation (MSFT) reported strong demand across "
            "its intelligent cloud segment."
        ),
        "url": "https://example.com/msft-expansion",
        "published_at": datetime.now(UTC).isoformat(),
        "source": {"name": "MarketWatch"},
    }

    # Execute enrichment task
    enriched_result = enrich_article_task(article_payload)
    assert isinstance(enriched_result, dict)
    assert enriched_result["status"] == "enriched"
    assert "sentiment" in enriched_result
    assert "ner" in enriched_result
    assert "title" in enriched_result

    tickers = enriched_result.get("ner", {}).get("tickers", [])
    symbol = tickers[0] if tickers else "MSFT"

    # 2. Embedding generation task (with mocked transformer output for fast deterministic execution)
    embedding_payload = {
        "text": enriched_result["title"],
        "model": "text-embedding-3-small",
        "signal_id": str(uuid.uuid4()),
    }
    mock_emb_item = MagicMock()
    mock_emb_item.embedding = [0.05] * 1536
    with patch(
        "market_intel.transformers.embeddings.DocumentTransformer.generate_embeddings_batch_async",
        new_callable=AsyncMock,
    ) as mock_emb_fn:
        mock_emb_fn.return_value = [mock_emb_item]
        embedding_result = generate_embedding_task(embedding_payload)

    assert isinstance(embedding_result, dict)
    assert "embedding" in embedding_result
    assert len(embedding_result["embedding"]) == 1536
    assert isinstance(embedding_result["embedding"][0], float)

    # 3. Alert dispatch task
    alert_payload = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "anomaly_type": "sentiment_spike",
        "score": 0.88,
        "message": "Strong bullish signal detected for MSFT following cloud revenue guidance.",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with patch(
        "market_intel.api.websocket.connection_manager.broadcast_alert",
        new_callable=AsyncMock,
    ) as mock_broadcast:
        mock_broadcast.return_value = 3  # 3 connected clients received alert
        alert_result = send_alert_task(alert_payload)
        assert isinstance(alert_result, dict)
        assert alert_result["status"] == "delivered"
        assert alert_result["alert"]["symbol"] == symbol


def test_celery_retry_backoff_and_dlq_integration() -> None:
    """Validate exponential backoff delay progression and Dead Letter Queue capturing."""
    # Test exponential progression: 60s, 120s, 240s, capped at max_delay
    delay_0 = calculate_backoff_delay(retries=0, base_delay=60, max_delay=600)
    delay_1 = calculate_backoff_delay(retries=1, base_delay=60, max_delay=600)
    delay_2 = calculate_backoff_delay(retries=2, base_delay=60, max_delay=600)
    delay_10 = calculate_backoff_delay(retries=10, base_delay=60, max_delay=600)

    assert delay_0 == 60
    assert delay_1 == 120
    assert delay_2 == 240
    assert delay_10 == 600  # Capped

    # Test Dead Letter Queue routing on permanent failure
    test_queue = "market_intel.dlq.test"
    clear_dlq()

    simulated_error = RuntimeError("Database connection timed out after 3 retries")
    task_id = str(uuid.uuid4())

    route_to_dlq(
        task_id=task_id,
        task_name="market_intel.tasks.enrich_article",
        args=({"url": "https://example.com/failed-article"},),
        kwargs={},
        exc=simulated_error,
        queue_name=test_queue,
    )

    # Inspect DLQ
    dlq_items = get_dlq_messages()
    assert len(dlq_items) == 1
    stored = dlq_items[0]
    assert stored["task_id"] == task_id
    assert stored["task_name"] == "market_intel.tasks.enrich_article"
    assert "Database connection timed out" in str(stored["exception_message"])
    assert stored["exception_type"] == "RuntimeError"

    # Clear DLQ
    clear_dlq()
    assert len(get_dlq_messages()) == 0
