# Issue 6: PostgreSQL schema migrations with Alembic for raw and enriched tables

**Branch:** `feature/issue-6-postgres-schema`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M2 — Storage & Indexing Layer  

---

## Objective

Diseñar y definir el esquema relacional completo en PostgreSQL utilizando SQLAlchemy 2.0 (con soporte asíncrono vía `asyncpg`) y configurar Alembic en `src/market_intel/loaders/migrations/` para gestionar las migraciones de base de datos de manera automatizada tanto en modo offline como online asíncrono.

---

## Acceptance Criteria

- [x] **SQLAlchemy Async Engine & Pool**: Configuración del motor asíncrono (`create_async_engine`) con connection pooling (`pool_size`, `max_overflow`, `pool_pre_ping`).
- [x] **Data Models / Tables**: Modelos declarativos para:
  - `articles` (noticias de NewsAPI)
  - `filings` (reportes 10-K/10-Q de SEC EDGAR)
  - `reddit_posts` (publicaciones financieras de Reddit)
  - `price_data` (series temporales OHLCV y métricas de Alpha Vantage)
  - `enriched_signals` (señales y embeddings de downstream NLP, preparado para pgvector en Issue #7)
- [x] **Alembic Async Migrations**: Configuración de `alembic.ini` y `src/market_intel/loaders/migrations/env.py` usando el runner asíncrono de SQLAlchemy 2.0 (`run_sync`).
- [x] **Initial Migration**: Generación de la migración inicial `0001_initial_schema.py` con todas las tablas, claves foráneas, índices de búsqueda y restricciones únicas.
- [x] **Migration Clean Run**: Verificación de ejecución limpia con `alembic upgrade head` y downgrade con `alembic downgrade base`.
- [x] **Test Suite**: Tests unitarios para validación de metadatos, índices, restricciones y creación de esquemas (`pytest -m issue_6`).

---

## Technical Design & Decisions

### 1. Storage Dependencies (`pyproject.toml`)
Se deben añadir las librerías necesarias al bloque `storage`:
- `sqlalchemy[asyncio]>=2.0.30`: ORM y Core declarativo con soporte async nativo.
- `asyncpg>=0.29.0`: Driver PostgreSQL asíncrono de alto rendimiento.
- `alembic>=1.13.0`: Herramienta de control de versiones y migraciones de esquemas.
- `psycopg2-binary>=2.9.9`: Driver síncrono opcional utilizado por herramientas CLI / scripts legacy si fuera necesario.

### 2. Tablas y Estructura de Datos
Cada tabla heredará de un `Base` declarativo común e incluirá columnas de auditoría `created_at` y `updated_at`:

1. **`articles`**
   - `id`: UUID (Primary Key, default `uuid4`)
   - `source_id`: String(100), nullable
   - `source_name`: String(255), not null
   - `author`: String(255), nullable
   - `title`: String(500), not null
   - `description`: Text, nullable
   - `url`: Text, unique index (deduplicación natural en ingesta)
   - `url_to_image`: Text, nullable
   - `published_at`: DateTime(timezone=True), index=True
   - `content`: Text, nullable

2. **`filings`**
   - `id`: UUID PK
   - `cik`: String(10), index=True
   - `company_name`: String(255), not null
   - `filing_type`: String(20), index=True (ej. "10-K", "10-Q")
   - `filing_date`: DateTime(timezone=True), index=True
   - `period_of_report`: DateTime(timezone=True), nullable
   - `revenue`: Float / Numeric(18, 2), nullable
   - `eps`: Float / Numeric(10, 4), nullable
   - `assets`: Float / Numeric(18, 2), nullable
   - `raw_metrics`: JSONB / JSON, nullable

3. **`reddit_posts`**
   - `id`: UUID PK
   - `post_id`: String(50), unique index (ID nativo de Reddit)
   - `subreddit`: String(100), index=True
   - `title`: String(500), not null
   - `body`: Text, nullable
   - `score`: Integer, not null, default 0
   - `num_comments`: Integer, not null, default 0
   - `created_utc`: DateTime(timezone=True), index=True
   - `flair`: String(100), nullable

4. **`price_data`**
   - `id`: UUID PK
   - `symbol`: String(20), index=True
   - `date`: DateTime(timezone=True), index=True
   - `open`: Numeric(12, 4), not null
   - `high`: Numeric(12, 4), not null
   - `low`: Numeric(12, 4), not null
   - `close`: Numeric(12, 4), not null
   - `adjusted_close`: Numeric(12, 4), nullable
   - `volume`: BigInteger, not null
   - `UniqueConstraint("symbol", "date", name="uq_price_data_symbol_date")`

5. **`enriched_signals`**
   - `id`: UUID PK
   - `source_type`: String(50), not null (ej. "article", "filing", "reddit_post")
   - `source_id`: UUID, nullable, index=True
   - `symbol`: String(20), index=True
   - `signal_type`: String(50), index=True (ej. "sentiment", "anomaly", "summary")
   - `sentiment_score`: Float, nullable
   - `sentiment_label`: String(50), nullable
   - `confidence`: Float, nullable
   - `summary`: Text, nullable
   - `entities`: JSONB / JSON, nullable
   - `timestamp`: DateTime(timezone=True), index=True
   - *(Nota: En Issue #7 se añadirá a esta tabla la columna `embedding VECTOR(1536)` e índice IVFFlat)*

---

## Implementation Tasks

### 1. Preparación de Rama
```bash
make start-issue ID=6 NAME=postgres-schema
```

### 2. Dependencias y Configuración
- **Archivo**: `pyproject.toml`
  - Añadir `sqlalchemy[asyncio]`, `asyncpg`, `alembic` a la sección `storage`.
  - Asegurar que `pytest -m issue_6` esté operativo.
- **Archivo**: `src/market_intel/core/config.py`
  - Añadir propiedades calculadas para URLs de conexión:
    - `async_postgres_url` (`postgresql+asyncpg://...`)
    - `sync_postgres_url` (`postgresql+psycopg2://...`)

### 3. Motor Asíncrono de Base de Datos y Sesiones
- **Archivo**: `src/market_intel/loaders/database.py`
  - Implementar `get_async_engine()` con pool configurable (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`).
  - Implementar `get_async_session_factory()` y generador `get_async_session()`.
  - Definir `Base = DeclarativeBase` y `TimestampMixin`.

### 4. Modelos Declarativos SQLAlchemy
- **Archivo**: `src/market_intel/loaders/models.py`
  - Definir modelos para `ArticleModel`, `FilingModel`, `RedditPostModel`, `PriceDataModel`, `EnrichedSignalModel`.
  - Definir índices y restricciones únicas correspondientes.
- **Archivo**: `src/market_intel/loaders/__init__.py`
  - Re-exportar `Base`, motor, sesiones y modelos.

### 5. Configuración de Alembic
- **Archivo**: `alembic.ini` (en raíz del proyecto)
  - Configurar `script_location = src/market_intel/loaders/migrations`.
- **Directorio**: `src/market_intel/loaders/migrations/`
  - Crear `env.py` configurado para:
    - Importar `Base.metadata` de `market_intel.loaders.models`.
    - Modo offline (`run_migrations_offline()`).
    - Modo online asíncrono (`run_migrations_online()` con `async_engine.connect()` y `run_sync`).
  - Crear `script.py.mako` template.

### 6. Migración Inicial
- **Archivo**: `src/market_intel/loaders/migrations/versions/0001_initial_schema.py`
  - Crear script de migración que genere las 5 tablas e índices.
  - Implementar `upgrade()` y `downgrade()`.

### 7. Suite de Tests
- **Archivo**: `tests/unit/test_postgres_schema.py`
  - Verificar inicialización de `async_engine` y configuración de pool.
  - Validar introspección de metadatos de SQLAlchemy: existencia de tablas, columnas obligatorias, tipos de datos, índices y restricciones (`UniqueConstraint`).
  - Test de ejecución de `Base.metadata.create_all()` en SQLite en memoria (`sqlite+aiosqlite://`) para validar DDL sin requerir un cluster PostgreSQL en tests unitarios.
  - Test de runner offline de Alembic para asegurar compatibilidad de `env.py`.

### 8. Verificación y Calidad
```bash
make deps-all
make test-issue ID=6
make check
```

### 9. Finalización y PR
```bash
make finish-issue ID=6 MSG="feat(storage): implement postgresql schema and alembic async migrations"
```
