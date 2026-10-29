# ==============================================================================
# Production Dockerfile for Raspberry Pi ARM64 / Linux K3s Cluster
# ==============================================================================
FROM python:3.11-slim

# Prevent bytecode caching and enable unbuffered output for instant stdout logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal runtime library dependencies for PostgreSQL client and probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Optimize Docker layer caching: install Python wheels before copying application source
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application entrypoint
COPY app.py .

# Security hardening: Run container as unprivileged non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Production WSGI server using Gunicorn: 2 workers, logging mapped to stdout/stderr
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

