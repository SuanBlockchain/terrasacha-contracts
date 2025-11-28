# Multi-stage Dockerfile for Terrasacha FastAPI Service
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies from pyproject.toml
# Extract and install only the runtime dependencies, not the package itself
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    "opshin>=0.26.0" \
    "python-dotenv>=1.1.1,<2.0.0" \
    "requests>=2.32.5,<3.0.0" \
    "sqlmodel>=0.0.27" \
    "asyncpg>=0.30.0" \
    "alembic>=1.17.0" \
    "fastapi[standard]>=0.119.0" \
    "pydantic>=2.12.2" \
    "pydantic-settings>=2.11.0" \
    "psycopg2-binary>=2.9.11" \
    "cryptography>=44.0.0" \
    "argon2-cffi>=23.1.0" \
    "pyjwt>=2.10.0"

# Stage 2: Runtime - Create minimal production image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src:$PYTHONPATH

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser . .

# Copy and set permissions for entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check (increased start-period to allow for migrations)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()"

# Default command - runs migrations then starts server
# For development, override this in docker-compose.yml
ENTRYPOINT ["/app/docker-entrypoint.sh"]
