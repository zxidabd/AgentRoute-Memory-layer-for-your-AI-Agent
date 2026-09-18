# Production Dockerfile for MemoryBrain Platform
FROM python:3.11-slim as builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.11-slim as runner

WORKDIR /app

# Install libpq runtime for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Run as non-root user for enterprise security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Healthcheck for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz/liveness || exit 1

CMD ["uvicorn", "agent_memory.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
