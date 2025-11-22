# ============================================
# Nadoo Sandbox Service - Multi-stage Build
# Secure Docker container for code execution
# ============================================

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install Poetry and dependencies
RUN pip install --no-cache-dir poetry==1.7.1 && \
    poetry config virtualenvs.in-project true && \
    poetry install --no-dev --no-interaction --no-ansi

# Stage 2: Runtime
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r nadoo && \
    useradd -r -g nadoo -u 1001 nadoo && \
    mkdir -p /app /tmp/nadoo_sandbox && \
    chown -R nadoo:nadoo /app /tmp/nadoo_sandbox

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder --chown=nadoo:nadoo /build/.venv /app/.venv

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --chown=nadoo:nadoo src ./src
COPY --chown=nadoo:nadoo pyproject.toml ./

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    NADOO_SANDBOX_HOST=0.0.0.0 \
    NADOO_SANDBOX_PORT=8002 \
    NADOO_SANDBOX_MAX_EXECUTION_TIME=60 \
    NADOO_SANDBOX_MAX_MEMORY=512m \
    NADOO_SANDBOX_MAX_CPU=0.5

# Security: Drop all capabilities and add only what's needed
# Note: docker.sock access requires privileged mode or proper capabilities
RUN setcap cap_net_bind_service=+ep /usr/bin/python3.11 || true

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Expose port
EXPOSE 8002

# Switch to non-root user
USER nadoo

# Run application with proper signal handling
CMD ["python", "-m", "src.main"]

# Metadata
LABEL maintainer="Nadoo Team <dev@nadoo.ai>" \
      version="1.0.0" \
      description="Nadoo Sandbox Service - Secure code execution" \
      org.opencontainers.image.source="https://github.com/nadoo-ai/nadoo-kb"
