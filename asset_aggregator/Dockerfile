# syntax=docker/dockerfile:1

########################
# Builder (Poetry only)
########################
FROM python:3.11-slim-bookworm AS builder

ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    PATH=/opt/poetry/bin:$PATH

# Build tools only in builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app
COPY pyproject.toml poetry.lock ./

# Export runtime deps for pip (no dev)
RUN poetry export --only main -f requirements.txt -o requirements.txt

########################
# Runtime (slim)
########################
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Non-root
RUN useradd -m app && chown -R app:app /app
USER app

EXPOSE 8000 8001
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -qO- http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "asset_aggregator.api:app", "--host", "0.0.0.0", "--port", "8000"]
