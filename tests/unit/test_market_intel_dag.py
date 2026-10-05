"""Unit tests for the market_intel_daily Airflow orchestration DAG."""

from datetime import timedelta

import pytest

from dags.market_intel_daily import dag as exposed_dag
from market_intel.pipelines.market_intel_dag import (
    market_intel_daily,
    run_ingest_filings,
    run_ingest_news,
    run_ingest_prices,
    run_ingest_reddit,
    run_load_to_db,
    run_transform_enrich,
    sla_miss_alert,
)

pytestmark = [pytest.mark.unit, pytest.mark.issue_14]


def test_dag_import_and_metadata() -> None:
    """Verify market_intel_daily DAG is importable and has correct metadata."""
    assert market_intel_daily is not None
    assert exposed_dag is market_intel_daily

    assert market_intel_daily.dag_id == "market_intel_daily"
    assert market_intel_daily.schedule_interval == "@daily"
    assert market_intel_daily.catchup is False
    assert "market-intel" in market_intel_daily.tags


def test_task_set_completeness() -> None:
    """Verify all 6 required ingestion, transformation, and load tasks exist in the DAG."""
    expected_tasks = {
        "ingest_news",
        "ingest_filings",
        "ingest_reddit",
        "ingest_prices",
        "transform_enrich",
        "load_to_db",
    }

    actual_tasks = set(market_intel_daily.task_ids)
    assert expected_tasks.issubset(actual_tasks)
    assert len(actual_tasks) == 6


def test_topological_dependencies() -> None:
    """Verify upstream and downstream task dependencies (fan-in ingest -> transform -> load)."""
    t_news = market_intel_daily.get_task("ingest_news")
    t_filings = market_intel_daily.get_task("ingest_filings")
    t_reddit = market_intel_daily.get_task("ingest_reddit")
    t_prices = market_intel_daily.get_task("ingest_prices")
    t_transform = market_intel_daily.get_task("transform_enrich")
    t_load = market_intel_daily.get_task("load_to_db")

    # Ingestion tasks must have transform_enrich downstream
    assert "transform_enrich" in t_news.downstream_task_ids
    assert "transform_enrich" in t_filings.downstream_task_ids
    assert "transform_enrich" in t_reddit.downstream_task_ids
    assert "transform_enrich" in t_prices.downstream_task_ids

    # transform_enrich must have all 4 ingestion tasks as upstreams
    expected_upstreams = {"ingest_news", "ingest_filings", "ingest_reddit", "ingest_prices"}
    assert expected_upstreams.issubset(t_transform.upstream_task_ids)

    # transform_enrich must lead to load_to_db
    assert "load_to_db" in t_transform.downstream_task_ids
    assert "transform_enrich" in t_load.upstream_task_ids

    # load_to_db has no downstreams (terminal sink)
    assert len(t_load.downstream_task_ids) == 0


def test_sla_configuration_and_callback() -> None:
    """Verify SLA miss alert callback is attached and runnable."""
    assert market_intel_daily.sla_miss_callback is sla_miss_alert

    # Verify callback executes without exceptions
    sla_miss_alert(
        dag=market_intel_daily,
        task_list=["transform_enrich"],
        blocking_task_list=["ingest_news"],
        slas=[timedelta(hours=2)],
        blocking_tis=[],
    )

    # Verify default args
    args = market_intel_daily.default_args
    assert args.get("retries") == 2
    assert args.get("retry_delay") == timedelta(minutes=5)
    assert args.get("email_on_failure") is True
    assert args.get("sla") == timedelta(hours=2.0)


def test_task_callables_execution() -> None:
    """Verify all task callables run cleanly and return execution metadata dictionaries."""
    res_news = run_ingest_news()
    assert res_news["task"] == "ingest_news"
    assert res_news["status"] == "success"
    assert "articles_ingested" in res_news

    res_filings = run_ingest_filings()
    assert res_filings["task"] == "ingest_filings"
    assert res_filings["status"] == "success"
    assert "filings_ingested" in res_filings

    res_reddit = run_ingest_reddit()
    assert res_reddit["task"] == "ingest_reddit"
    assert res_reddit["status"] == "success"
    assert "posts_ingested" in res_reddit

    res_prices = run_ingest_prices()
    assert res_prices["task"] == "ingest_prices"
    assert res_prices["status"] == "success"
    assert "prices_ingested" in res_prices

    res_transform = run_transform_enrich()
    assert res_transform["task"] == "transform_enrich"
    assert res_transform["status"] == "success"
    assert "signals_enriched" in res_transform

    res_load = run_load_to_db()
    assert res_load["task"] == "load_to_db"
    assert res_load["status"] == "success"
    assert "records_loaded" in res_load
