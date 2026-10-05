# ==============================================================================
# Multi-Stage Production Dockerfile for AI-Powered Market Intelligence
# Stage 1: Build virtual environment and compile native wheels
# Stage 2: Lean, unprivileged security-hardened runtime container
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system build dependencies required for compiling C extensions & pg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade core packaging tools
RUN pip install --upgrade pip setuptools wheel

# Copy project manifest and install dependencies
COPY pyproject.toml ./
COPY src/ /build/src/
COPY alembic.ini /build/alembic.ini

# Install core market intelligence package with production dependencies
RUN pip install --no-cache-dir .

# ------------------------------------------------------------------------------
# Stage 2: Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    APP_ENV=production

# Install minimal runtime system libraries and signal forwarder (tini)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user and group (UID/GID 10001)
RUN groupadd -g 10001 marketintel && \
    useradd -u 10001 -g marketintel -s /bin/bash -m marketintel

# Copy virtual environment from builder stage
COPY --from=builder --chown=marketintel:marketintel /opt/venv /opt/venv

# Copy application code, Alembic migrations, and configuration
COPY --chown=marketintel:marketintel src/ /app/src/
COPY --chown=marketintel:marketintel alembic.ini /app/alembic.ini
COPY --chown=marketintel:marketintel pyproject.toml /app/pyproject.toml

# Copy entrypoint script and ensure execution permissions
COPY --chown=marketintel:marketintel infra/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create runtime directories for temporary storage and logs
RUN mkdir -p /app/data /app/logs && chown -R marketintel:marketintel /app

# Switch to unprivileged execution user
USER marketintel:marketintel

# Expose HTTP and WebSocket API port
EXPOSE 8000

# Native container healthcheck validating FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["api"]
