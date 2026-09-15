# Issue 1: Bootstrap market_intel package skeleton and config

## Objetivo
Establecer la configuración base del paquete `market_intel`, incluyendo el manejo de variables de entorno, configuración de logging centralizada, y la jerarquía base de excepciones.

## Tareas

### 1. Preparación y Branching
```bash
make start-issue ID=01 NAME=package-skeleton
```

### 2. Implementación de Core Modules
- **Acción**: Implementar manejo de configuración.
- **Implementación**: Crear `src/market_intel/core/config.py` usando `pydantic-settings` para cargar variables del `.env`.

- **Acción**: Configurar logging base.
- **Implementación**: Crear `src/market_intel/core/logger.py` para exponer un logger unificado con formato estándar.

- **Acción**: Definir excepciones base.
- **Implementación**: Crear `src/market_intel/core/exceptions.py` con una clase `MarketIntelError` base.

### 3. Testing Local
```bash
make test-issue ID=01
```

### 4. Git y Cierre
```bash
make finish-issue ID=01
```
