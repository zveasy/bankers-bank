# syntax=docker/dockerfile:1
# Bank Connector service image
FROM python:3.11-slim AS base

# Install system dependencies (if any additional are needed, add here)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    PATH="$POETRY_HOME/bin:$PATH" \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Set workdir
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml poetry.lock ./

# Configure Poetry to not create a virtualenv, then install only main dependencies
RUN poetry config virtualenvs.create false \
    && poetry lock --no-update \
    && poetry install --only main --no-ansi --no-root

# Copy project source (entire repo so that shared modules are available)
COPY . .

EXPOSE 8080 8001

# run as non-root
RUN adduser -D app 2>/dev/null || useradd -m app
USER app

CMD ["uvicorn", "bank_connector.main:app", "--host", "0.0.0.0", "--port", "8080"]
