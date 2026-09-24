# Issue 8: Redis caching layer for hot-path deduplication

**Branch:** `feature/issue-8-redis-cache`  
**Status:** In Progress  
**PR:** TBD  
**Milestone:** M2 — Storage & Indexing Layer  

---

## Objective

Implementar una capa de deduplicación de alto rendimiento respaldada por Redis asíncrono (`redis.asyncio`) en `src/market_intel/core/cache.py`. La capa gestionará huellas digitales (hashes criptográficos SHA-256 / normalización de URLs) con expiración basada en TTL y expondrá métricas de aciertos (*cache hits*) y fallos (*cache misses*) a través de contadores de Prometheus.

---

## Acceptance Criteria

- [x] **Async Redis Client**: Integración del cliente asíncrono oficial `redis-py` (`redis.asyncio`) utilizando `redis_url` desde `Settings`.
- [x] **`DeduplicationCache` Class**:
  - Ubicado en `src/market_intel/core/cache.py`.
  - Generación de fingerprints estandarizados mediante hashing SHA-256 de URLs o contenidos crudos.
  - Método atómico `check_and_set(key, ttl=86400)` utilizando operaciones `SET ... EX ... NX`.
  - Métodos `is_duplicate(key)`, `set_fingerprint(key, ttl)` y `close()`.
- [x] **Prometheus Metrics**:
  - Exposición de contadores `cache_hits_total` y `cache_misses_total` usando `prometheus_client`.
  - Registro automático de hits y misses en cada operación de deduplicación.
- [x] **Exceptions & Resilience**:
  - Definición de `CacheError` en `src/market_intel/core/exceptions.py`.
  - Manejo robusto de errores de conexión y timeouts.
- [x] **Unit Tests**:
  - Suite de tests unitarios (`pytest -m issue_8`) con cliente Redis mockeado (`AsyncMock`).
  - Validación de fingerprinting, expiración de TTL, métricas de Prometheus y degradación ante fallos.

---

## Technical Design & Decisions

### 1. Dependencias (`pyproject.toml`)
Se añaden al grupo `storage`:
- `redis>=5.0.0`: Soporte nativo para `redis.asyncio` y pooling de conexiones.
- `prometheus-client>=0.20.0`: Registro de métricas estándar de Prometheus (`Counter`).

### 2. Arquitectura de `DeduplicationCache` (`src/market_intel/core/cache.py`)
- **Fingerprinting:**
  Normaliza las URLs (removiendo parámetros de tracking como `utm_*`, espacios y trailing slashes) y genera un digest hexadecimal SHA-256: `f"dedup:{prefix}:{sha256_hash}"`.
- **Operación Atómica:**
  Para evitar race conditions en ingestas concurrentes (ej. NewsAPI, Reddit, SEC filings en paralelo):
  ```python
  # redis.set with nx=True and ex=ttl
  was_set = await self.client.set(name=cache_key, value="1", ex=ttl, nx=True)
  if was_set:
      # Miss (clave nueva guardada)
      CACHE_MISSES_TOTAL.labels(cache_name=self.name).inc()
      return False  # Not a duplicate
  else:
      # Hit (clave ya existía)
      CACHE_HITS_TOTAL.labels(cache_name=self.name).inc()
      return True   # Is duplicate
  ```
- **Métricas de Prometheus:**
  ```python
  from prometheus_client import Counter

  CACHE_HITS_TOTAL = Counter(
      "cache_hits_total",
      "Total number of cache hits in deduplication layer",
      ["cache_name"],
  )
  CACHE_MISSES_TOTAL = Counter(
      "cache_misses_total",
      "Total number of cache misses in deduplication layer",
      ["cache_name"],
  )
  ```

---

## Implementation Tasks

### 1. Preparación y Branching
```bash
make start-issue ID=8 NAME=redis-cache
```

### 2. Dependencias y Configuración
- **Archivo**: `pyproject.toml`
  - Añadir `redis>=5.0.0` y `prometheus-client>=0.20.0` a `storage`.
  - Verificar que el marker `issue_8` esté en `[tool.pytest.ini_options]`.
- Instalar dependencias:
  ```bash
  make deps-all
  ```
- **Archivo**: `src/market_intel/core/exceptions.py`
  - Añadir `CacheError` heredando de `MarketIntelError`.

### 3. Implementación de la Capa de Caché
- **Archivo**: `src/market_intel/core/cache.py`
  - Definir métricas de Prometheus `CACHE_HITS_TOTAL` y `CACHE_MISSES_TOTAL`.
  - Implementar función auxiliar `generate_fingerprint(text, prefix="doc") -> str`.
  - Implementar clase `DeduplicationCache`:
    - Inicialización con cliente inyectado o resolución vía `Settings.redis_url`.
    - Métodos: `check_and_set`, `is_duplicate`, `set_fingerprint`, `delete`, `close`.
    - Context manager asíncrono (`async with DeduplicationCache(...) as cache:`).
- **Archivo**: `src/market_intel/core/__init__.py`
  - Re-exportar `DeduplicationCache`, `generate_fingerprint`, `CacheError`.

### 4. Suite de Tests
- **Archivo**: `tests/unit/test_cache.py`
  - Tests unitarios marcados con `@pytest.mark.unit` y `@pytest.mark.issue_8`.
  - Test de normalización y generación determinística de SHA-256.
  - Test de comportamiento de `check_and_set` con `AsyncMock` para escenarios de hit y miss.
  - Test de incremento de contadores de Prometheus en hits y misses.
  - Test de manejo de excepciones y timeouts (`ConnectionError`, `TimeoutError`).
  - Test de ciclo de vida del context manager asíncrono (`__aenter__` / `__aexit__`).

### 5. Verificación de Calidad
```bash
make test-issue ID=8
make check
make test
```

### 6. Finalización y PR
```bash
make finish-issue ID=8 MSG="feat(core): implement redis caching layer for hot-path deduplication"
```
