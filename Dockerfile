# ── SecureMedia — Production Dockerfile ─────────────────────────────────
# Multi-stage build: slim Python image with only runtime dependencies.
# Usage:
#   docker build -t securemedia .
#   docker run -p 8000:8000 --env-file .env securemedia
# ────────────────────────────────────────────────────────────────────────

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed to compile Python packages (numpy, opencv, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ libffi-dev libssl-dev \
        libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && pip install --no-cache-dir --prefix=/install gunicorn

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

LABEL maintainer="SecureMedia Team"
LABEL description="Digital Audio & Video Encryption with Watermarking"

# Runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r securemedia && useradd -r -g securemedia -d /app -s /sbin/nologin securemedia

WORKDIR /app

# Copy application code
COPY app/ app/
COPY config.py run.py wsgi.py ./
COPY requirements.txt ./

# Create storage directory with correct permissions
RUN mkdir -p /app/storage /app/instance \
    && chown -R securemedia:securemedia /app

USER securemedia

# Expose Gunicorn port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with Gunicorn (production WSGI server)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]
