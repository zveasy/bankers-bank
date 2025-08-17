# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.8.2 POETRY_HOME="/opt/poetry" POETRY_NO_INTERACTION=1
ENV PATH="${POETRY_HOME}/bin:${PATH}"
ENV LOG_FORMAT=json
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app
COPY pyproject.toml ./
# Recompute lock inside build for reproducibility
RUN poetry lock --no-interaction --no-ansi
# Recompute the lock inside the build so export is consistent with pyproject
RUN poetry lock --no-interaction --no-ansi
RUN poetry export -f requirements.txt --output /tmp/requirements.txt --without-hashes

FROM python:3.11-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /tmp/requirements.txt /tmp/requirements.txt
# install runtime deps; pin Pydantic v1 for constr(regex=...) compatibility
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir "pydantic<2" \
    && pip install --no-cache-dir psycopg2-binary==2.9.9 \
    && pip install --no-cache-dir "sqlmodel>=0.0.22"   # belt & suspenders

COPY . .
EXPOSE 8080 8001

# Simple container-level healthcheck
HEALTHCHECK CMD curl -f http://localhost:8080/healthz || exit 1
RUN useradd -m app || true
USER app
CMD ["uvicorn", "bank_connector.main:app", "--host", "0.0.0.0", "--port", "8080"]
