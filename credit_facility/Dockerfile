# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS builder

ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    PATH="${POETRY_HOME}/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml ./
# Recompute lock inside build for reproducibility
RUN poetry lock --no-interaction --no-ansi
RUN poetry export --only main -f requirements.txt -o requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json

WORKDIR /app

COPY --from=builder /app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m app && chown -R app:app /app
USER app

EXPOSE 8050

HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=25s \
  CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8050/healthz', timeout=5).getcode()==200 else sys.exit(1)"

CMD ["uvicorn","credit_facility.api:create_app","--host","0.0.0.0","--port","8050"]
