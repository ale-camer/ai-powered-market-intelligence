# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-10-05

### Added
- **Ingestion**: Extractors for NewsAPI, SEC EDGAR, Reddit, and Alpha Vantage.
- **Storage**: PostgreSQL with pgvector for efficient vector similarity search, Redis for caching.
- **NLP & AI**: FinBERT for financial sentiment analysis, SpaCy for NER, and OpenAI for document embeddings and summarization.
- **Orchestration**: End-to-end Airflow DAG managing the daily ingestion, transformation, and loading pipeline.
- **Delivery**: Asynchronous FastAPI REST API with endpoints for querying signals, anomalies, and summaries.
- **Streaming**: WebSocket support for real-time anomaly alerts.
- **Observability**: Prometheus metrics and Sentry integration.
- **Security**: OWASP headers, CORS hardening, Bandit SAST scanning, and Gitleaks secrets detection.
- **Infrastructure**: Docker containerization and Terraform IaC for deployment.
- **CI/CD**: Fully automated GitHub Actions workflow for linting, testing, and security checks.

### Changed
- Promoted project status from Planning to Production/Stable.
- Bumped API version to 1.0.0.
