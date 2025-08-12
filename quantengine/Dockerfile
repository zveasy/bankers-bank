# syntax=docker/dockerfile:1

########################
# Builder (Poetry only)
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
COPY pyproject.toml ./
# No poetry.lock copied – generate lock & export runtime deps only
RUN poetry lock --no-interaction --no-ansi \
 && poetry export --only main -f requirements.txt -o requirements.txt

########################
# Runtime
########################
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json

WORKDIR /app

COPY --from=builder /app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Non-root user for security and ensure writable volume directory
RUN useradd -m app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER app

EXPOSE 8000

# Healthcheck probes /healthz
HEALTHCHECK --interval=10s --timeout=5s --start-period=25s --retries=12 CMD python -c "import sys, urllib.request, urllib.error;\n\ntry:\n    with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5) as r:\n        sys.exit(0 if r.getcode() == 200 else 1)\nexcept Exception:\n    sys.exit(1)"

CMD ["uvicorn", "quantengine.main:app", "--host", "0.0.0.0", "--port", "8000"]
