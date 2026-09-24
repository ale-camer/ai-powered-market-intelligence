# Issue 9: Pydantic data models and schema validation layer

**Branch:** `feature/issue-9-pydantic-schemas`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M2 — Storage & Indexing Layer (Final Issue of M2)  

---

## Objective

Centralizar y formalizar todos los modelos de dominio Pydantic v2 en `src/market_intel/core/schemas.py` con validación estricta (`strict=True`), normalización automática mediante validadores (`field_validator`), ejemplos de esquemas JSON (`json_schema_extra`), y métodos adaptadores bidireccionales (`from_orm` / `from_attributes=True`) para interactuar directamente con los modelos ORM de SQLAlchemy (`src/market_intel/loaders/models.py`).

---

## Acceptance Criteria

- [x] **Core Pydantic Models**:
  - `ArticleSchema`: noticia ingerida con metadatos de fuente, autor, título, descripción, URL normalizada y fecha.
  - `FilingSchema`: reporte 10-K/10-Q con CIK, nombre de compañía, métricas XBRL y fechas.
  - `PostSchema`: publicación de Reddit con subreddit, post_id, autor, título, métricas de engagement y fecha.
  - `PriceSchema`: registro de precios OHLCV diarios con ticker en mayúsculas y volumen.
  - `EnrichedSignalSchema`: señal NLP enriquecida con `source_type`, `symbol`, `signal_type`, `sentiment_score`, `entities` y `embedding` vectorial opcional.
- [x] **Custom Validators**:
  - `normalize_url_validator`: normalización automática de URLs eliminando parámetros de tracking (`utm_*`) vía `normalize_url`.
  - `uppercase_symbol_validator`: conversión automática de símbolos de ticker a mayúsculas limpias (ej. `"aapl"` -> `"AAPL"`).
  - `parse_datetime_validator`: parseo robusto y garantía de datetimes con zona horaria UTC.
- [x] **Model Configuration**:
  - `model_config = ConfigDict(strict=True, from_attributes=True, populate_by_name=True, json_schema_extra=...)`.
  - Ejemplos documentados en `json_schema_extra` para cada modelo.
- [x] **SQLAlchemy ORM Adapters**:
  - Métodos `from_orm(model)` o compatibilidad nativa vía `model_validate(orm_obj, from_attributes=True)` para transformar instancias de:
    - `ArticleModel` <-> `ArticleSchema`
    - `FilingModel` <-> `FilingSchema`
    - `RedditPostModel` <-> `PostSchema`
    - `PriceDataModel` <-> `PriceSchema`
    - `EnrichedSignalModel` <-> `EnrichedSignalSchema`
- [x] **Backward Compatibility**:
  - Re-exportar o armonizar con `src/market_intel/extractors/schemas.py` para asegurar que los extractores de M1 mantengan retrocompatibilidad.
- [x] **Unit Tests & 100% Coverage**:
  - Suite de tests en `tests/unit/test_schemas.py` (`pytest -m issue_9`).
  - Cobertura integral en `src/market_intel/core/schemas.py`.

---

## Technical Design & Decisions

### 1. Ubicación de Modelos (`src/market_intel/core/schemas.py`)
Centraliza los esquemas canónicos compartidos entre ingesta, persistencia, pipelines NLP y APIs REST.

### 2. Estructura de Schemas y Campos
1. **`ArticleSchema`**
   - `id`: `uuid.UUID | None`
   - `source_id`: `str | None`
   - `source_name`: `str`
   - `author`: `str | None`
   - `title`: `str` (min_length=1)
   - `description`: `str | None`
   - `url`: `str` (con validador de normalización)
   - `url_to_image`: `str | None`
   - `published_at`: `datetime` (UTC)
   - `content`: `str | None`

2. **`FilingMetricsSchema` & `FilingSchema`**
   - `FilingMetricsSchema`: `revenue: float | None`, `eps: float | None`, `assets: float | None`, `raw_metrics: dict[str, Any] | None`
   - `FilingSchema`:
     - `id`: `uuid.UUID | None`
     - `cik`: `str` (longitud 10 dígitos o normalizado a 10 con zfill)
     - `company_name`: `str`
     - `filing_type`: `str` ("10-K", "10-Q", etc.)
     - `filing_date`: `datetime` (UTC)
     - `period_of_report`: `datetime | None`
     - `metrics`: `FilingMetricsSchema`

3. **`PostSchema`**
   - `id`: `uuid.UUID | None`
   - `post_id`: `str`
   - `subreddit`: `str`
   - `title`: `str`
   - `body`: `str | None`
   - `score`: `int` (default 0)
   - `num_comments`: `int` (default 0)
   - `created_utc`: `datetime` (UTC)
   - `flair`: `str | None`

4. **`PriceSchema`**
   - `id`: `uuid.UUID | None`
   - `symbol`: `str` (validador uppercase)
   - `date`: `datetime` (UTC)
   - `open`: `float`
   - `high`: `float`
   - `low`: `float`
   - `close`: `float`
   - `adjusted_close`: `float | None`
   - `volume`: `int` (ge=0)

5. **`EnrichedSignalSchema`**
   - `id`: `uuid.UUID | None`
   - `source_type`: `str` ("article", "filing", "reddit_post")
   - `source_id`: `uuid.UUID | None`
   - `symbol`: `str` (validador uppercase)
   - `signal_type`: `str` ("sentiment", "anomaly", "summary", etc.)
   - `sentiment_score`: `float | None` (ge=-1.0, le=1.0)
   - `sentiment_label`: `str | None` ("bullish", "bearish", "neutral")
   - `confidence`: `float | None` (ge=0.0, le=1.0)
   - `summary`: `str | None`
   - `entities`: `dict[str, Any] | None`
   - `embedding`: `list[float] | None` (longitud 1536 si está presente)
   - `timestamp`: `datetime` (UTC)

### 3. Validadores Reutilizables
```python
@field_validator("url", mode="before")
@classmethod
def validate_url(cls, v: str) -> str:
    return normalize_url(v)

@field_validator("symbol", mode="before")
@classmethod
def validate_symbol(cls, v: str) -> str:
    return v.strip().upper()
```

### 4. Adaptadores ORM Bidireccionales
Cada schema implementará:
- `classmethod from_orm(cls, obj: Any) -> Self`: Facilita la conversión desde modelos SQLAlchemy (`model_validate(obj, from_attributes=True)`).
- `to_orm(self) -> Model`: Método opcional para generar la instancia correspondiente de SQLAlchemy.

---

## Implementation Tasks

### 1. Preparación y Branching
```bash
make start-issue ID=9 NAME=pydantic-schemas
```

### 2. Implementación de Schemas Canónicos
- **Archivo**: `src/market_intel/core/schemas.py`
  - Definir `ArticleSchema`, `FilingMetricsSchema`, `FilingSchema`, `PostSchema`, `PriceSchema`, `EnrichedSignalSchema`.
  - Configurar `model_config` con `strict=True`, `from_attributes=True`, `json_schema_extra`.
  - Implementar validadores para URLs, símbolos y fechas.
  - Implementar métodos `from_orm`.
- **Archivo**: `src/market_intel/core/__init__.py`
  - Re-exportar todos los esquemas canónicos.
- **Archivo**: `src/market_intel/extractors/schemas.py`
  - Armonizar y re-exportar esquemas desde `core.schemas` manteniendo compatibilidad con M1.

### 3. Suite de Tests
- **Archivo**: `tests/unit/test_schemas.py`
  - Tests unitarios con marker `@pytest.mark.issue_9` y `@pytest.mark.unit`.
  - Validación de campos requeridos y tipos estrictos.
  - Validación de normalización de URLs en `ArticleSchema`.
  - Validación de ticker en mayúsculas en `PriceSchema` y `EnrichedSignalSchema`.
  - Validación de conversión bidireccional ORM <-> Pydantic para los 5 modelos.
  - Validación de serialización JSON y `json_schema_extra`.
  - 100% de cobertura en `src/market_intel/core/schemas.py`.

### 4. Verificación de Calidad
```bash
make test-issue ID=9
make check
make test
```

### 5. Finalización del Issue y Cierre del Milestone M2
```bash
make finish-issue ID=9 MSG="feat(core): implement canonical pydantic schemas and orm adapters"
make finish-milestone MILESTONE=M2
```
