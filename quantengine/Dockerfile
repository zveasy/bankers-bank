# syntax=docker/dockerfile:1
# Quantengine (Kafka consumer) service image
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

# Copy dependency manifests first
COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry lock --no-update \
    && poetry install --only main --no-ansi --no-root

# Copy source code
COPY . .

CMD ["python", "-m", "quantengine.kafka_consumer", "redpanda:9092"]
