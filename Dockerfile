# Production Dockerfile for MemoryBrain Platform
FROM python:3.11-slim

WORKDIR /app

# Install system runtime & build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages globally
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

ENV PORT=8000

CMD ["sh", "-c", "uvicorn agent_memory.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
