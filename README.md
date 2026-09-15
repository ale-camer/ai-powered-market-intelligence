# AI-Powered Market Intelligence

> An end-to-end pipeline that ingests multi-source financial data, enriches it
> with NLP and AI models, stores it in a vector-enabled PostgreSQL database, and
> delivers actionable market signals via a REST/WebSocket API — all orchestrated
> by Apache Airflow.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Data Sources (External)                          │
│  NewsAPI │ SEC EDGAR │ Reddit │ Alpha Vantage │ Custom RSS               │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │  HTTP / REST / FTP
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Ingestion Layer (src/extractors)                      │
│  Rate-limited HTTP clients │ Pagination │ Retry logic │ Schema validation│
└──────────────────────────┬──────────────────────────────────────────────┘
                           │  Raw JSON / XML / XBRL
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Transformation Layer (src/transformers)                │
│  NLP Enrichment: FinBERT sentiment │ NER │ Embedding generation (OpenAI) │
│  Deduplication │ Normalization │ Anomaly detection                       │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │  Enriched records + embeddings
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Storage Layer (src/loaders)                         │
│  PostgreSQL + pgvector: raw & enriched tables                            │
│  Redis: hot-path deduplication cache                                     │
│  Alembic: schema migrations                                              │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Orchestration (src/pipelines + Airflow)                │
│  DAG: ingest → transform → load  │  Celery async workers  │  Scheduling  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Delivery Layer (src/api)                               │
│  FastAPI REST endpoints │ WebSocket streaming │ Market signal alerts      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
ai-powered-market-intelligence/
├── src/
│   └── market_intel/
│       ├── extractors/     # Data source connectors
│       ├── transformers/   # NLP enrichment, normalization
│       ├── loaders/        # DB / vector store writers
│       ├── pipelines/      # Airflow DAGs
│       ├── api/            # FastAPI app
│       └── core/           # Shared config, logging, exceptions
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── infra/
│   ├── docker/
│   ├── terraform/
│   └── k8s/
├── docs/
├── .agents/rules/
├── .env.example
├── .gitignore
├── pyproject.toml
├── Makefile
└── README.md
```

---

## Milestones

| Milestone | Scope | Issues |
|-----------|-------|--------|
| **M1** — Data Ingestion | NewsAPI, SEC, Reddit, Alpha Vantage extractors | #1–#5 |
| **M2** — Storage & Indexing | PostgreSQL/pgvector, Redis, Pydantic models | #6–#9 |
| **M3** — NLP & AI Enrichment | Sentiment, NER, embeddings, anomaly detection | #10–#13 |
| **M4** — Orchestration & Delivery | Airflow DAGs, FastAPI, WebSocket, Celery, Observability | #14–#18 |
| **M5** — Quality & Release | Tests, Docker, Terraform, CI/CD, Security, Docs, v1.0 | #19–#25 |

---

## Quick Start (Developer)

```bash
# 1. Clone the repo
git clone https://github.com/ale-camer/ai-powered-market-intelligence.git
cd ai-powered-market-intelligence

# 2. Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 3. Install dev dependencies
make deps

# 4. Copy environment variables
cp .env.example .env
# edit .env with your actual keys

# 5. Run the test suite
make test
```

---

## Development Workflow

```bash
# Start an issue (creates branch from develop)
make start-issue ID=2 NAME=newsapi-extractor

# Install updated dependencies
make deps

# Run tests for the current issue
make test-issue ID=2

# Finish the issue (PR + merge + cleanup)
make finish-issue ID=2
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+ |
| Orchestration | Apache Airflow 2.9+ |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| AI / NLP | OpenAI GPT-4o, FinBERT (HuggingFace) |
| API | FastAPI |
| Async workers | Celery |
| Linting | Ruff, Mypy |
| Testing | pytest, pytest-asyncio, pytest-cov |
| Infrastructure | Docker, Terraform, Kubernetes |
| CI/CD | GitHub Actions |
| Observability | Prometheus + Grafana |

---

## License

MIT — see [LICENSE](LICENSE).
