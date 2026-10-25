# Backend Dockerfile for WPI AI Adviser
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Prevent debconf warnings during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching (runtime deps only; tests use requirements-dev.txt)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user. Its uid should own the mounted ./database directory
# (Chroma writes to it), so it defaults to 1000, the usual first host user.
ARG APP_UID=1000
RUN useradd --create-home --uid ${APP_UID} appuser

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

# Expose port
EXPOSE 8000

# Liveness only: /api/status calls Gemini and needs a token, so it must not be polled
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Session state lives in Redis, so any worker can serve any request.
# X-Forwarded-* headers are trusted only from FORWARDED_ALLOW_IPS (the nginx container).
ENV UVICORN_WORKERS=2 \
    FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS}\""]
