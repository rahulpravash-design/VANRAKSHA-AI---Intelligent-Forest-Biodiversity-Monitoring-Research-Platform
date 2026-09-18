# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: libpq for psycopg (binary wheel still needs libpq at runtime
# on slim images), and build-essential in case any dependency has no wheel
# for this platform.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# The AI engine is a sibling package the backend imports in-process by
# default (see app/services/ai_client.py), so it ships in the same image.
COPY ai ai
COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/docker-entrypoint.sh backend/docker-entrypoint.sh
COPY scripts scripts
RUN chmod +x backend/docker-entrypoint.sh

WORKDIR /app/backend
RUN mkdir -p storage

EXPOSE 8000
ENV PYTHONPATH=/app:/app/backend

ENTRYPOINT ["./docker-entrypoint.sh"]
