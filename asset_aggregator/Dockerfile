# syntax=docker/dockerfile:1
# Asset Aggregator (Treasury Orchestrator) service image
FROM python:3.11-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    PATH="$POETRY_HOME/bin:$PATH" \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy dependency manifests
COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry lock --no-update \
    && poetry install --only main --no-ansi --no-root

# Copy source code
COPY . .

EXPOSE 8000 8001

# run as non-root
RUN adduser -D app 2>/dev/null || useradd -m app
USER app

CMD ["uvicorn", "asset_aggregator.api:app", "--host", "0.0.0.0", "--port", "8000"]
