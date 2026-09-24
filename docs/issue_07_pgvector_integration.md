# Issue 7: pgvector integration for embedding storage and similarity search

**Branch:** `feature/issue-7-pgvector-integration`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M2 — Storage & Indexing Layer  

---

## Objective

Habilitar la extensión `pgvector` en PostgreSQL para almacenar embeddings vectoriales de 1536 dimensiones (compatibles con `text-embedding-3-small` / OpenAI) en la tabla `enriched_signals`, configurar el índice de búsqueda aproximada `ivfflat` mediante una nueva migración de Alembic, e implementar la clase `EmbeddingRepository` con métodos asíncronos para `upsert` y búsqueda por similitud de coseno (`similarity_search`) retornando los top-K resultados.

---

## Acceptance Criteria

- [x] **pgvector Dependency**: Incorporar `pgvector` en las dependencias de `storage` en `pyproject.toml`.
- [x] **Alembic Migration (`0002_add_vector_embeddings.py`)**:
  - Habilitar extensión PostgreSQL `vector` (`CREATE EXTENSION IF NOT EXISTS vector`).
  - Añadir columna `embedding VECTOR(1536)` a la tabla `enriched_signals`.
  - Crear índice `ivfflat` con `vector_cosine_ops` en `enriched_signals(embedding)`.
  - Implementar rollback limpio en `downgrade()`.
- [x] **Model Update**: Actualizar `EnrichedSignalModel` en `src/market_intel/loaders/models.py` para mapear el campo `embedding` usando `Vector(1536)` con fallback de compatibilidad SQLite para testing.
- [x] **`EmbeddingRepository` Class**:
  - Ubicado en `src/market_intel/loaders/repository.py`.
  - Método `upsert(...)` para insertar o actualizar señales enriquecidas con su embedding.
  - Método `similarity_search(query_embedding, top_k=5, symbol=None, signal_type=None)` ordenado por distancia de coseno (`cosine_distance`).
- [x] **Unit Tests**: Suite de tests unitarios (`pytest -m issue_7`) validando la matemática de similitud de coseno, top-K ranking, filtros, repositorios y migración.

---

## Technical Design & Decisions

### 1. Dependencias (`pyproject.toml`)
Añadir `pgvector>=0.3.0` a `[project.optional-dependencies] storage`.
Provee integración nativa con SQLAlchemy ORM (`from pgvector.sqlalchemy import Vector`).

### 2. Modelo Declarativo (`src/market_intel/loaders/models.py`)
En `EnrichedSignalModel`:
```python
embedding: Mapped[list[float] | None] = mapped_column(
    Vector(1536).with_variant(JSON(), "sqlite"),
    nullable=True,
)
```
- `Vector(1536)` para PostgreSQL/pgvector.
- Fallback con `.with_variant(JSON(), "sqlite")` para que las suites de tests unitarios en memoria sigan corriendo sin requerir una instancia real de PostgreSQL con la extensión instalada.

### 3. Migración de Alembic (`0002_add_vector_embeddings.py`)
- `upgrade()`:
  1. `op.execute("CREATE EXTENSION IF NOT EXISTS vector;")`
  2. `op.add_column("enriched_signals", sa.Column("embedding", Vector(1536), nullable=True))`
  3. `op.create_index("ix_enriched_signals_embedding_ivfflat", "enriched_signals", ["embedding"], postgresql_using="ivfflat", postgresql_with={"lists": 100}, postgresql_ops={"embedding": "vector_cosine_ops"})`
- `downgrade()`:
  1. `op.drop_index("ix_enriched_signals_embedding_ivfflat", table_name="enriched_signals")`
  2. `op.drop_column("enriched_signals", "embedding")`

### 4. `EmbeddingRepository` (`src/market_intel/loaders/repository.py`)
- Clase `EmbeddingRepository`:
  - Inyección de `AsyncSession`.
  - `upsert(signal: EnrichedSignalModel) -> EnrichedSignalModel` o creación/actualización por `id`.
  - `similarity_search(query_embedding: list[float], top_k: int = 5, symbol: str | None = None, signal_type: str | None = None) -> list[tuple[EnrichedSignalModel, float]]`:
    - Filtra por `symbol` y `signal_type` si se proporcionan.
    - Calcula la distancia de coseno: `EnrichedSignalModel.embedding.cosine_distance(query_embedding)`.
    - Ordena de menor a mayor distancia (`ASC`).
    - Convierte la distancia a score de similitud: `1.0 - distance`.
    - Retorna tuplas `(signal, similarity_score)` limitadas a `top_k`.

### 5. Suite de Pruebas (`tests/unit/test_embedding_repository.py`)
- Pruebas unitarias aisladas:
  - Función auxiliar de cálculo de distancia/similitud de coseno pura en Python.
  - Validación de ranking y ordenamiento top-K con vectores conocidos (vectores ortogonales, paralelos, opuestos).
  - Test de `EmbeddingRepository.similarity_search` y `upsert` con mocks de `AsyncSession`.
  - Test de compatibilidad del modelo `EnrichedSignalModel` con columna `embedding`.
  - Test de estructura de la migración `0002_add_vector_embeddings.py` (descubrimiento en cadena de Alembic `0001 -> 0002`).
  - Test de generación de SQL offline de Alembic con `CREATE EXTENSION` e índice `ivfflat`.

---

## Implementation Tasks

### 1. Preparación y Branching
```bash
make start-issue ID=7 NAME=pgvector-integration
```

### 2. Dependencias y Configuración
- **Archivo**: `pyproject.toml`
  - Añadir `pgvector>=0.3.0` a la lista `storage`.
  - Verificar que el marker `issue_7` esté registrado en `[tool.pytest.ini_options]`.
- Instalar dependencias:
  ```bash
  make deps-all
  ```

### 3. Actualización del Modelo ORM
- **Archivo**: `src/market_intel/loaders/models.py`
  - Importar `Vector` de `pgvector.sqlalchemy`.
  - Añadir el atributo `embedding: Mapped[list[float] | None]` a `EnrichedSignalModel`.
  - Mantener compatibilidad SQLite vía `.with_variant(JSON(), "sqlite")`.

### 4. Migración de Alembic
- **Archivo**: `src/market_intel/loaders/migrations/versions/0002_add_vector_embeddings.py`
  - Encadenar a `down_revision = "0001_initial_schema"`.
  - Implementar creación de extensión, columna e índice `ivfflat`.
  - Implementar rollback en `downgrade()`.

### 5. Repositorio de Embeddings
- **Archivo**: `src/market_intel/loaders/repository.py`
  - Implementar clase `EmbeddingRepository` con inicializador `(session: AsyncSession)`.
  - Implementar método `upsert`.
  - Implementar método `similarity_search` con soporte de filtros opcionales.
  - Implementar método auxiliar `cosine_similarity(v1, v2)` para validaciones y fallback.
- **Archivo**: `src/market_intel/loaders/__init__.py`
  - Exportar `EmbeddingRepository`.

### 6. Suite de Tests
- **Archivo**: `tests/unit/test_embedding_repository.py`
  - Tests unitarios completos marcados con `@pytest.mark.unit` y `@pytest.mark.issue_7`.
  - Validación de operaciones matemáticas vectoriales, queries y repositorios.
  - Validación de la migración 0002 en Alembic.

### 7. Verificación de Calidad
```bash
make test-issue ID=7
make check
make test
```

### 8. Finalización y PR
```bash
make finish-issue ID=7 MSG="feat(storage): integrate pgvector for embedding storage and similarity search"
```
