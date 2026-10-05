#!/usr/bin/env bash
# ==============================================================================
# Container Lifecycle & Entrypoint Manager
# Supports roles: api, worker, beat, migrate, or arbitrary commands
# ==============================================================================
set -euo pipefail

# Helper function: Wait for a TCP socket connection using Python standard library
wait_for_service() {
    local host="$1"
    local port="$2"
    local service_name="${3:-service}"
    local max_retries="${4:-30}"
    local retry_delay="${5:-2}"
    local attempt=1

    echo "==> Waiting for ${service_name} at ${host}:${port}..."
    until python3 -c "import socket; s = socket.create_connection(('${host}', int(${port})), timeout=2); s.close()" 2>/dev/null; do
        if [ "$attempt" -ge "$max_retries" ]; then
            echo "ERROR: Timed out waiting for ${service_name} at ${host}:${port} after $((max_retries * retry_delay))s." >&2
            exit 1
        fi
        echo "    Attempt ${attempt}/${max_retries}: ${service_name} not available yet. Retrying in ${retry_delay}s..."
        sleep "$retry_delay"
        attempt=$((attempt + 1))
    done
    echo "==> ${service_name} is ready!"
}

# Helper function: Parse host and port from Redis URL (e.g. redis://host:port/0)
check_redis_dependency() {
    if [ -n "${REDIS_URL:-}" ]; then
        local redis_host_port
        redis_host_port=$(python3 -c "from urllib.parse import urlparse; u = urlparse('${REDIS_URL}'); print(f'{u.hostname or \"redis\"}:{u.port or 6379}')" 2>/dev/null || echo "redis:6379")
        local r_host="${redis_host_port%%:*}"
        local r_port="${redis_host_port##*:}"
        wait_for_service "$r_host" "$r_port" "Redis Cache"
    elif [ -n "${REDIS_HOST:-}" ]; then
        wait_for_service "$REDIS_HOST" "${REDIS_PORT:-6379}" "Redis Cache"
    fi
}

# Helper function: Check PostgreSQL dependency
check_postgres_dependency() {
    if [ -n "${POSTGRES_HOST:-}" ]; then
        wait_for_service "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}" "PostgreSQL Database"
    fi
}

# Command dispatching
ROLE="${1:-api}"

case "$ROLE" in
    api)
        echo "==> Starting Market Intelligence REST & WebSocket API..."
        check_postgres_dependency
        check_redis_dependency

        # Run database schema migrations prior to launching API
        echo "==> Applying Alembic schema migrations..."
        alembic upgrade head
        echo "==> Migrations applied successfully."

        # Launch production Uvicorn ASGI server
        exec uvicorn market_intel.api.app:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}" \
            --workers "${UVICORN_WORKERS:-2}" \
            --log-level "${LOG_LEVEL:-info}"
        ;;

    worker)
        echo "==> Starting Celery Background Task Worker..."
        check_postgres_dependency
        check_redis_dependency

        exec celery -A market_intel.core.celery_app worker \
            --loglevel="${LOG_LEVEL:-INFO}" \
            -Q high_priority,default,dlq \
            --concurrency="${CELERY_CONCURRENCY:-4}"
        ;;

    beat)
        echo "==> Starting Celery Beat Scheduler..."
        check_redis_dependency

        exec celery -A market_intel.core.celery_app beat \
            --loglevel="${LOG_LEVEL:-INFO}"
        ;;

    migrate)
        echo "==> Running Alembic Database Migrations..."
        check_postgres_dependency

        exec alembic upgrade head
        ;;

    *)
        # Passthrough execution for ad-hoc debugging or custom commands
        exec "$@"
        ;;
esac
