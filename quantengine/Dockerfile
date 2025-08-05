# syntax=docker/dockerfile:1

########################
# Builder (with Poetry)
########################
FROM python:3.11-slim-bookworm AS builder

ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    PATH=/opt/poetry/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# Export only runtime deps to requirements.txt
RUN poetry export --only main -f requirements.txt -o requirements.txt

########################
# Runtime (slim)
########################
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Non-root + writable SQLite dir
RUN useradd -m app \
 && mkdir -p /data \
 && chown -R app:app /app /data
USER app

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -qO- http://localhost:8001/ || exit 1
# Entrypoint runs the consumer script that starts the metrics server on 8001
# (If you start via python -m or similar, keep that here.)
