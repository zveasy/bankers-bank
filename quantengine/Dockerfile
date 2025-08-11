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
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Non-root user for security
RUN useradd -m app && chown -R app:app /app
USER app

EXPOSE 8000

# Healthcheck probes /healthz
HEALTHCHECK --interval=10s --timeout=5s --start-period=25s --retries=12 CMD python - <<'PY' || exit 1
import urllib.request, sys
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5) as r:
        sys.exit(0 if r.getcode()==200 else 1)
except Exception:
    sys.exit(1)
PY

CMD ["uvicorn", "quantengine.main:app", "--host", "0.0.0.0", "--port", "8000"]

# END
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
# Recompute lock inside build for reproducibility
RUN poetry lock --no-interaction --no-ansi
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
